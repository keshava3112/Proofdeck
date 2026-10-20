"""Exact PPTX export: each card type maps to one slide layout, sources in the footer."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Emu, Inches, Pt

from .facts import FactLibrary
from .render import Brand, stat_split
from .schema import Deck

W, H = Inches(13.333), Inches(7.5)


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#")[:6].upper())


def _text(slide, x, y, w, h, text, size, color, bold=False, italic=False, font="Inter"):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size, run.font.bold, run.font.italic = Pt(size), bold, italic
    run.font.color.rgb = _rgb(color)
    run.font.name = font
    return box


def export_pptx(deck: Deck, facts: FactLibrary, path: str | Path, brand: Brand | None = None) -> Path:
    brand = brand or Brand(name=deck.company)
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]
    margin = Inches(0.8)
    numbering: dict[str, int] = {}

    for card in deck.cards:
        s = prs.slides.add_slide(blank)
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = _rgb(brand.background)
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.18), H)
        bar.fill.solid()
        bar.fill.fore_color.rgb = _rgb(brand.accent)
        bar.line.fill.background()
        _text(s, margin, Inches(0.35), Inches(6), Inches(0.4), brand.name or deck.company, 12, brand.muted, bold=True, font=brand.font)

        refs = []
        for cid in card.all_cites:
            if cid in facts.facts:
                numbering.setdefault(cid, len(numbering) + 1)
                refs.append(cid)

        if card.type == "title":
            if deck.recipient:
                _text(s, margin, Inches(2.2), W - 2 * margin, Inches(0.5), f"PREPARED FOR {deck.recipient.upper()}", 14, brand.accent, bold=True, font=brand.font)
            _text(s, margin, Inches(2.7), W - 2 * margin, Inches(1.6), card.heading, 54, brand.primary, bold=True, font=brand.font)
            if card.bullets:
                _text(s, margin, Inches(4.4), W - 2 * margin, Inches(1), card.bullets[0].text, 24, brand.muted, font=brand.font)
        else:
            _text(s, margin, Inches(0.95), W - 2 * margin, Inches(0.4), card.type.replace("_", " ").upper(), 13, brand.accent, bold=True, font=brand.font)
            _text(s, margin, Inches(1.35), W - 2 * margin, Inches(1.2), card.heading, 34, brand.primary, bold=True, font=brand.font)
            top = Inches(2.75)
            if card.type in ("traction", "pricing", "market") and card.bullets:
                n = len(card.bullets)
                gap = Inches(0.3)
                cw = Emu(int((W - 2 * margin - gap * (n - 1)) / n))
                for k, b in enumerate(card.bullets):
                    x = margin + (cw + gap) * k
                    tile = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, top, cw, Inches(2.6))
                    tile.fill.solid()
                    tile.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    tile.line.color.rgb = _rgb("#e3e1da")
                    tile.adjustments[0] = 0.08
                    num, rest = stat_split(b.text)
                    marks = "".join(f" [{numbering[c]}]" for c in b.cites if c in numbering)
                    if num:
                        _text(s, x + Inches(0.25), top + Inches(0.3), cw - Inches(0.5), Inches(1), num, 40, brand.primary, bold=True, font=brand.font)
                        _text(s, x + Inches(0.25), top + Inches(1.3), cw - Inches(0.5), Inches(1.2), rest + marks, 15, brand.muted, font=brand.font)
                    else:
                        _text(s, x + Inches(0.25), top + Inches(0.3), cw - Inches(0.5), Inches(2.1), b.text + marks, 18, brand.text, font=brand.font)
            else:
                box = s.shapes.add_textbox(margin, top, W - 2 * margin, Inches(3.8))
                tf = box.text_frame
                tf.word_wrap = True
                for k, b in enumerate(card.bullets):
                    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                    p.space_after = Pt(14)
                    prefix = f"{k + 1}.  " if card.type == "plan" else ("" if card.type == "their_words" else "▪  ")
                    r = p.add_run()
                    r.text = prefix + b.text
                    r.font.size = Pt(26 if card.type == "their_words" else 22)
                    r.font.italic = card.type == "their_words"
                    r.font.color.rgb = _rgb(brand.text)
                    r.font.name = brand.font
                    marks = "".join(f" [{numbering[c]}]" for c in b.cites if c in numbering)
                    if marks:
                        m = p.add_run()
                        m.text = marks
                        m.font.size = Pt(12)
                        m.font.color.rgb = _rgb(brand.muted)
            if refs:
                src = "   ".join(f"[{numbering[c]}] {facts.facts[c].source or facts.facts[c].kind}" for c in refs)
                _text(s, margin, H - Inches(0.7), W - 2 * margin, Inches(0.4), src, 10, brand.muted, font=brand.font)
        if card.notes:
            s.notes_slide.notes_text_frame.text = card.notes

    out = Path(path)
    prs.save(out)
    return out
