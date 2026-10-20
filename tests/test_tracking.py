from datetime import datetime, timedelta

import pytest

from proofdeck.service import publish, share
from proofdeck.tracking import HOT_MS, MAX_EVENT_MS, engagement, follow_up_hint, leaderboard, record

MAC = "Mozilla/5.0 (Macintosh; Mac OS X) Chrome/130"
IPHONE = "Mozilla/5.0 (iPhone) Safari/18"
T0 = datetime(2026, 10, 12, 9, 0)


@pytest.fixture
def setup(sf, founder_deck, founder_facts):
    s = sf()
    row = publish(s, founder_deck, founder_facts)
    a, b = share(s, row, [{"name": "Priya", "firm": "Banyan"}, {"name": "Lena"}])
    idx = {c.type: i for i, c in enumerate(founder_deck.cards)}
    yield s, row, a, b, idx
    s.close()


def kinds(alerts):
    return [a.kind for a in alerts]


def test_t1_first_open_alerts_once(setup):
    s, _, a, _, _ = setup
    assert kinds(record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0)) == ["opened"]
    assert record(s, a.token, "v1", [{"card": 0, "ms": 3000}], user_agent=MAC, ip="1.2.3.4", now=T0) == []


def test_t2_cleared_cookies_same_network_is_same_person(setup):
    s, _, a, _, _ = setup
    record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0)
    assert record(s, a.token, "v1-new", [], user_agent=MAC, ip="1.2.3.99", now=T0) == []
    assert engagement(s, a).viewers == 1


def test_t3_new_device_new_network_is_a_forward(setup):
    s, _, a, _, _ = setup
    record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0)
    alerts = record(s, a.token, "v2", [], user_agent=IPHONE, ip="49.36.8.2", now=T0 + timedelta(hours=2))
    assert kinds(alerts) == ["forwarded"] and "Banyan" in alerts[0].message
    assert engagement(s, a).forwarded


def test_t4_coming_back_after_a_gap(setup):
    s, _, a, _, _ = setup
    record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0)
    assert record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0 + timedelta(hours=2)) == []
    assert kinds(record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0 + timedelta(days=1))) == ["returned"]


def test_t5_hot_card_alert_once(setup):
    s, _, a, _, idx = setup
    t = idx["traction"]
    record(s, a.token, "v1", [{"card": t, "ms": HOT_MS - 5000}], user_agent=MAC, ip="1.2.3.4", now=T0)
    alerts = record(s, a.token, "v1", [{"card": t, "ms": 6000}], user_agent=MAC, ip="1.2.3.4", now=T0)
    assert kinds(alerts) == ["hot_card"]
    assert record(s, a.token, "v1", [{"card": t, "ms": 60000}], user_agent=MAC, ip="1.2.3.4", now=T0) == []


def test_non_hot_cards_never_alert(setup):
    s, _, a, _, idx = setup
    record(s, a.token, "v1", [], user_agent=MAC, ip="1.2.3.4", now=T0)
    assert record(s, a.token, "v1", [{"card": idx["team"], "ms": 120000}], user_agent=MAC, ip="1.2.3.4", now=T0) == []


def test_t6_clamps_and_ignores_garbage(setup):
    s, _, a, _, _ = setup
    record(s, a.token, "v1", [{"card": 1, "ms": 10**9}, {"card": 99, "ms": 5000}, {"card": "x"}, {"ms": 5}],
           user_agent=MAC, ip="1.2.3.4", now=T0)
    e = engagement(s, a)
    assert e.per_card[1] == MAX_EVENT_MS // 1000 and sum(e.per_card) == MAX_EVENT_MS // 1000


def test_unknown_token_is_ignored(setup):
    s, *_ = setup
    assert record(s, "nope", "v1", [{"card": 0, "ms": 1000}]) == []


def test_leaderboard_and_hints(setup, founder_deck):
    s, row, a, b, idx = setup
    events = [{"card": i, "ms": 15000} for i in range(len(founder_deck.cards))]
    events[idx["traction"]]["ms"] = 60000
    record(s, a.token, "v1", events, user_agent=MAC, ip="1.2.3.4", now=T0)
    board = leaderboard(s, row)
    assert [e.link.recipient for e in board] == ["Priya", "Lena"]
    assert "Traction" in follow_up_hint(board[0], founder_deck)
    assert follow_up_hint(board[1], founder_deck).startswith("Not opened")
