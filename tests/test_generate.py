from types import SimpleNamespace

from pptx import Presentation

from proofdeck.export_pptx import export_pptx
from proofdeck.facts import FactLibrary
from proofdeck.generate import Context, LLMGenerator, TemplateGenerator
from proofdeck.render import Brand, render_html
from proofdeck.validate import validate

from .conftest import EX


def test_founder_template_deck_is_grounded(founder_deck, founder_facts):
    assert [c.type for c in founder_deck.cards] == ["title", "problem", "solution", "traction", "proof", "market", "team", "ask"]
    assert validate(founder_deck, founder_facts) == []


def test_sales_deck_uses_their_words_and_matching_proof():
    facts = FactLibrary.load(EX / "sales/facts.yaml")
    ctx = Context.load(EX / "sales/call.yaml")
    deck = TemplateGenerator().generate(facts, ctx).deck
    types = [c.type for c in deck.cards]
    assert types[:2] == ["title", "their_words"] and types[-1] == "next_step"
    proof = next(c for c in deck.cards if c.type == "proof")
    assert "Sahyadri Cold Chain" in proof.bullets[0].text  # cold-chain + food beats construction
    assert all("Deccan" not in b.text for b in proof.bullets)
    assert deck.recipient == "Juniper Foods"
    assert validate(deck, facts) == []


class FakeClaude:
    """Returns queued tool inputs; records requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        data = self.responses.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id=f"tu{len(self.calls)}", name="write_deck", input=data)])


def card(t, heading, *bullets):
    return {"type": t, "heading": heading, "bullets": [{"text": x, "cites": c} for x, c in bullets]}


def test_llm_repair_loop_fixes_invented_number(founder_facts):
    bad = {"title": "Freightline", "cards": [card("traction", "Traction", ("$3M ARR", ["arr"]))]}
    good = {"title": "Freightline", "cards": [card("traction", "Traction", ("$1.2M ARR, up from $310K a year ago", ["arr"]))]}
    client = FakeClaude(bad, good)
    res = LLMGenerator(client=client, model="m").generate(founder_facts, Context(mode="founder"))
    assert len(client.calls) == 2
    feedback = client.calls[1]["messages"][-1]["content"][0]
    assert feedback["type"] == "tool_result" and "G2" in feedback["content"]
    assert res.issues_found and not res.dropped
    assert res.deck.cards[0].bullets[0].text.startswith("$1.2M")


def test_llm_still_wrong_after_repair_gets_sanitized(founder_facts):
    bad = {"title": "F", "cards": [card("traction", "Traction", ("$3M ARR", ["arr"]), ("131% net revenue retention", ["nrr"]))]}
    res = LLMGenerator(client=FakeClaude(bad, bad), model="m").generate(founder_facts, Context(mode="founder"))
    assert [b.text for b in res.deck.cards[0].bullets] == ["131% net revenue retention"]
    assert validate(res.deck, founder_facts) == []


def test_prompt_contains_facts_with_ids_and_rules(founder_facts):
    good = {"title": "F", "cards": [card("ask", "The ask", ("Raising $4M seed", ["ask"]))]}
    client = FakeClaude(good)
    LLMGenerator(client=client, model="m").generate(founder_facts, Context(mode="founder"))
    req = client.calls[0]
    assert "[arr] (metric) $1.2M ARR" in req["messages"][0]["content"]
    assert "Never write a number" in req["system"]
    assert req["tool_choice"] == {"type": "tool", "name": "write_deck"}


def test_html_has_sources_and_tracking_only_when_tokened(founder_deck, founder_facts):
    html = render_html(founder_deck, founder_facts, Brand(name="Freightline"))
    assert "Stripe + invoices, Sep 2026" in html and "/api/beacon" not in html
    tracked = render_html(founder_deck, founder_facts, token="abc")
    assert '"abc"' in tracked and "/api/beacon" in tracked


def test_html_escapes_fact_text():
    facts = FactLibrary.from_dict({"company": "X", "facts": [{"id": "p", "kind": "problem", "text": "<script>alert(1)</script>"}]})
    deck = TemplateGenerator().generate(facts, Context()).deck
    assert "<script>alert(1)</script>" not in render_html(deck, facts)


def test_pptx_one_slide_per_card_with_sources(founder_deck, founder_facts, tmp_path):
    path = export_pptx(founder_deck, founder_facts, tmp_path / "d.pptx")
    prs = Presentation(path)
    assert len(prs.slides) == len(founder_deck.cards)
    text = " ".join(sh.text_frame.text for sh in prs.slides[3].shapes if sh.has_text_frame)
    assert "$1.2M" in text and "Stripe + invoices" in text
