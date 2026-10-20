# Contributing to Proofdeck

## Setup

```bash
git clone https://github.com/keshava3112/Proofdeck && cd Proofdeck
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest              # 33 tests, about 2 seconds
proofdeck demo      # the whole loop on example data
```

## Ground rules

- **Nothing reaches a recipient without passing the gate.** New generators, card
  types or import paths must run through `validate()` and `sanitize()`.
- **Every rule has a test named after it** (G1–G5 in `test_validate.py`, T1–T6 in
  `test_tracking.py`). If you change a rule, change its test and its docstring.
- **Tracking stays first-party and minimal.** No third-party scripts, and no new
  identifiers without a clear reason in the PR.
- **PPTX and HTML stay in step.** A new card type needs a layout in both
  `templates/deck.html` and `export_pptx.py`.

## Good places to start

- A new card type (timeline, comparison, team grid) in both renderers
- A transcript importer (`.vtt`, Fireflies or Gong export) that produces a `call.yaml`
- A Slack Block Kit version of the alerts
- Live metric facts (Stripe or Google Sheets) resolved at render time

## Regenerating the README animation

```bash
pip install playwright && playwright install chromium
python scripts/make_demo_gif.py   # needs ffmpeg
```
