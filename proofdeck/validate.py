"""The grounding gate. A deck ships only if every number is backed by a fact it cites.

Rules (each tested in tests/test_validate.py):
  G1  Every cited id must exist in the facts library.
  G2  Every number in a bullet must appear in a fact *that bullet* cites.
  G3  Numbers in a heading must appear in a fact the card cites.
  G4  Small counts (0-10) and years need no citation.
  G5  Card types must be known.
"""
from __future__ import annotations

from dataclasses import dataclass

from .facts import FactLibrary, is_exempt, numbers_in
from .schema import CARD_TYPES, Bullet, Card, Deck


@dataclass
class Issue:
    card: int
    where: str  # "heading" | "bullet 2" | "card"
    rule: str
    message: str

    def __str__(self) -> str:
        return f"card {self.card} {self.where}: [{self.rule}] {self.message}"


def _ungrounded(text: str, cites: list[str], facts: FactLibrary) -> set[str]:
    allowed: set[str] = set()
    for c in cites:
        if c in facts.facts:
            allowed |= facts.facts[c].numbers
    return {n for n in numbers_in(text) if not is_exempt(n) and n not in allowed}


def validate(deck: Deck, facts: FactLibrary) -> list[Issue]:
    issues: list[Issue] = []
    for i, card in enumerate(deck.cards):
        if card.type not in CARD_TYPES:
            issues.append(Issue(i, "card", "G5", f"unknown card type {card.type!r}"))
        for c in card.all_cites:
            if c not in facts.facts:
                issues.append(Issue(i, "card", "G1", f"cites unknown fact {c!r}"))
        bad = _ungrounded(card.heading, card.all_cites, facts)
        if bad:
            issues.append(Issue(i, "heading", "G3", f"numbers {sorted(bad)} are not in any cited fact"))
        for j, b in enumerate(card.bullets):
            bad = _ungrounded(b.text, b.cites, facts)
            if bad:
                issues.append(Issue(i, f"bullet {j}", "G2", f"numbers {sorted(bad)} are not in its cited facts {b.cites}"))
    return issues


def sanitize(deck: Deck, facts: FactLibrary) -> tuple[Deck, list[Issue]]:
    """Last line of defence: drop whatever fails the gate rather than ship it."""
    dropped: list[Issue] = []
    cards: list[Card] = []
    for i, card in enumerate(deck.cards):
        if card.type not in CARD_TYPES:
            dropped.append(Issue(i, "card", "G5", f"dropped card of unknown type {card.type!r}"))
            continue
        keep: list[Bullet] = []
        for j, b in enumerate(card.bullets):
            b.cites = [c for c in b.cites if c in facts.facts]
            bad = _ungrounded(b.text, b.cites, facts)
            if bad:
                dropped.append(Issue(i, f"bullet {j}", "G2", f"dropped {b.text!r}: ungrounded {sorted(bad)}"))
            else:
                keep.append(b)
        card.bullets = keep
        card.cites = [c for c in card.cites if c in facts.facts]
        if _ungrounded(card.heading, card.all_cites, facts):
            dropped.append(Issue(i, "heading", "G3", f"heading {card.heading!r} replaced: ungrounded number"))
            card.heading = card.type.replace("_", " ").title()
        cards.append(card)
    deck.cards = cards
    return deck, dropped
