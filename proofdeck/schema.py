"""A deck is typed, structured data: cards of known types made of cited bullets.

Typed cards (instead of a freeform canvas) are what make the output brand-safe,
validatable, and exportable to PPTX without loss.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

FOUNDER_CARDS = ["title", "problem", "solution", "traction", "proof", "market", "team", "ask"]
SALES_CARDS = ["title", "their_words", "solution", "proof", "pricing", "plan", "next_step"]
CARD_TYPES = sorted(set(FOUNDER_CARDS + SALES_CARDS))
# Cards worth an alert when someone lingers on them.
HOT_CARDS = {"traction", "pricing", "ask", "proof", "plan"}


@dataclass
class Bullet:
    text: str
    cites: list[str] = field(default_factory=list)


@dataclass
class Card:
    type: str
    heading: str
    bullets: list[Bullet] = field(default_factory=list)
    cites: list[str] = field(default_factory=list)  # for numbers in the heading
    notes: str = ""  # speaker notes

    @property
    def all_cites(self) -> list[str]:
        seen: list[str] = []
        for c in self.cites + [c for b in self.bullets for c in b.cites]:
            if c not in seen:
                seen.append(c)
        return seen


@dataclass
class Deck:
    title: str
    mode: str  # founder | sales
    company: str
    recipient: str = ""
    cards: list[Card] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Deck":
        cards = [
            Card(
                type=c["type"],
                heading=c["heading"],
                bullets=[Bullet(text=b["text"], cites=list(b.get("cites", []))) for b in c.get("bullets", [])],
                cites=list(c.get("cites", [])),
                notes=c.get("notes", ""),
            )
            for c in d.get("cards", [])
        ]
        return cls(
            title=d["title"],
            mode=d.get("mode", "founder"),
            company=d.get("company", ""),
            recipient=d.get("recipient", ""),
            cards=cards,
        )
