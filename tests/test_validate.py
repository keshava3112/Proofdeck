import pytest

from proofdeck.facts import FactLibrary, normalize_number, numbers_in
from proofdeck.schema import Bullet, Card, Deck
from proofdeck.validate import sanitize, validate

FACTS = FactLibrary.from_dict({
    "company": "Acme",
    "facts": [
        {"id": "arr", "kind": "metric", "text": "$1.2M ARR, up from $310K", "source": "Stripe"},
        {"id": "nrr", "kind": "metric", "text": "131% net revenue retention"},
        {"id": "team", "kind": "team", "text": "Founder ran a 600-truck fleet"},
    ],
})


def deck(*cards):
    return Deck(title="t", mode="founder", company="Acme", cards=list(cards))


def test_normalization_equates_formats():
    assert normalize_number("$1.2M") == normalize_number("1.2 m") == "1.2m"
    assert normalize_number("1,200") == "1200"
    assert normalize_number("2.50") == "2.5"
    assert normalize_number("40 lakh") == "40l"
    assert numbers_in("Grew 3x to $1.2M in 2025") == {"3x", "1.2m", "2025"}


def test_g2_grounded_bullet_passes():
    assert validate(deck(Card("traction", "Traction", [Bullet("$1.2M ARR", ["arr"])])), FACTS) == []


def test_g2_invented_number_fails():
    issues = validate(deck(Card("traction", "Traction", [Bullet("$2M ARR by March", ["arr"])])), FACTS)
    assert [i.rule for i in issues] == ["G2"]


def test_g2_number_must_be_in_the_bullets_own_cites():
    # 131% exists in the library, but this bullet cites a different fact
    issues = validate(deck(Card("traction", "T", [Bullet("131% retention", ["arr"])])), FACTS)
    assert issues and issues[0].rule == "G2"


def test_g1_unknown_citation():
    issues = validate(deck(Card("traction", "T", [Bullet("Strong growth", ["nope"])])), FACTS)
    assert [i.rule for i in issues] == ["G1"]


def test_g3_heading_numbers_need_card_cites():
    bad = validate(deck(Card("traction", "We hit $5M", [Bullet("$1.2M ARR", ["arr"])])), FACTS)
    assert any(i.rule == "G3" for i in bad)
    ok = validate(deck(Card("traction", "$1.2M ARR and climbing", [Bullet("131% NRR", ["nrr"])], cites=["arr"])), FACTS)
    assert ok == []


def test_g4_small_counts_and_years_are_exempt():
    assert validate(deck(Card("plan", "Plan", [Bullet("3 steps, starting in 2027")])), FACTS) == []


def test_g5_unknown_card_type():
    assert [i.rule for i in validate(deck(Card("vibes", "x")), FACTS)] == ["G5"]


def test_sanitize_drops_only_what_fails():
    d = deck(Card("traction", "Up to $9M", [Bullet("$1.2M ARR", ["arr"]), Bullet("$9M pipeline", ["arr"])]))
    clean, dropped = sanitize(d, FACTS)
    assert [b.text for b in clean.cards[0].bullets] == ["$1.2M ARR"]
    assert clean.cards[0].heading == "Traction"
    assert validate(clean, FACTS) == []
    assert len(dropped) == 2


def test_facts_reject_unknown_kind_and_duplicates():
    with pytest.raises(ValueError):
        FactLibrary.from_dict({"facts": [{"id": "a", "kind": "rumour", "text": "x"}]})
    with pytest.raises(ValueError):
        FactLibrary.from_dict({"facts": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]})
