"""proofdeck — command line.

  proofdeck demo                         # the whole loop on example data, no keys needed
  proofdeck build FACTS CONTEXT [-o out] # generate + validate -> deck.json, deck.html, deck.pptx
  proofdeck share DECK.json FACTS RECIPIENTS.csv [--gate] [--base-url URL]
  proofdeck serve [--port 8000]
  proofdeck report DECK_ID
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

from .export_pptx import export_pptx
from .facts import FactLibrary
from .generate import Context, Result, TemplateGenerator, default_generator
from .render import Brand, render_html
from .schema import Deck

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"


def _report(result: Result) -> None:
    if result.issues_found:
        print(f"Grounding gate: {len(result.issues_found)} issue(s) found in the first draft")
        for i in result.issues_found:
            print(f"  · {i}")
    if result.dropped:
        print(f"Removed {len(result.dropped)} line(s) that still failed:")
        for i in result.dropped:
            print(f"  · {i}")
    if not (result.issues_found or result.dropped):
        print("Grounding gate: every number is backed by a cited fact ✓")


def build(facts_path, context_path, out_dir="out", brand_path=None, generator=None) -> tuple[Deck, FactLibrary]:
    facts = FactLibrary.load(facts_path)
    ctx = Context.load(context_path)
    result = (generator or default_generator()).generate(facts, ctx)
    _report(result)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    brand = Brand.load(brand_path) if brand_path else Brand(name=facts.company)
    (out / "deck.json").write_text(json.dumps(result.deck.to_dict(), indent=2, ensure_ascii=False))
    (out / "deck.html").write_text(render_html(result.deck, facts, brand))
    export_pptx(result.deck, facts, out / "deck.pptx", brand)
    print(f"Wrote {out}/deck.json, deck.html, deck.pptx ({len(result.deck.cards)} cards)")
    return result.deck, facts


def _print_board(session, row) -> None:
    from .service import load_published
    from .tracking import follow_up_hint, leaderboard

    deck, _, _ = load_published(row)
    print(f"\nWho to follow up with — “{deck.title}”")
    print(f"{'':2}{'recipient':<34}{'score':>6}{'read':>7}{'time':>8}   signals")
    for e in leaderboard(session, row):
        sig = []
        if e.viewers == 0:
            sig.append("not opened")
        if e.forwarded:
            sig.append(f"forwarded ({e.viewers} viewers)")
        if e.sessions > e.viewers:
            sig.append("came back")
        sig += [f"🔥 {h}" for h in e.hot]
        who = e.link.recipient + (f", {e.link.company}" if e.link.company else "")
        print(f"  {who:<34}{e.score:>6.0f}{e.cards_seen:>4}/{e.cards_total:<2}{e.seconds // 60:>4}m{e.seconds % 60:02d}s   {', '.join(sig)}")
        print(f"  {'':<34}→ {follow_up_hint(e, deck)}")


def demo(out_dir: str = "out") -> None:
    from .alerts import ConsoleNotifier
    from .service import publish, read_recipients, share
    from .store import make_session_factory, utcnow
    from .tracking import record

    bar = "─" * 72
    print(f"{bar}\n1. Build a fundraising deck from facts (offline generator)\n{bar}")
    deck, facts = build(EXAMPLES / "founder/facts.yaml", EXAMPLES / "founder/context.yaml",
                        out_dir, EXAMPLES / "brand.yaml", TemplateGenerator())

    print(f"\n{bar}\n2. The gate in action: a draft that invents a number\n{bar}")
    from .schema import Bullet
    from .validate import validate

    bad = Deck.from_dict(deck.to_dict())
    traction = next(c for c in bad.cards if c.type == "traction")
    traction.bullets.append(Bullet("$2M ARR expected by March", ["arr"]))
    for issue in validate(bad, facts):
        print(f"  ✗ {issue}")

    db = Path(out_dir) / "demo.db"
    db.unlink(missing_ok=True)
    sf = make_session_factory(f"sqlite:///{db}")
    notifier = ConsoleNotifier()
    with sf() as s:
        row = publish(s, deck, facts, Brand.load(EXAMPLES / "brand.yaml"))
        links = share(s, row, read_recipients(EXAMPLES / "founder/investors.csv"))
        print(f"\n{bar}\n3. Shared with {len(links)} investors, one tracked link each\n{bar}")
        for link in links:
            print(f"  {link.recipient:<16} /d/{link.token}")

        print(f"\n{bar}\n4. A week of (simulated) reading → live alerts\n{bar}")
        t0 = utcnow() - timedelta(days=6)
        n = len(deck.cards)
        idx = {c.type: i for i, c in enumerate(deck.cards)}
        mac, iphone = "Mozilla/5.0 (Macintosh; Mac OS X) Chrome/130", "Mozilla/5.0 (iPhone) Safari/18"

        def read(link, vid, ua, ip, at, secs):
            alerts = record(s, link.token, vid, [{"card": i, "ms": ms * 1000} for i, ms in secs.items()],
                            user_agent=ua, ip=ip, now=at)
            for a in alerts:
                notifier.send(f"  [{at:%a %H:%M}] {a.message}")

        full = {i: 12 for i in range(n)}
        # Priya reads everything, lingers on traction, forwards to a partner, comes back two days later.
        read(links[0], "v1", mac, "103.21.4.10", t0, {**full, idx["traction"]: 70, idx["ask"]: 30})
        read(links[0], "v1b", iphone, "49.36.88.2", t0 + timedelta(hours=5), {idx["traction"]: 40, idx["team"]: 25})
        read(links[0], "v1", mac, "103.21.4.10", t0 + timedelta(days=2), {idx["ask"]: 20, idx["proof"]: 15})
        # Daniel reads it properly once.
        read(links[1], "v2", mac, "8.8.4.4", t0 + timedelta(days=1), {**full, idx["proof"]: 50})
        # Meera skims the first three cards.
        read(links[2], "v3", iphone, "117.55.2.9", t0 + timedelta(days=1, hours=3), {0: 4, 1: 6, 2: 3})
        # Sam opens on a phone, clears cookies, reopens on the same network: same person, not a forward.
        read(links[3], "v4", iphone, "72.14.1.20", t0 + timedelta(days=3), {0: 5, 1: 8})
        read(links[3], "v4-new", iphone, "72.14.1.77", t0 + timedelta(days=3, minutes=10), {idx["traction"]: 18})
        # Arjun and Lena never open it.

        _print_board(s, row)
    print(f"\nOpen {out_dir}/deck.html and {out_dir}/deck.pptx to see the deck.")
    print(f"See it live: proofdeck serve --db sqlite:///{db}  →  http://localhost:8000/admin?key=demo")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="proofdeck", description="Decks that can't make things up, and tell you who read them.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the whole loop on example data")
    d.add_argument("-o", "--out", default="out")
    b = sub.add_parser("build", help="generate a deck from facts + context")
    b.add_argument("facts")
    b.add_argument("context")
    b.add_argument("-o", "--out", default="out")
    b.add_argument("--brand")
    b.add_argument("--offline", action="store_true", help="use the template generator even if ANTHROPIC_API_KEY is set")
    sh = sub.add_parser("share", help="publish a deck and create one tracked link per recipient")
    sh.add_argument("deck")
    sh.add_argument("facts")
    sh.add_argument("recipients")
    sh.add_argument("--brand")
    sh.add_argument("--gate", action="store_true", help="ask for an email before showing the deck")
    sh.add_argument("--base-url", default=os.getenv("PROOFDECK_BASE_URL", "http://localhost:8000"))
    sh.add_argument("--db")
    sv = sub.add_parser("serve", help="run the viewer + dashboard")
    sv.add_argument("--port", type=int, default=int(os.getenv("PORT", 8000)))
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--db")
    r = sub.add_parser("report", help="print the follow-up ranking for a deck")
    r.add_argument("deck_id", type=int)
    r.add_argument("--db")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.cmd == "serve" else logging.WARNING)

    if args.cmd == "demo":
        demo(args.out)
    elif args.cmd == "build":
        build(args.facts, args.context, args.out, args.brand, TemplateGenerator() if args.offline else None)
    elif args.cmd == "share":
        from .service import publish, read_recipients, share
        from .store import make_session_factory

        facts = FactLibrary.load(args.facts)
        deck = Deck.from_dict(json.loads(Path(args.deck).read_text()))
        with make_session_factory(args.db)() as s:
            row = publish(s, deck, facts, Brand.load(args.brand) if args.brand else None)
            links = share(s, row, read_recipients(args.recipients), email_gate=args.gate)
            print(f"Deck #{row.id} shared with {len(links)} recipients:")
            for link in links:
                print(f"  {link.recipient:<24} {args.base_url.rstrip('/')}/d/{link.token}")
    elif args.cmd == "serve":
        import uvicorn

        from .server import create_app
        from .store import make_session_factory

        key = os.getenv("PROOFDECK_ADMIN_KEY") or ("demo" if args.db and "demo.db" in args.db else None)
        app = create_app(make_session_factory(args.db), admin_key=key)
        print(f"Dashboard: http://{args.host}:{args.port}/admin?key={key or '<see log>'}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    elif args.cmd == "report":
        from .store import DeckRow, make_session_factory

        with make_session_factory(args.db)() as s:
            row = s.get(DeckRow, args.deck_id)
            if not row:
                print(f"No deck #{args.deck_id}")
                return 1
            _print_board(s, row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
