"""Turn (facts, context) into a Deck.

context.yaml (founder)              context.yaml (sales, e.g. after a discovery call)
---------------------               ------------------------------------------------
mode: founder                       mode: sales
audience: seed investors            recipient: {name: Meera, company: Juniper Foods,
                                                role: COO, industry: food}
                                    quotes:
                                      - {speaker: Meera, text: "We re-key every order by hand."}
                                    goal: "Agree a two-week pilot with the ops team."

Quotes and the goal become facts too, so the prospect's own words are citable.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from .facts import Fact, FactLibrary
from .schema import CARD_TYPES, FOUNDER_CARDS, SALES_CARDS, Bullet, Card, Deck
from .validate import Issue, sanitize, validate

log = logging.getLogger(__name__)


@dataclass
class Context:
    mode: str = "founder"
    audience: str = ""
    recipient: dict = field(default_factory=dict)
    quotes: list[dict] = field(default_factory=list)
    goal: str = ""
    source: str = "discovery call"

    @classmethod
    def load(cls, path: str | Path) -> "Context":
        return cls(**(yaml.safe_load(Path(path).read_text()) or {}))

    @property
    def tags(self) -> set[str]:
        r = self.recipient
        return {t.lower() for t in [r.get("industry", ""), *r.get("tags", [])] if t}

    def merge_into(self, facts: FactLibrary) -> FactLibrary:
        for i, q in enumerate(self.quotes, 1):
            facts.add(Fact(id=f"q{i}", kind="quote", text=q["text"], source=f"{q.get('speaker', '')}, {self.source}".strip(", ")))
        if self.goal:
            facts.add(Fact(id="goal", kind="plan", text=self.goal, source=self.source))
        return facts


@dataclass
class Result:
    deck: Deck
    issues_found: list[Issue] = field(default_factory=list)  # before repair/sanitize
    dropped: list[Issue] = field(default_factory=list)  # removed to ship clean


class Generator(Protocol):
    def generate(self, facts: FactLibrary, ctx: Context) -> Result: ...


def _bullets(facts: list[Fact], limit: int = 4) -> list[Bullet]:
    return [Bullet(text=f.text, cites=[f.id]) for f in facts[:limit]]


class TemplateGenerator:
    """Deterministic, offline. Lays facts into the canonical card order."""

    def generate(self, facts: FactLibrary, ctx: Context) -> Result:
        ctx.merge_into(facts)
        r = ctx.recipient
        cards: list[Card] = []
        if ctx.mode == "sales":
            who = r.get("company", "you")
            cards.append(Card("title", f"{facts.company} × {who}",
                              [Bullet(f"Prepared for {r.get('name', who)}{', ' + r['role'] if r.get('role') else ''}")]))
            quotes = facts.by_kind("quote")
            if quotes:
                cards.append(Card("their_words", "What we heard from you",
                                  [Bullet(f"“{q.text}” — {q.source.split(',')[0]}", [q.id]) for q in quotes[:4]]))
            cards.append(Card("solution", "How we solve it", _bullets(facts.with_tags(ctx.tags, "solution"), 3)))
            proof = [f for f in facts.with_tags(ctx.tags, "case_study")][:2]
            cards.append(Card("proof", "Teams like yours", _bullets(proof, 2)))
            cards.append(Card("pricing", "Pricing", _bullets(facts.by_kind("price"), 4)))
            plan = [f for f in facts.by_kind("plan") if f.id != "goal"]
            cards.append(Card("plan", "Mutual action plan", _bullets(plan, 5)))
            if "goal" in facts.facts:
                cards.append(Card("next_step", "Proposed next step", _bullets([facts.facts["goal"]], 1)))
        else:
            tagline = facts.tagline or ""
            cards.append(Card("title", facts.company, [Bullet(tagline)] if tagline else []))
            for kind, heading in [("problem", "The problem"), ("solution", "Our solution"),
                                  ("metric", "Traction"), ("case_study", "Customer proof"),
                                  ("team", "Team"), ("ask", "The ask")]:
                pool = facts.by_kind(kind)
                if kind == "metric":
                    pool = [f for f in pool if "market" not in f.tags]
                if pool:
                    ctype = {"metric": "traction", "case_study": "proof"}.get(kind, kind)
                    cards.append(Card(ctype, heading, _bullets(pool, 4)))
            market = [f for f in facts.by_kind("claim", "metric") if "market" in f.tags]
            if market:
                cards.insert(len(cards) - 2 if len(cards) > 3 else len(cards), Card("market", "Market", _bullets(market, 3)))
        deck = Deck(
            title=cards[0].heading if cards else facts.company,
            mode=ctx.mode,
            company=facts.company,
            recipient=r.get("company", "") or r.get("name", ""),
            cards=[c for c in cards if c.bullets or c.type == "title"],
        )
        issues = validate(deck, facts)
        deck, dropped = sanitize(deck, facts)
        return Result(deck, issues, dropped)


# ------------------------------------------------------------------- LLM
TOOL = {
    "name": "write_deck",
    "description": "Write the deck as typed cards made of cited bullets.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": CARD_TYPES},
                        "heading": {"type": "string"},
                        "cites": {"type": "array", "items": {"type": "string"}},
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "cites": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["text", "cites"],
                            },
                        },
                        "notes": {"type": "string", "description": "Speaker notes"},
                    },
                    "required": ["type", "heading", "bullets"],
                },
            },
        },
        "required": ["title", "cards"],
    },
}

SYSTEM = """You write {mode} decks that are specific, short and true.

Hard rules:
- Use ONLY the facts provided. Every bullet lists the fact ids it relies on in `cites`.
- Never write a number (amount, %, multiple, count, date) unless it appears in a fact that bullet cites.
  If you want a number that isn't in the facts, leave it out.
- Bullets are one line each, at most 4 per card. Headings are a claim, not a label, when the facts support one.
- Card order for this mode: {order}. Skip a card if no facts support it.
{mode_rules}"""

MODE_RULES = {
    "sales": "- Open with the prospect's own words (quote facts, verbatim, in quotation marks).\n"
             "- Choose case studies closest to the recipient's industry.\n"
             "- End with the proposed next step.",
    "founder": "- Lead traction with the strongest metric. Keep the ask concrete.",
}


class LLMGenerator:
    def __init__(self, client=None, model: str | None = None, max_repairs: int = 1):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.getenv("PROOFDECK_MODEL", "claude-sonnet-5-5")
        self.max_repairs = max_repairs

    def _call(self, system: str, messages: list[dict]) -> tuple[dict, object]:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "write_deck"},
            messages=messages,
        )
        block = next(b for b in resp.content if getattr(b, "type", "") == "tool_use")
        data = block.input if isinstance(block.input, dict) else json.loads(block.input)
        return data, block

    def generate(self, facts: FactLibrary, ctx: Context) -> Result:
        ctx.merge_into(facts)
        order = SALES_CARDS if ctx.mode == "sales" else FOUNDER_CARDS
        system = SYSTEM.format(mode=ctx.mode, order=", ".join(order), mode_rules=MODE_RULES.get(ctx.mode, ""))
        brief = {
            "company": facts.company,
            "tagline": facts.tagline,
            "audience": ctx.audience,
            "recipient": ctx.recipient,
            "goal": ctx.goal,
        }
        user = f"<brief>{json.dumps(brief, ensure_ascii=False)}</brief>\n<facts>\n{facts.for_prompt()}\n</facts>"
        messages: list[dict] = [{"role": "user", "content": user}]
        data, block = self._call(system, messages)
        deck = self._to_deck(data, facts, ctx)
        first_issues = validate(deck, facts)
        issues = first_issues
        for _ in range(self.max_repairs):
            if not issues:
                break
            log.info("repairing %d issues", len(issues))
            messages += [
                {"role": "assistant", "content": [{
                    "type": "tool_use", "id": block.id, "name": block.name, "input": data,
                }]},
                {"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "The deck failed validation. Fix these and call write_deck again:\n"
                               + "\n".join(str(i) for i in issues),
                    "is_error": True,
                }]},
            ]
            data, block = self._call(system, messages)
            deck = self._to_deck(data, facts, ctx)
            issues = validate(deck, facts)
        deck, dropped = sanitize(deck, facts)
        return Result(deck, first_issues, dropped)

    @staticmethod
    def _to_deck(data: dict, facts: FactLibrary, ctx: Context) -> Deck:
        r = ctx.recipient
        return Deck.from_dict({
            **data,
            "mode": ctx.mode,
            "company": facts.company,
            "recipient": r.get("company", "") or r.get("name", ""),
        })


def default_generator() -> Generator:
    return LLMGenerator() if os.getenv("ANTHROPIC_API_KEY") else TemplateGenerator()
