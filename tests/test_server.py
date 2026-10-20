import json

import pytest
from starlette.testclient import TestClient

from proofdeck.alerts import ConsoleNotifier
from proofdeck.server import create_app
from proofdeck.service import publish, share


@pytest.fixture
def app(sf, founder_deck, founder_facts):
    with sf() as s:
        row = publish(s, founder_deck, founder_facts)
        open_link, gated = share(s, row, [{"name": "Priya", "firm": "Banyan"}])[0], \
            share(s, row, [{"name": "Lena"}], email_gate=True)[0]
    notifier = ConsoleNotifier()
    client = TestClient(create_app(sf, notifier=notifier, admin_key="k"))
    return client, notifier, row.id, open_link.token, gated.token


def test_viewer_sets_cookie_and_beacon_alerts(app):
    client, notifier, _, token, _ = app
    r = client.get(f"/d/{token}")
    assert r.status_code == 200 and "Freightline" in r.text and "/api/beacon" in r.text
    assert "pd_vid" in r.cookies
    r = client.post("/api/beacon", content=json.dumps({"token": token, "events": [{"card": 3, "ms": 50000}]}),
                    headers={"user-agent": "Mozilla/5.0 (Macintosh) Chrome/130"})
    assert r.status_code == 204
    assert any("opened" in m for m in notifier.sent) and any("🔥" in m for m in notifier.sent)


def test_beacon_without_cookie_or_bad_json(app):
    client, notifier, _, token, _ = app
    fresh = TestClient(client.app)
    assert fresh.post("/api/beacon", content=json.dumps({"token": token, "events": []})).status_code == 204
    assert notifier.sent == []
    assert client.post("/api/beacon", content="{not json").status_code == 400


def test_unknown_link_404(app):
    client, *_ = app
    assert client.get("/d/nope").status_code == 404


def test_email_gate(app):
    client, _, _, _, gated = app
    r = client.get(f"/d/{gated}")
    assert "Enter your email" in r.text and "/api/beacon" not in r.text
    assert "valid email" in client.post(f"/d/{gated}", data={"email": "nope"}).text
    r = client.post(f"/d/{gated}", data={"email": "lena@peakseed.example"})
    assert r.status_code == 200 and "/api/beacon" in r.text  # followed redirect, now unlocked


def test_admin_requires_key_and_shows_ranking(app):
    client, _, deck_id, token, _ = app
    assert client.get("/admin").status_code == 403
    client.get(f"/d/{token}")
    client.post("/api/beacon", content=json.dumps({"token": token, "events": [{"card": 1, "ms": 9000}]}))
    r = client.get(f"/admin/decks/{deck_id}?key=k")
    assert r.status_code == 200 and "Priya" in r.text and "Who to follow up with" in r.text
    assert client.get("/admin").status_code == 200  # key remembered in a cookie


def test_admin_pptx_download(app):
    client, _, deck_id, *_ = app
    r = client.get(f"/admin/decks/{deck_id}/pptx?key=k")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert "attachment" in r.headers["content-disposition"]
