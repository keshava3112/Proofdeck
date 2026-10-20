"""Render docs/assets/demo.gif: facts → grounded deck → gate → links → alerts → ranking.

    pip install playwright && playwright install chromium
    python scripts/make_demo_gif.py          # needs ffmpeg on PATH
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "demo.gif"
W, H, FPS = 960, 540, 15

HTML = r"""
<html><head><style>
*{box-sizing:border-box}
body{margin:0;width:960px;height:540px;background:#f4f2ec;overflow:hidden;color:#1b1b1f;
  font-family:Inter,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
.panel{position:absolute;background:#fff;border:1px solid #e3e1da;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.06);overflow:hidden}
.ph{height:36px;border-bottom:1px solid #eeece6;padding:0 14px;display:flex;align-items:center;font-size:12px;font-weight:600;color:#6b6a70;gap:8px}
#facts{left:24px;top:24px;width:330px;height:420px}
#deck{left:374px;top:24px;width:562px;height:420px;background:#fbfaf7}
pre{margin:0;padding:12px 14px;font:12px/1.65 ui-monospace,Menlo,monospace;color:#3a3a40;white-space:pre-wrap}
.fl{display:block;border-radius:4px;padding:0 4px;margin:0 -4px;transition:none}
.k{color:#9a6400}.s{color:#1e7a46}
.kick{font-size:11px;font-weight:700;letter-spacing:.08em;color:#e2583e;margin:26px 26px 6px}
.h{font-size:30px;font-weight:800;color:#14213d;margin:0 26px 16px;letter-spacing:-.02em}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:0 26px}
.tile{border:1px solid #e3e1da;border-radius:12px;padding:14px 14px 12px;background:#fff;min-height:118px;position:relative}
.n{font-size:30px;font-weight:800;color:#14213d;letter-spacing:-.02em;line-height:1}
.r{font-size:12px;color:#6b6a70;margin-top:8px;line-height:1.4}
sup{font-size:10px;color:#e2583e;font-weight:700;margin-left:2px}
#bad{grid-column:1 / span 3;min-height:0;display:flex;align-items:center;gap:14px;border:2px solid #e74c3c;background:#fff5f4}
#bad .n{font-size:22px;color:#b03a2e}
#stamp{margin-left:auto;font-size:12px;font-weight:700;color:#fff;background:#c0392b;border-radius:6px;padding:5px 9px;white-space:nowrap}
.src{position:absolute;left:26px;right:26px;bottom:14px;font-size:11px;color:#6b6a70;border-top:1px solid #e7e5df;padding-top:8px}
#links,#board{position:absolute;left:374px;top:24px;width:562px;height:420px}
.row{display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid #f0eee8;font-size:14px}
.row code{margin-left:auto;font:12px ui-monospace,Menlo,monospace;color:#6b6a70;background:#f4f2ec;padding:3px 7px;border-radius:5px}
.av{width:28px;height:28px;border-radius:50%;color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
#alerts{position:absolute;left:24px;top:24px;width:330px;height:420px}
.al{margin:10px 12px 0;padding:10px 12px;background:#1f2328;color:#fff;border-radius:10px;font-size:13px;line-height:1.4}
.al small{display:block;color:#a8a7a2;font-size:11px;margin-bottom:3px;font-weight:600}
.sc{margin-left:auto;font-weight:800;font-size:18px;width:40px;text-align:right}
.tag{font-size:11px;font-weight:700;padding:2px 7px;border-radius:99px;margin-left:4px}
.fw{background:#e8eefc;color:#2f5bd3}.hot{background:#fdeee6;color:#c2410c}.no{background:#f1f0eb;color:#6b6a70}
.hint{font-size:12px;color:#6b6a70;padding:0 16px 10px 54px;margin-top:-6px;border-bottom:1px solid #f0eee8}
#board .row{border-bottom:0}
#cap{position:absolute;left:24px;top:462px;right:24px;height:50px;display:flex;align-items:center;gap:12px}
#cap .num{width:28px;height:28px;border-radius:50%;background:#14213d;color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;flex:none}
#cap .t{font-size:18px;font-weight:700;color:#14213d}
#brand{position:absolute;right:24px;top:476px;font-weight:800;font-size:16px;color:#14213d}
#brand small{font-weight:500;color:#8a8984;font-size:12px;margin-left:6px}
</style></head><body>
<div class="panel" id="facts"><div class="ph">facts.yaml</div><pre>
<span class="fl" id="f0">- id: <span class="k">arr</span>
  text: <span class="s">"$1.2M ARR, up from $310K"</span>
  source: Stripe + invoices, Sep 2026</span>
<span class="fl" id="f1">- id: <span class="k">mom</span>
  text: <span class="s">"14% month-over-month growth"</span>
  source: Stripe, Apr–Sep 2026</span>
<span class="fl" id="f2">- id: <span class="k">nrr</span>
  text: <span class="s">"131% net revenue retention"</span>
  source: Cohort analysis, Sep 2026</span>
<span class="fl">- id: <span class="k">ask</span>
  text: <span class="s">"Raising $4M seed…"</span></span></pre></div>

<div class="panel" id="alerts"><div class="ph">#fundraise · alerts</div>
  <div class="al" id="a0"><small>Tue 10:14</small>👀 Priya Menon (Banyan Capital) opened “Freightline”</div>
  <div class="al" id="a1"><small>Tue 10:19</small>🔥 Priya spent 70s on “Traction”</div>
  <div class="al" id="a2"><small>Tue 15:02</small>↗️ Priya's link opened on a new device: probably forwarded</div>
  <div class="al" id="a3"><small>Thu 09:40</small>🔁 Priya came back to “Freightline”</div>
</div>

<div class="panel" id="deck">
  <div class="kick">TRACTION</div><div class="h">Traction</div>
  <div class="tiles">
    <div class="tile" id="t0"><div class="n">$1.2M</div><div class="r">ARR, up from $310K a year ago<sup>1</sup></div></div>
    <div class="tile" id="t1"><div class="n">14%</div><div class="r">month-over-month growth<sup>2</sup></div></div>
    <div class="tile" id="t2"><div class="n">131%</div><div class="r">net revenue retention<sup>3</sup></div></div>
    <div class="tile" id="bad"><div class="n">$2M</div><div class="r" style="margin:0">ARR expected by March</div><div id="stamp">✗ not in any cited fact — removed</div></div>
  </div>
  <div class="src" id="src">1 Stripe + invoices, Sep 2026 · 2 Stripe, Apr–Sep 2026 · 3 Cohort analysis, Sep 2026</div>
</div>

<div class="panel" id="links"><div class="ph">proofdeck share deck.json facts.yaml investors.csv</div>
  <div class="row" id="l0"><div class="av" style="background:#7d5ba6">PM</div>Priya Menon · Banyan Capital<code>/d/i7dTV2Cj</code></div>
  <div class="row" id="l1"><div class="av" style="background:#2f5bd3">DO</div>Daniel Okafor · Northstar<code>/d/vFtqQy30</code></div>
  <div class="row" id="l2"><div class="av" style="background:#c2410c">MI</div>Meera Iyer · Monsoon Fund<code>/d/OlIwwJdD</code></div>
  <div class="row" id="l3"><div class="av" style="background:#1e7a46">AB</div>Arjun Bhat · Lattice VC<code>/d/z6BpiibC</code></div>
  <div class="row" id="l4"><div class="av" style="background:#6b6a70">LP</div>Lena Park · Peak Seed<code>/d/QW56UhsV</code></div>
</div>

<div class="panel" id="board"><div class="ph">Who to follow up with</div>
  <div class="row"><div class="av" style="background:#7d5ba6">PM</div><b>Priya Menon</b><span class="tag fw">forwarded</span><span class="tag hot">🔥 traction</span><span class="sc">78</span></div>
  <div class="hint">Forwarded internally: ask who else is involved.</div>
  <div class="row"><div class="av" style="background:#2f5bd3">DO</div><b>Daniel Okafor</b><span class="tag hot">🔥 proof</span><span class="sc">40</span></div>
  <div class="hint">Lead your follow-up with the customer proof.</div>
  <div class="row"><div class="av" style="background:#c2410c">MI</div><b>Meera Iyer</b><span class="sc">10</span></div>
  <div class="hint">Skimmed: send the one card that matters most.</div>
  <div class="row"><div class="av" style="background:#1e7a46">AB</div><b>Arjun Bhat</b><span class="tag no">not opened</span><span class="sc">0</span></div>
  <div class="hint">A short, personal nudge.</div>
</div>

<div id="cap"><div class="num" id="capn"></div><div class="t" id="capt"></div></div>
<div id="brand">Proofdeck<small>decks that can't make things up</small></div>
<script>
function ease(t){t=Math.max(0,Math.min(1,t));return t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2}
function op(id,p,dy=10,dx=0){const e=document.getElementById(id);const q=ease(p);e.style.opacity=q;
  e.style.transform=`translate(${(1-q)*dx}px,${(1-q)*dy}px)`;e.style.visibility=q>0?"visible":"hidden"}
window.render=function(s){
  op("facts",s.facts,0);op("deck",s.deck,0);op("links",s.links,0,30);op("alerts",s.alerts,0,-30);op("board",s.board,0,30);
  ["t0","t1","t2"].forEach((t,i)=>op(t,s["t"+i],14));
  op("bad",s.bad,14);document.getElementById("bad").style.display=s.bad>0?"flex":"none";
  op("stamp",s.stamp,0);op("src",s.t0,0);
  [0,1,2].forEach(i=>{document.getElementById("f"+i).style.background=s.hl===i?"#fff1b8":"transparent"});
  [0,1,2,3,4].forEach(i=>op("l"+i,s["l"+i],0,20));
  [0,1,2,3].forEach(i=>op("a"+i,s["a"+i],-12));
  document.getElementById("capn").textContent=s.n;document.getElementById("capt").textContent=s.cap;
};
</script></body></html>
"""

BASE = dict(facts=1, deck=1, links=0, alerts=0, board=0, t0=0, t1=0, t2=0, bad=0, stamp=0, hl=-1,
            l0=0, l1=0, l2=0, l3=0, l4=0, a0=0, a1=0, a2=0, a3=0,
            n="1", cap="Write your facts once, each with its source")


def timeline() -> list[dict]:
    frames: list[dict] = []
    s = dict(BASE)

    def hold(sec, **kw):
        s.update(kw)
        frames.extend(dict(s) for _ in range(max(1, int(sec * FPS))))

    def tween(sec, **targets):
        start = {k: s[k] for k in targets}
        n = max(1, int(sec * FPS))
        for i in range(1, n + 1):
            for k, v in targets.items():
                s[k] = start[k] + (v - start[k]) * i / n
            frames.append(dict(s))

    hold(1.2)
    hold(0.1, n="2", cap="Proofdeck writes the deck, and every number cites a fact")
    for i in range(3):
        hold(0.1, hl=i)
        tween(0.35, **{f"t{i}": 1})
        hold(0.45)
    hold(0.6, hl=-1)
    hold(0.1, n="3", cap="It won't invent one: ungrounded numbers never ship")
    tween(0.35, bad=1)
    hold(0.4)
    tween(0.25, stamp=1)
    hold(1.4)
    tween(0.35, bad=0, stamp=0)
    hold(0.5)
    hold(0.1, n="4", cap="One tracked link per investor (or per stakeholder)")
    tween(0.35, facts=0, deck=0)
    tween(0.3, links=1)
    for i in range(5):
        tween(0.18, **{f"l{i}": 1})
    hold(1.0)
    hold(0.1, n="5", cap="Know who read it, what they lingered on, who they forwarded it to")
    tween(0.3, alerts=1)
    for i in range(4):
        tween(0.3, **{f"a{i}": 1})
        hold(0.55)
    hold(0.6)
    hold(0.1, n="6", cap="Follow up with the right person, about the right slide")
    tween(0.35, links=0)
    tween(0.35, board=1)
    hold(2.6)
    return frames


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    frames = timeline()
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.set_content(HTML)
        page.wait_for_timeout(200)
        for i, f in enumerate(frames):
            page.evaluate(f"render({json.dumps(f)})")
            page.screenshot(path=f"{tmp}/f{i:04d}.png")
        browser.close()
        palette = f"{tmp}/palette.png"
        src = ["-framerate", str(FPS), "-i", f"{tmp}/f%04d.png"]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src,
                        "-vf", "palettegen=max_colors=256:stats_mode=full", palette], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, "-i", palette,
                        "-lavfi", "paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                        "-loop", "0", str(OUT)], check=True)
    print(f"{OUT.relative_to(ROOT)}: {len(frames)} frames, {len(frames) / FPS:.1f}s, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
