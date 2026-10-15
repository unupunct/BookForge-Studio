"""Regenerates the built-in template JSON files in app/templates/.

Templates are data, not code: after generation they are plain JSON that users
can duplicate, edit, export and import. Run: python scripts/generate_templates.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "templates"


def tpl(key, name, description, page, margins, body, styles=None, **settings):
    w, h = page
    return {
        "key": key, "name": name, "description": description, "builtin": True, "version": 1,
        "settings": {"page_size": settings.pop("page_size_name", "Custom"), "width_mm": w,
                     "height_mm": h, "margins": margins, "body_font": body["font"],
                     "body_size": body["size"], "line_height": body["leading"],
                     "paragraph_spacing": body.get("spacing", 0.0),
                     "first_line_indent": body.get("indent", 14.0),
                     "justify": body.get("justify", True), **settings},
        "styles": styles or {},
    }


M = lambda t, b, i, o: {"top": t, "bottom": b, "inner": i, "outer": o}
A5 = (148.0, 210.0)
A4 = (210.0, 297.0)
TRADE = (152.4, 228.6)
SQ = (203.0, 203.0)

TEMPLATES = [
    tpl("modern_novel", "Modern Novel", "Clean sans chapter openings over readable serif text.",
        TRADE, M(20, 24, 24, 17), {"font": "Georgia", "size": 10.5, "leading": 1.42},
        {"chapter_title": {"font_family": "Segoe UI", "font_size": 24, "bold": True,
                           "space_before": 90, "space_after": 36},
         "header_footer": {"font_family": "Segoe UI", "font_size": 8}},
        page_size_name="US Trade 6x9", chapter_right_page=True, chapter_drop=90),
    tpl("classic_novel", "Classic Novel", "Traditional serif typography with centred chapter titles.",
        TRADE, M(22, 26, 25, 18), {"font": "Palatino Linotype", "size": 11, "leading": 1.45,
                                    "indent": 16},
        {"chapter_title": {"font_family": "Palatino Linotype", "font_size": 22, "bold": False,
                           "italic": True, "align": "center", "space_before": 80,
                           "space_after": 40}},
        page_size_name="US Trade 6x9", chapter_right_page=True),
    tpl("minimalist_poetry", "Minimalist Poetry", "Generous white space, one idea per page.",
        A5, M(28, 30, 26, 22), {"font": "Cambria", "size": 11, "leading": 1.6, "indent": 0,
                                  "justify": False},
        {"chapter_title": {"font_family": "Cambria", "font_size": 16, "bold": False,
                           "align": "center", "space_before": 90},
         "poetry": {"font_size": 11.5, "line_height": 1.65, "left_indent": 20},
         "poetry_title": {"italic": True, "bold": False}},
        page_size_name="A5", header_rule=False, footer_position="outer", chapter_right_page=True),
    tpl("contemporary_poetry", "Contemporary Poetry", "Sans-serif poems with bold titles.",
        A5, M(24, 26, 24, 20), {"font": "Segoe UI", "size": 10.5, "leading": 1.6, "indent": 0,
                                  "justify": False},
        {"chapter_title": {"font_family": "Segoe UI", "font_size": 20, "bold": True,
                           "align": "left"},
         "poetry": {"font_family": "Segoe UI", "font_size": 10.5, "left_indent": 0},
         "poetry_title": {"font_family": "Segoe UI", "bold": True, "left_indent": 0}},
        page_size_name="A5", header_rule=False, footer_position="outer"),
    tpl("technical_handbook", "Technical Handbook", "Strong heading hierarchy, code and tables.",
        A4, M(22, 24, 24, 20), {"font": "Segoe UI", "size": 10, "leading": 1.4, "indent": 0,
                                  "justify": False, "spacing": 6},
        {"chapter_title": {"font_family": "Segoe UI", "font_size": 26, "bold": True,
                           "color": "#1F3A5F", "space_before": 20},
         "heading1": {"font_family": "Segoe UI", "color": "#1F3A5F", "font_size": 16},
         "heading2": {"font_family": "Segoe UI", "color": "#1F3A5F", "font_size": 13},
         "code": {"font_size": 8.5}},
        page_size_name="A4", chapter_right_page=False, toc_depth=3),
    tpl("it_documentation", "IT Documentation", "Compact documentation layout with continuous chapters.",
        A4, M(20, 22, 22, 18), {"font": "Calibri", "size": 10.5, "leading": 1.35, "indent": 0,
                                  "justify": False, "spacing": 5},
        {"chapter_title": {"font_family": "Calibri", "font_size": 22, "bold": True,
                           "space_before": 10},
         "heading1": {"font_family": "Calibri", "font_size": 15},
         "code": {"font_size": 8.5, "background": "#EFEFEF"}},
        page_size_name="A4", chapter_new_page=False, header_rule=True, toc_depth=3),
    tpl("academic_textbook", "Academic Textbook", "Textbook layout with callouts and numbered hierarchy.",
        A4, M(24, 26, 28, 22), {"font": "Times New Roman", "size": 11, "leading": 1.4, "indent": 0,
                                  "justify": True, "spacing": 6},
        {"chapter_title": {"font_family": "Times New Roman", "font_size": 26, "bold": True,
                           "space_before": 50},
         "callout": {"background": "#EEF3F8"}},
        page_size_name="A4", chapter_right_page=True, toc_depth=3),
    tpl("illustrated_children", "Illustrated Children's Book", "Large friendly type, square pages.",
        SQ, M(18, 18, 18, 18), {"font": "Verdana", "size": 16, "leading": 1.6, "indent": 0,
                                  "justify": False, "spacing": 10},
        {"chapter_title": {"font_family": "Verdana", "font_size": 30, "bold": True,
                           "align": "center"},
         "body": {"font_size": 16}},
        page_size_name="Custom", facing_pages=True, header_rule=False, header_recto="",
        header_verso="", image_default_width_pct=100.0, show_toc=False),
    tpl("cookbook", "Cookbook", "Recipe-first layout with clear headings.",
        A5, M(18, 20, 20, 16), {"font": "Cambria", "size": 10.5, "leading": 1.4, "indent": 0,
                                  "justify": False, "spacing": 4},
        {"chapter_title": {"font_family": "Cambria", "font_size": 24, "color": "#8A3B12"},
         "recipe_heading": {"font_family": "Cambria", "font_size": 18, "color": "#8A3B12"}},
        page_size_name="A5", chapter_right_page=True),
    tpl("biography", "Biography", "Reflective serif layout with generous chapter openings.",
        TRADE, M(22, 25, 25, 18), {"font": "Georgia", "size": 10.5, "leading": 1.45, "indent": 15},
        {"chapter_title": {"font_family": "Georgia", "font_size": 24, "space_before": 80}},
        page_size_name="US Trade 6x9", chapter_right_page=True),
    tpl("business_nonfiction", "Business Nonfiction", "Practical layout with spaced paragraphs.",
        TRADE, M(20, 24, 22, 17), {"font": "Calibri", "size": 11, "leading": 1.4, "indent": 0,
                                     "justify": False, "spacing": 7},
        {"chapter_title": {"font_family": "Calibri", "font_size": 28, "bold": True,
                           "color": "#333333"},
         "heading1": {"font_family": "Calibri", "color": "#C97B3C"}},
        page_size_name="US Trade 6x9", chapter_right_page=False),
    tpl("photo_heavy", "Photo-heavy Book", "Wide margins and full-width images.",
        SQ, M(15, 18, 15, 15), {"font": "Segoe UI", "size": 10, "leading": 1.45, "indent": 0,
                                  "justify": False, "spacing": 6},
        {"caption": {"font_family": "Segoe UI", "font_size": 8.5}},
        page_size_name="Custom", image_default_width_pct=100.0, header_rule=False,
        chapter_right_page=False),
    tpl("general_purpose", "General Purpose", "Balanced defaults for any publication.",
        A5, M(20, 22, 22, 16), {"font": "Georgia", "size": 11, "leading": 1.4, "indent": 14},
        {}, page_size_name="A5"),
]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for t in TEMPLATES:
        (OUT / f"{t['key']}.json").write_text(json.dumps(t, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    print(f"wrote {len(TEMPLATES)} templates to {OUT}")
