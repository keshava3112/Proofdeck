"""HTML rendering (the viewer) with brand tokens from brand.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, PackageLoader, select_autoescape

from .facts import FactLibrary
from .schema import Deck


@dataclass
class Brand:
    name: str = ""
    primary: str = "#1f2328"
    accent: str = "#2f5bd3"
    background: str = "#faf9f6"
    text: str = "#1d1c1d"
    muted: str = "#6b6a65"
    font: str = "Inter"
    logo_url: str = ""

    @classmethod
    def load(cls, path: str | Path | None) -> "Brand":
        if not path or not Path(path).exists():
            return cls()
        return cls(**(yaml.safe_load(Path(path).read_text()) or {}))


STAT = re.compile(
    r"^\s*([$₹€£]?\d[\d,]*(?:\.\d+)?(?:%|\s?(?:x|k|m|bn|b|cr|l|lakh|crore|million|billion)\b|-[a-z]+)?)",
    re.I,
)


def stat_split(text: str) -> tuple[str, str]:
    """'$1.2M ARR, up 18% MoM' -> ('$1.2M', 'ARR, up 18% MoM'); '9-point drop' -> ('9-point', 'drop')."""
    m = STAT.match(text)
    if not m or re.fullmatch(r"\d", m.group(1)):  # "3 pilots" is not a headline stat
        return "", text
    return m.group(1).strip(), text[m.end():].lstrip(" ,—-:")


_env = Environment(loader=PackageLoader("proofdeck", "templates"), autoescape=select_autoescape(["html"]))
_env.filters["stat_split"] = stat_split


def render_html(deck: Deck, facts: FactLibrary, brand: Brand | None = None, *,
                token: str | None = None, beacon_url: str = "/api/beacon") -> str:
    brand = brand or Brand(name=deck.company)
    sources: list[list[tuple[int, str, str]]] = []
    numbering: dict[str, int] = {}
    for card in deck.cards:
        rows = []
        for cid in card.all_cites:
            f = facts.facts.get(cid)
            if not f:
                continue
            numbering.setdefault(cid, len(numbering) + 1)
            rows.append((numbering[cid], f.source or f.kind, f.text))
        sources.append(rows)
    return _env.get_template("deck.html").render(
        deck=deck, brand=brand, sources=sources, numbering=numbering,
        token=token, beacon_url=beacon_url,
    )
