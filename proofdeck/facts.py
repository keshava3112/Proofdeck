"""The facts library: the only place numbers and claims are allowed to come from.

facts.yaml
----------
    company: Acme
    facts:
      - id: arr
        kind: metric            # metric | price | case_study | claim | team | ask | plan | quote
        text: "$1.2M ARR, growing 18% month over month"
        source: "Stripe dashboard, Sep 2026"
        tags: [traction]

A deck may only state a number that appears in a fact it cites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KINDS = {"metric", "price", "case_study", "claim", "team", "ask", "plan", "quote", "problem", "solution"}

# $2.4M, ₹40L, 38%, 3x, 1,200, 0.5, 12k, 2 weeks -> "2"
NUMBER = re.compile(
    r"(?<![\w.])[$₹€£]?\s?\d[\d,]*(?:\.\d+)?\s?(?:%|x|k|m|mn|bn|b|cr|l|lakh|crore|million|billion)?(?![\w])",
    re.I,
)
SUFFIX_ALIASES = {"mn": "m", "million": "m", "bn": "b", "billion": "b", "lakh": "l", "crore": "cr"}


def normalize_number(token: str) -> str:
    t = token.lower().replace(",", "").replace(" ", "")
    t = t.lstrip("$₹€£")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(%|x|k|m|mn|bn|b|cr|l|lakh|crore|million|billion)?", t)
    if not m:
        return t
    num, suf = m.group(1), m.group(2) or ""
    if "." in num:
        num = num.rstrip("0").rstrip(".")
    return num + SUFFIX_ALIASES.get(suf, suf)


def numbers_in(text: str) -> set[str]:
    return {normalize_number(m.group(0)) for m in NUMBER.finditer(text or "")}


def is_exempt(n: str) -> bool:
    """Small counts ("3 steps", "Week 2") and years ("since 2019") need no citation."""
    if re.fullmatch(r"\d", n) or n == "10":
        return True
    return bool(re.fullmatch(r"(19[9]\d|20\d\d|2100)", n))


@dataclass
class Fact:
    id: str
    kind: str
    text: str
    source: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def numbers(self) -> set[str]:
        return numbers_in(self.text)


@dataclass
class FactLibrary:
    company: str
    facts: dict[str, Fact]
    tagline: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "FactLibrary":
        data = yaml.safe_load(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "FactLibrary":
        facts: dict[str, Fact] = {}
        for raw in data.get("facts", []):
            f = Fact(
                id=str(raw["id"]),
                kind=raw.get("kind", "claim"),
                text=str(raw["text"]).strip(),
                source=raw.get("source", ""),
                tags=list(raw.get("tags", [])),
            )
            if f.kind not in KINDS:
                raise ValueError(f"fact {f.id}: unknown kind {f.kind!r} (use one of {sorted(KINDS)})")
            if f.id in facts:
                raise ValueError(f"duplicate fact id {f.id!r}")
            facts[f.id] = f
        return cls(company=data.get("company", ""), facts=facts, tagline=data.get("tagline", ""))

    def by_kind(self, *kinds: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.kind in kinds]

    def with_tags(self, tags: set[str], *kinds: str) -> list[Fact]:
        pool = self.by_kind(*kinds) if kinds else list(self.facts.values())
        return sorted(pool, key=lambda f: -len(tags & set(f.tags)))

    def add(self, fact: Fact) -> None:
        self.facts[fact.id] = fact

    def for_prompt(self) -> str:
        return "\n".join(f"[{f.id}] ({f.kind}) {f.text}  — source: {f.source or 'n/a'}" for f in self.facts.values())
