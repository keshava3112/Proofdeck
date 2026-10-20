"""Web app: recipient viewer, beacon endpoint, private dashboard.

    proofdeck serve        # http://localhost:8000/admin?key=$PROOFDECK_ADMIN_KEY
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import tempfile
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from .alerts import Notifier, default_notifier
from .export_pptx import export_pptx
from .render import render_html
from .service import load_published
from .store import DeckRow, Link, Visit, make_session_factory
from .tracking import follow_up_hint, leaderboard, record

log = logging.getLogger(__name__)
VID_COOKIE = "pd_vid"
YEAR = 365 * 24 * 3600
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_env = Environment(loader=PackageLoader("proofdeck", "templates"), autoescape=select_autoescape(["html"]))


def create_app(session_factory=None, notifier: Notifier | None = None, admin_key: str | None = None) -> Starlette:
    sf = session_factory or make_session_factory()
    notify = notifier or default_notifier()
    key = admin_key or os.getenv("PROOFDECK_ADMIN_KEY") or secrets.token_urlsafe(12)
    if not (admin_key or os.getenv("PROOFDECK_ADMIN_KEY")):
        log.warning("PROOFDECK_ADMIN_KEY not set; this run's dashboard key is: %s", key)

    def client_ip(req: Request) -> str:
        fwd = req.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() if fwd else (req.client.host if req.client else "")

    def is_admin(req: Request) -> bool:
        return secrets.compare_digest(req.query_params.get("key") or req.cookies.get("pd_admin") or "", key)

    def admin_response(req: Request, resp: Response) -> Response:
        if req.query_params.get("key"):
            resp.set_cookie("pd_admin", key, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
        return resp

    # ------------------------------------------------------------ viewer
    async def view(req: Request) -> Response:
        token = req.path_params["token"]
        with sf() as s:
            link = s.scalar(select(Link).where(Link.token == token))
            if not link:
                return HTMLResponse("<h1>Link not found</h1>", status_code=404)
            vid = req.cookies.get(VID_COOKIE) or secrets.token_urlsafe(12)
            gated = link.email_gate and not req.cookies.get(f"pd_ok_{token}")
            if req.method == "POST" and link.email_gate:
                form = await req.form()
                email = str(form.get("email", "")).strip()
                if not EMAIL.match(email):
                    return HTMLResponse(_env.get_template("gate.html").render(title=link.deck.title, error=True))
                record(s, token, vid, [], user_agent=req.headers.get("user-agent", ""), ip=client_ip(req))
                v = s.scalar(select(Visit).where(Visit.link_id == link.id, Visit.visitor_id == vid))
                if v:
                    v.email = email
                    s.commit()
                resp = RedirectResponse(f"/d/{token}", status_code=303)
                resp.set_cookie(f"pd_ok_{token}", "1", max_age=YEAR, httponly=True, samesite="lax")
                resp.set_cookie(VID_COOKIE, vid, max_age=YEAR, httponly=True, samesite="lax")
                return resp
            if gated:
                resp = HTMLResponse(_env.get_template("gate.html").render(title=link.deck.title, error=False))
            else:
                deck, facts, brand = load_published(link.deck)
                resp = HTMLResponse(render_html(deck, facts, brand, token=token))
            resp.set_cookie(VID_COOKIE, vid, max_age=YEAR, httponly=True, samesite="lax")
            return resp

    async def beacon(req: Request) -> Response:
        try:
            body = json.loads(await req.body() or b"{}")
        except json.JSONDecodeError:
            return Response(status_code=400)
        token = str(body.get("token", ""))
        vid = req.cookies.get(VID_COOKIE)
        if not token or not vid:
            return Response(status_code=204)
        events = body.get("events") or []
        if not isinstance(events, list):
            return Response(status_code=400)
        with sf() as s:
            for a in record(s, token, vid, events[:100], user_agent=req.headers.get("user-agent", ""), ip=client_ip(req)):
                notify.send(a.message)
        return Response(status_code=204)

    # ------------------------------------------------------------- admin
    async def admin(req: Request) -> Response:
        if not is_admin(req):
            return HTMLResponse("<h1>Forbidden</h1><p>Open /admin?key=YOUR_KEY</p>", status_code=403)
        with sf() as s:
            decks = s.scalars(select(DeckRow).order_by(DeckRow.id.desc())).all()
            rows = []
            for d in decks:
                board = leaderboard(s, d)
                rows.append((d, len(d.links), sum(1 for e in board if e.viewers), sum(e.seconds for e in board)))
            return admin_response(req, HTMLResponse(_env.get_template("admin.html").render(page="list", rows=rows)))

    async def admin_deck(req: Request) -> Response:
        if not is_admin(req):
            return HTMLResponse("Forbidden", status_code=403)
        with sf() as s:
            row = s.get(DeckRow, int(req.path_params["deck_id"]))
            if not row:
                return HTMLResponse("Not found", status_code=404)
            deck, _, _ = load_published(row)
            board = leaderboard(s, row)
            totals = [sum(e.per_card[i] for e in board) for i in range(len(deck.cards))]
            base = str(req.base_url).rstrip("/")
            return admin_response(req, HTMLResponse(_env.get_template("admin.html").render(
                page="deck", row=row, deck=deck, board=board, totals=totals, peak=max(totals + [1]),
                base=base, hint=lambda e: follow_up_hint(e, deck),
            )))

    async def preview(req: Request) -> Response:
        if not is_admin(req):
            return HTMLResponse("Forbidden", status_code=403)
        with sf() as s:
            row = s.get(DeckRow, int(req.path_params["deck_id"]))
            if not row:
                return HTMLResponse("Not found", status_code=404)
            deck, facts, brand = load_published(row)
            return HTMLResponse(render_html(deck, facts, brand))

    async def pptx(req: Request) -> Response:
        if not is_admin(req):
            return HTMLResponse("Forbidden", status_code=403)
        with sf() as s:
            row = s.get(DeckRow, int(req.path_params["deck_id"]))
            if not row:
                return HTMLResponse("Not found", status_code=404)
            deck, facts, brand = load_published(row)
        with tempfile.TemporaryDirectory() as tmp:
            path = export_pptx(deck, facts, Path(tmp) / "deck.pptx", brand)
            data = path.read_bytes()
        name = re.sub(r"[^\w-]+", "-", deck.title).strip("-")[:60] or "deck"
        return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                 headers={"content-disposition": f'attachment; filename="{name}.pptx"'})

    async def health(_: Request) -> Response:
        return JSONResponse({"ok": True})

    return Starlette(routes=[
        Route("/d/{token}", view, methods=["GET", "POST"]),
        Route("/api/beacon", beacon, methods=["POST"]),
        Route("/admin", admin),
        Route("/admin/decks/{deck_id:int}", admin_deck),
        Route("/admin/decks/{deck_id:int}/preview", preview),
        Route("/admin/decks/{deck_id:int}/pptx", pptx),
        Route("/healthz", health),
        Route("/", lambda r: RedirectResponse("/admin")),
    ])
