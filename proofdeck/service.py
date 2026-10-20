"""Publishing and sharing: the glue between generation, storage and tracking."""
from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.orm import Session

from .facts import Fact, FactLibrary
from .render import Brand
from .schema import Deck
from .store import DeckRow, Link


def facts_to_dict(facts: FactLibrary) -> dict:
    return {
        "company": facts.company,
        "tagline": facts.tagline,
        "facts": [asdict(f) for f in facts.facts.values()],
    }


def publish(session: Session, deck: Deck, facts: FactLibrary, brand: Brand | None = None) -> DeckRow:
    row = DeckRow(title=deck.title, mode=deck.mode, data=deck.to_dict(), facts=facts_to_dict(facts),
                  brand=asdict(brand or Brand(name=deck.company)))
    session.add(row)
    session.commit()
    return row


def load_published(row: DeckRow) -> tuple[Deck, FactLibrary, Brand]:
    facts = FactLibrary(
        company=row.facts.get("company", ""),
        tagline=row.facts.get("tagline", ""),
        facts={f["id"]: Fact(**f) for f in row.facts.get("facts", [])},
    )
    return Deck.from_dict(row.data), facts, Brand(**(row.brand or {}))


def share(session: Session, row: DeckRow, recipients: list[dict], *, email_gate: bool = False) -> list[Link]:
    links = []
    for r in recipients:
        name = (r.get("name") or r.get("recipient") or "").strip()
        if not name:
            continue
        link = Link(deck_id=row.id, recipient=name, email=(r.get("email") or None),
                    company=(r.get("company") or r.get("firm") or None), email_gate=email_gate)
        session.add(link)
        links.append(link)
    session.commit()
    return links


def read_recipients(path: str | Path) -> list[dict]:
    with open(path, newline="") as f:
        return [{k.strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]
