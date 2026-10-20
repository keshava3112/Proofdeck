"""Beacons in, intelligence out: dwell per card, forwards, returns, hot cards, scores.

Rules (tested in tests/test_tracking.py):
  T1  A visitor is (link, cookie). Same browser on the same link = same visit.
  T2  A cookie we haven't seen, but with the same fingerprint (UA family + /24
      network) as an existing visit, is the same person who cleared cookies:
      merged, not a forward.
  T3  A new cookie with a new fingerprint on a link that already had a visitor
      = forwarded to someone new. Alert once per new visitor.
  T4  A session after a gap of 12h+ = came back. Alert once per day.
  T5  Lingering 45s+ (cumulative) on a hot card (pricing, traction, ask...)
      = hot card alert, once per card per link.
  T6  Beacon ms per event is clamped (max 10 min) so a tab left open can't
      inflate engagement.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .schema import HOT_CARDS, Deck
from .store import Alert, CardTime, DeckRow, Link, Visit, utcnow

HOT_MS = 45_000
MAX_EVENT_MS = 10 * 60_000
RETURN_GAP = timedelta(hours=12)


def fingerprint(user_agent: str, ip: str) -> str:
    ua = (user_agent or "").lower()
    family = next((b for b in ("edg", "chrome", "firefox", "safari") if b in ua), "other")
    os_ = next((o for o in ("iphone", "android", "mac os", "windows", "linux") if o in ua), "other")
    net = ".".join((ip or "").split(".")[:3]) if re.match(r"\d+\.\d+\.\d+\.\d+", ip or "") else (ip or "")[:19]
    return hashlib.sha256(f"{family}|{os_}|{net}".encode()).hexdigest()[:16]


def _alert(session: Session, link: Link, kind: str, message: str, key: str = "") -> Alert | None:
    if session.scalar(select(Alert).where(Alert.link_id == link.id, Alert.kind == kind, Alert.key == key)):
        return None
    a = Alert(link_id=link.id, kind=kind, key=key, message=message)
    session.add(a)
    session.flush()
    return a


def _who(link: Link) -> str:
    return link.recipient + (f" ({link.company})" if link.company and link.company not in link.recipient else "")


def record(
    session: Session,
    token: str,
    visitor_id: str,
    events: list[dict],
    *,
    user_agent: str = "",
    ip: str = "",
    now: datetime | None = None,
) -> list[Alert]:
    now = now or utcnow()
    link = session.scalar(select(Link).where(Link.token == token))
    if not link:
        return []
    deck = Deck.from_dict(link.deck.data)
    fp = fingerprint(user_agent, ip)
    alerts: list[Alert | None] = []

    visit = session.scalar(select(Visit).where(Visit.link_id == link.id, Visit.visitor_id == visitor_id))
    if visit is None:
        same_person = session.scalar(select(Visit).where(Visit.link_id == link.id, Visit.fingerprint == fp))  # T2
        if same_person:
            visit = same_person
        else:
            others = session.scalars(select(Visit).where(Visit.link_id == link.id)).all()
            visit = Visit(link_id=link.id, visitor_id=visitor_id, fingerprint=fp, first_seen=now, last_seen=now)
            session.add(visit)
            session.flush()
            if not others:
                alerts.append(_alert(session, link, "opened", f"👀 {_who(link)} opened “{deck.title}”"))
            else:  # T3
                alerts.append(_alert(session, link, "forwarded",
                                     f"↗️ {_who(link)}'s link was opened on a new device: probably forwarded "
                                     f"(viewer #{len(others) + 1})", key=visitor_id))
    if now - visit.last_seen >= RETURN_GAP:  # T4
        visit.sessions += 1
        alerts.append(_alert(session, link, "returned", f"🔁 {_who(link)} came back to “{deck.title}”",
                             key=now.strftime("%Y-%m-%d")))
    visit.last_seen = max(visit.last_seen, now)

    for ev in events:
        try:
            idx, ms = int(ev["card"]), int(ev["ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= idx < len(deck.cards)) or ms <= 0:
            continue
        ms = min(ms, MAX_EVENT_MS)  # T6
        ct = session.scalar(select(CardTime).where(CardTime.visit_id == visit.id, CardTime.card == idx))
        if ct is None:
            ct = CardTime(visit_id=visit.id, card=idx, ms=0)
            session.add(ct)
        ct.ms += ms
        session.flush()
        card = deck.cards[idx]
        if card.type in HOT_CARDS:  # T5
            total = sum(
                c.ms for c in session.scalars(
                    select(CardTime).join(Visit).where(Visit.link_id == link.id, CardTime.card == idx)
                )
            )
            if total >= HOT_MS:
                alerts.append(_alert(session, link, "hot_card",
                                     f"🔥 {_who(link)} spent {total // 1000}s on “{card.heading}” ({card.type.replace('_', ' ')})",
                                     key=str(idx)))
    session.commit()
    return [a for a in alerts if a]


# ------------------------------------------------------------- reporting
@dataclass
class Engagement:
    link: Link
    viewers: int
    seconds: int
    cards_seen: int
    cards_total: int
    sessions: int
    per_card: list[int]  # seconds per card, summed across viewers
    hot: list[str]
    score: float

    @property
    def forwarded(self) -> bool:
        return self.viewers > 1


def engagement(session: Session, link: Link) -> Engagement:
    deck = Deck.from_dict(link.deck.data)
    per_card = [0] * len(deck.cards)
    visits = session.scalars(select(Visit).where(Visit.link_id == link.id)).all()
    for v in visits:
        for ct in session.scalars(select(CardTime).where(CardTime.visit_id == v.id)):
            if ct.card < len(per_card):
                per_card[ct.card] += ct.ms // 1000
    seconds = sum(per_card)
    seen = sum(1 for s in per_card if s >= 2)
    hot = [deck.cards[i].type for i, s in enumerate(per_card) if s * 1000 >= HOT_MS and deck.cards[i].type in HOT_CARDS]
    sessions = sum(v.sessions for v in visits)
    # Simple, explainable score. Reading most of it, forwarding it and coming back are what predict a reply.
    score = (
        min(seconds / 60, 10) * 4
        + (seen / max(1, len(per_card))) * 25
        + max(0, len(visits) - 1) * 15
        + max(0, sessions - len(visits)) * 8
        + len(hot) * 6
    )
    return Engagement(link, len(visits), seconds, seen, len(per_card), sessions, per_card, hot, round(score, 1))


def leaderboard(session: Session, deck_row: DeckRow) -> list[Engagement]:
    rows = [engagement(session, link) for link in deck_row.links]
    return sorted(rows, key=lambda e: -e.score)


def follow_up_hint(e: Engagement, deck: Deck) -> str:
    if e.viewers == 0:
        return "Not opened yet: a short, personal nudge."
    if e.forwarded:
        return "Forwarded internally: ask who else is involved and offer to walk them through it."
    if e.hot:
        top = max(range(len(e.per_card)), key=lambda i: e.per_card[i])
        return f"Most time on “{deck.cards[top].heading}”: lead your follow-up with that."
    if e.cards_seen < e.cards_total / 2:
        return "Skimmed: send the one card that matters most, not the whole deck again."
    return "Read it through: propose a concrete next step."
