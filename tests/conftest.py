from pathlib import Path

import pytest

from proofdeck.facts import FactLibrary
from proofdeck.generate import Context, TemplateGenerator
from proofdeck.store import make_session_factory

EX = Path(__file__).resolve().parents[1] / "proofdeck" / "examples"


@pytest.fixture
def founder_facts():
    return FactLibrary.load(EX / "founder/facts.yaml")


@pytest.fixture
def founder_deck(founder_facts):
    return TemplateGenerator().generate(founder_facts, Context.load(EX / "founder/context.yaml")).deck


@pytest.fixture
def sf(tmp_path):
    return make_session_factory(f"sqlite:///{tmp_path / 't.db'}")
