"""Cover presets (ready-made layered designs) and colour palettes."""
from __future__ import annotations

from dataclasses import replace

from ..domain.book import BookProject
from ..domain.layouts import CoverDesign, CoverLayer

# palette: (label, background, background2 or None, title, subtitle, author, accent)
PALETTES: dict[str, tuple[str, str, str | None, str, str, str, str]] = {
    "midnight_gold": ("Midnight & gold", "#1F2430", None, "#F2E8CF", "#C9C2B0", "#D9A066", "#D9A066"),
    "ivory_ink": ("Ivory & ink", "#F4F0E6", None, "#1E1E24", "#4A4A52", "#8A3B12", "#8A3B12"),
    "forest": ("Forest", "#17301F", "#0C1A11", "#F0EAD2", "#B9C9B0", "#E0B96A", "#6FA36B"),
    "burgundy": ("Burgundy", "#4A1423", "#2A0A14", "#F6E9E4", "#D9B8B3", "#E8B86B", "#C97B8B"),
    "ocean": ("Ocean", "#0F3050", "#071A2E", "#EAF4FA", "#A7C4D9", "#7FD1E8", "#3C9DD9"),
    "sunset": ("Sunset", "#E8603C", "#5B2A86", "#FFFFFF", "#FFE2B8", "#FFD27D", "#FFD27D"),
    "slate_orange": ("Slate & orange", "#2B2D31", None, "#E6E6E3", "#A9ABB0", "#D08C4B", "#D08C4B"),
    "rose": ("Rose", "#F3D9D9", "#E8B7B7", "#4A1F2E", "#7A4152", "#8A3B4A", "#B5566B"),
    "noir": ("Noir", "#111214", None, "#F0F0F0", "#9A9AA0", "#FFFFFF", "#C0392B"),
    "royal": ("Royal purple", "#2A1B4D", "#120A28", "#F4EBD0", "#B8AEDC", "#E8D7A0", "#E8D7A0"),
    "sage": ("Sage", "#DDE6D5", "#C4D3BA", "#25402B", "#4F6A55", "#3E5C45", "#6FA36B"),
    "sand": ("Sand", "#EFE3C8", "#D9C7A0", "#3E2A12", "#6B5642", "#7A4B2A", "#9A6B3A"),
    "sky": ("Sky", "#D6E9F6", "#B5D4EA", "#14304F", "#3F5F7C", "#1F4E79", "#3C9DD9"),
    "coral": ("Coral", "#F6D5C8", "#EDB4A0", "#4A1F18", "#7A4034", "#B5402B", "#E8603C"),
}


def _L(kind: str, **kw) -> CoverLayer:
    return CoverLayer(kind=kind, **kw)


def _title(y=0.22, h=0.28, size=38, **kw) -> CoverLayer:
    d = dict(text="{title}", role="title", x=0.1, y=y, w=0.8, h=h, size=size, bold=True, autofit=True,
             valign="middle", name="Title")
    d.update(kw)
    return _L("text", **d)


def _subtitle(y=0.52, size=16, **kw) -> CoverLayer:
    d = dict(text="{subtitle}", role="subtitle", x=0.12, y=y, w=0.76, h=0.1, size=size, italic=True,
             autofit=True, name="Subtitle")
    d.update(kw)
    return _L("text", **d)


def _author(y=0.86, size=16, **kw) -> CoverLayer:
    d = dict(text="{author}", role="author", x=0.1, y=y, w=0.8, h=0.07, size=size, autofit=True,
             valign="middle", name="Author")
    d.update(kw)
    return _L("text", **d)


def _back(color="#F2F2F2", accent="#D9A066", align="center") -> list[CoverLayer]:
    return [_L("text", text="{back_text}", role="subtitle", x=0.14, y=0.18, w=0.72, h=0.55, size=11.5,
               color=color, align=align, line_height=1.4, name="Back text"),
            _L("line", role="accent", x=0.4, y=0.78, w=0.2, h=0.0, stroke=accent, stroke_width=1.0,
               name="Rule"),
            _L("text", text="{publisher}", role="author", x=0.1, y=0.88, w=0.8, h=0.05, size=10, color=accent,
               name="Publisher")]


def preset_keys() -> list[tuple[str, str]]:
    return [(k, v[0]) for k, v in PRESETS.items()]


def _classic() -> tuple:
    return ("#1F2430", None, [
        _L("frame", role="accent", x=0.06, y=0.045, w=0.88, h=0.91, stroke="#D9A066", stroke_width=1.6, name="Frame"),
        _L("frame", role="accent", x=0.075, y=0.06, w=0.85, h=0.88, stroke="#D9A066", stroke_width=0.6, name="Inner frame"),
        _title(color="#F2E8CF", font_family="serif"),
        _L("line", role="accent", x=0.38, y=0.5, w=0.24, h=0.0, stroke="#D9A066", stroke_width=1.2, name="Rule"),
        _subtitle(color="#C9C2B0"), _author(color="#D9A066")], _back("#E8E2D0", "#D9A066"))


def _modern() -> tuple:
    return ("#F4F0E6", None, [
        _L("rect", role="accent", x=0.0, y=0.0, w=0.07, h=0.62, fill="#C97B3C", name="Colour stripe"),
        _title(x=0.14, w=0.78, y=0.12, h=0.4, size=52, color="#1E1E24", align="left", uppercase=True,
               font_family="sans", valign="top"),
        _subtitle(x=0.14, y=0.55, w=0.78, color="#4A4A52", align="left", font_family="sans"),
        _author(x=0.14, y=0.88, color="#1E1E24", align="left", font_family="sans", bold=True)], _back("#1E1E24", "#C97B3C", "left"))


def _minimal() -> tuple:
    return ("#FAFAF7", None, [
        _L("line", role="accent", x=0.15, y=0.3, w=0.7, h=0.0, stroke="#1E1E24", stroke_width=0.6, name="Rule"),
        _title(y=0.32, h=0.2, size=26, color="#1E1E24", uppercase=True, bold=False, font_family="sans"),
        _L("line", role="accent", x=0.15, y=0.55, w=0.7, h=0.0, stroke="#1E1E24", stroke_width=0.6, name="Rule 2"),
        _subtitle(y=0.58, color="#4A4A52"), _author(color="#1E1E24", size=12, font_family="sans")], _back("#1E1E24", "#1E1E24"))


def _photo() -> tuple:
    return ("#222222", None, [
        _L("image", role="photo", x=0.0, y=0.0, w=1.0, h=1.0, name="Photo", fit="cover"),
        _L("rect", role="deco", x=0.0, y=0.45, w=1.0, h=0.55, fill="#000000", fill2="#000000", opacity=0.55,
           name="Shade"),
        _title(y=0.58, h=0.2, size=40, color="#FFFFFF", shadow=True),
        _subtitle(y=0.78, color="#EEEEEE"), _author(y=0.9, color="#FFD27D")], _back("#FFFFFF", "#FFD27D"))


def _geometric() -> tuple:
    return ("#12304A", "#0B1D2E", [
        _L("pattern", role="deco", x=0.0, y=0.0, w=1.0, h=0.62, pattern="circles", scale=22, fill="#3C9DD9",
           stroke_width=0.8, opacity=0.35, name="Circles"),
        _L("ellipse", role="accent", x=0.62, y=0.08, w=0.26, h=0.18, fill="#7FD1E8", opacity=0.85, name="Disc"),
        _title(y=0.45, h=0.25, size=40, color="#EAF4FA"), _subtitle(y=0.72, color="#A7C4D9"),
        _author(color="#7FD1E8")], _back("#EAF4FA", "#7FD1E8"))


def _vintage() -> tuple:
    return ("#E8DCC0", None, [
        _L("frame", role="accent", x=0.07, y=0.05, w=0.86, h=0.9, stroke="#5A3E1B", stroke_width=2.5, name="Frame"),
        _L("frame", role="accent", x=0.09, y=0.07, w=0.82, h=0.86, stroke="#5A3E1B", stroke_width=0.7, name="Inner frame"),
        _title(y=0.22, h=0.3, size=36, color="#3E2A12", italic=True, bold=False),
        _L("text", text="*   *   *", role="accent", x=0.3, y=0.54, w=0.4, h=0.05, size=14, color="#5A3E1B", name="Ornament"),
        _subtitle(y=0.62, color="#5A3E1B"), _author(color="#3E2A12", size=15)], _back("#3E2A12", "#5A3E1B"))


def _sunset() -> tuple:
    return ("#E8603C", "#5B2A86", [
        _L("ellipse", role="accent", x=0.3, y=0.1, w=0.4, h=0.26, fill="#FFD27D", opacity=0.9, name="Sun"),
        _L("pattern", role="deco", x=0.0, y=0.6, w=1.0, h=0.2, pattern="waves", scale=16, fill="#FFFFFF",
           stroke_width=1.0, opacity=0.35, name="Waves"),
        _title(y=0.4, h=0.2, size=38, color="#FFFFFF", uppercase=True, shadow=True),
        _subtitle(y=0.82, size=14, color="#FFE2B8"), _author(y=0.9, color="#FFFFFF", bold=True)], _back("#FFFFFF", "#FFD27D"))


def _dark_elegant() -> tuple:
    return ("#0E0E10", None, [
        _L("line", role="accent", x=0.15, y=0.12, w=0.7, h=0.0, stroke="#D9A066", stroke_width=0.8, name="Top rule"),
        _title(y=0.25, h=0.3, size=34, color="#D9A066", uppercase=True, font_family="serif"),
        _subtitle(y=0.57, color="#9A9AA0"),
        _L("line", role="accent", x=0.15, y=0.88, w=0.7, h=0.0, stroke="#D9A066", stroke_width=0.8, name="Bottom rule"),
        _author(y=0.9, color="#D9A066", size=13)], _back("#C8C8CC", "#D9A066"))


def _poetry_pale() -> tuple:
    return ("#EDE7DD", None, [
        _L("rect", role="accent", x=0.12, y=0.14, w=0.006, h=0.4, fill="#8A6A4A", name="Spine line"),
        _title(x=0.17, w=0.7, y=0.14, h=0.4, size=34, color="#3A2A1C", italic=True, bold=False, align="left",
               valign="top"),
        _subtitle(x=0.17, w=0.7, y=0.58, color="#6B5642", align="left"),
        _L("pattern", role="deco", x=0.0, y=0.78, w=1.0, h=0.22, pattern="stripes", scale=7, fill="#8A6A4A",
           stroke_width=0.5, opacity=0.35, name="Lines"),
        _author(x=0.17, w=0.7, y=0.7, color="#3A2A1C", align="left", size=14)], _back("#3A2A1C", "#8A6A4A"))


def _stack() -> tuple:
    return ("#1B1C1F", None, [
        _L("rect", role="accent", x=0.1, y=0.08, w=0.14, h=0.012, fill="#D08C4B", name="Bar"),
        _title(y=0.12, h=0.6, size=70, color="#E6E6E3", align="left", uppercase=True, font_family="sans",
               valign="top", x=0.1, w=0.82),
        _subtitle(y=0.76, x=0.1, w=0.8, color="#A9ABB0", align="left", font_family="sans"),
        _author(y=0.88, x=0.1, w=0.8, color="#D08C4B", align="left", font_family="sans", bold=True)], _back("#E6E6E3", "#D08C4B", "left"))


def _band() -> tuple:
    return ("#F4F0E6", None, [
        _L("rect", role="accent", x=0.0, y=0.36, w=1.0, h=0.26, fill="#C97B3C", name="Band"),
        _title(y=0.37, h=0.24, size=34, color="#FFFFFF", autofit=True),
        _subtitle(y=0.66, color="#4A4A52"), _author(y=0.88, color="#1E1E24", bold=True)], _back("#1E1E24", "#C97B3C"))


def _split() -> tuple:
    return ("#EDE9E0", None, [
        _L("rect", role="accent", x=0.0, y=0.0, w=0.34, h=1.0, fill="#2B2D31", name="Side panel"),
        _title(x=0.42, w=0.52, y=0.18, h=0.42, size=34, color="#1E1E24", align="left", valign="top"),
        _L("line", role="accent", x=0.42, y=0.64, w=0.18, h=0.0, stroke="#D08C4B", stroke_width=1.6, name="Rule"),
        _subtitle(x=0.42, w=0.52, y=0.67, color="#4A4A52", align="left"),
        _author(x=0.42, w=0.52, y=0.86, color="#1E1E24", align="left", bold=True)], _back("#1E1E24", "#D08C4B", "left"))


def _stars() -> tuple:
    return ("#1A1233", "#0B0718", [
        _L("pattern", role="deco", x=0.0, y=0.0, w=1.0, h=0.36, pattern="dots", scale=26, fill="#E8D7A0",
           stroke_width=0.6, opacity=0.35, name="Stars"),
        _L("ellipse", role="accent", x=0.4, y=0.1, w=0.2, h=0.13, fill="#E8D7A0", opacity=0.9, name="Moon"),
        _title(y=0.42, h=0.26, size=38, color="#F4EBD0", uppercase=True),
        _subtitle(y=0.7, color="#B8AEDC"), _author(color="#E8D7A0", size=15)], _back("#EDE6FF", "#E8D7A0"))


def _ribbon() -> tuple:
    return ("#111214", None, [
        _L("rect", role="accent", x=0.0, y=0.0, w=1.0, h=0.05, fill="#C0392B", name="Top bar"),
        _L("rect", role="accent", x=0.0, y=0.9, w=1.0, h=0.1, fill="#C0392B", name="Bottom bar"),
        _title(y=0.25, h=0.35, size=46, color="#F0F0F0", uppercase=True, bold=True),
        _subtitle(y=0.62, color="#9A9AA0"),
        _author(y=0.915, h=0.07, color="#FFFFFF", bold=True, size=14)], _back("#E8E8E8", "#C0392B"))


def _ornate() -> tuple:
    return ("#18201C", None, [
        _L("frame", role="accent", x=0.07, y=0.05, w=0.86, h=0.9, stroke="#C9A24B", stroke_width=1.4, name="Frame"),
        _L("rect", role="accent", x=0.465, y=0.13, w=0.07, h=0.045, fill="#C9A24B", rotation=45, name="Diamond"),
        _L("line", role="accent", x=0.2, y=0.155, w=0.22, h=0.0, stroke="#C9A24B", stroke_width=0.8, name="Rule left"),
        _L("line", role="accent", x=0.58, y=0.155, w=0.22, h=0.0, stroke="#C9A24B", stroke_width=0.8, name="Rule right"),
        _title(y=0.25, h=0.3, size=36, color="#F2EAD3"), _subtitle(y=0.57, color="#C9C2B0"),
        _L("rect", role="accent", x=0.465, y=0.8, w=0.07, h=0.045, fill="#C9A24B", rotation=45, name="Diamond 2"),
        _author(y=0.87, color="#C9A24B", size=15)], _back("#EDE6D0", "#C9A24B"))


def _horizon() -> tuple:
    return ("#EFE6D6", "#D9C7A8", [
        _L("ellipse", role="accent", x=0.3, y=0.12, w=0.4, h=0.26, fill="#B5566B", opacity=0.85, name="Sun"),
        _L("pattern", role="deco", x=0.0, y=0.7, w=1.0, h=0.3, pattern="waves", scale=18, fill="#8A6A4A",
           stroke_width=0.9, opacity=0.4, name="Waves"),
        _title(y=0.42, h=0.22, size=34, color="#3A2A1C", italic=True, bold=False),
        _subtitle(y=0.64, color="#6B5642"), _author(y=0.58, color="#3A2A1C", size=14)], _back("#3A2A1C", "#8A6A4A"))


def _grid() -> tuple:
    return ("#101820", None, [
        _L("pattern", role="deco", x=0.0, y=0.0, w=1.0, h=0.55, pattern="grid", scale=24, fill="#3C9DD9",
           stroke_width=0.5, opacity=0.3, name="Grid"),
        _L("rect", role="accent", x=0.1, y=0.58, w=0.12, h=0.01, fill="#3C9DD9", name="Bar"),
        _title(x=0.1, w=0.82, y=0.62, h=0.2, size=34, color="#EAF4FA", align="left", bold=True, valign="top"),
        _subtitle(x=0.1, w=0.82, y=0.8, color="#A7C4D9", align="left"),
        _author(x=0.1, w=0.82, y=0.9, color="#7FD1E8", align="left", size=13, bold=True)], _back("#EAF4FA", "#7FD1E8", "left"))


def _playful() -> tuple:
    return ("#FFE9A8", None, [
        _L("ellipse", role="accent", x=0.06, y=0.06, w=0.34, h=0.22, fill="#F26B5B", name="Blob 1"),
        _L("ellipse", role="accent", x=0.56, y=0.1, w=0.36, h=0.24, fill="#4FB0C6", name="Blob 2"),
        _L("ellipse", role="accent", x=0.3, y=0.78, w=0.4, h=0.2, fill="#8BC34A", name="Blob 3"),
        _title(y=0.38, h=0.3, size=48, color="#2B2B5A", font_family="sans"),
        _subtitle(y=0.68, color="#5A4A2A"), _author(y=0.9, color="#2B2B5A", bold=True)], _back("#2B2B5A", "#F26B5B"))


def _triangles() -> tuple:
    return ("#0F2236", "#06101B", [
        _L("pattern", role="deco", x=0.0, y=0.0, w=1.0, h=0.55, pattern="triangles", scale=30, fill="#3C9DD9",
           stroke_width=0.8, opacity=0.35, name="Triangles"),
        _L("line", role="accent", x=0.1, y=0.62, w=0.8, h=0.0, stroke="#7FD1E8", stroke_width=1.0, name="Rule"),
        _title(y=0.64, h=0.2, size=34, color="#EAF4FA", uppercase=True, font_family="sans"),
        _subtitle(y=0.84, size=13, color="#A7C4D9"), _author(y=0.92, color="#7FD1E8", size=13)], _back("#EAF4FA", "#7FD1E8"))


PRESETS: dict[str, tuple] = {
    "classic": ("Classic centred", _classic), "modern": ("Bold modern", _modern),
    "minimal": ("Minimal lines", _minimal), "photo": ("Photo with shade", _photo),
    "geometric": ("Geometric circles", _geometric), "vintage": ("Vintage frame", _vintage),
    "sunset": ("Gradient sunset", _sunset), "elegant": ("Dark elegant", _dark_elegant),
    "poetry": ("Poetry pale", _poetry_pale), "stack": ("Typographic stack", _stack),
    "band": ("Colour band", _band), "split": ("Side panel", _split), "stars": ("Starry night", _stars),
    "ribbon": ("Noir bars", _ribbon), "ornate": ("Ornate diamond", _ornate), "horizon": ("Sun and waves", _horizon),
    "grid": ("Technical grid", _grid), "playful": ("Playful shapes", _playful), "triangles": ("Triangles", _triangles),
}


def apply_preset(book: BookProject, key: str) -> CoverDesign:
    """Replace the cover design with a preset. Existing photo assets are kept on photo layers."""
    label, fn = PRESETS[key]
    bg, bg2, front, back = fn()
    cv = book.settings.cover
    photo = next((l.asset for l in cv.front_layers if l.role == "photo" and l.asset), cv.image_asset)
    for l in front:
        if l.kind == "image" and photo:
            l.asset = photo
        if l.kind == "image" and not photo:
            l.visible = True
    cv.background, cv.background2 = bg, bg2
    cv.front_layers, cv.back_layers = front, back
    cv.back_background = None
    cv.preset, cv.palette = key, ""
    cv.title_color = next((l.color for l in front if l.role == "title"), cv.title_color)
    cv.author_color = next((l.color for l in front if l.role == "author"), cv.author_color)
    return cv


def apply_palette(book: BookProject, key: str) -> None:
    _, bg, bg2, title, sub, author, accent = PALETTES[key]
    cv = book.settings.cover
    cv.palette = key
    cv.background, cv.background2 = bg, bg2
    cv.title_color, cv.author_color = title, author
    for layers in (cv.front_layers, cv.back_layers):
        for l in layers:
            if l.role == "title":
                l.color = title
            elif l.role == "subtitle":
                l.color = sub
            elif l.role == "author":
                l.color = author
            elif l.role == "accent":
                if l.kind in ("text",):
                    l.color = accent
                elif l.kind in ("frame", "line"):
                    l.stroke = accent
                else:
                    l.fill = accent
            elif l.role == "deco" and l.kind == "pattern":
                l.fill = accent


def apply_font(book: BookProject, family: str) -> None:
    """Set the typeface of every text layer, so the cover speaks the same language as the pages."""
    cv = book.settings.cover
    cv.font_family = family
    for layers in (cv.front_layers, cv.back_layers):
        for l in layers:
            if l.kind == "text":
                l.font_family = family


def apply_template_cover(book: BookProject, template: dict) -> bool:
    """Give the book the cover design a template specifies ({"preset", "palette", "font"}).

    Returns False when the template has no cover entry or names something unknown.
    """
    spec = template.get("cover") or {}
    preset, palette = spec.get("preset", ""), spec.get("palette", "")
    if preset not in PRESETS:
        return False
    apply_preset(book, preset)
    if palette in PALETTES:
        apply_palette(book, palette)
    if spec.get("font"):
        apply_font(book, spec["font"])
    book.settings.cover.from_template = template.get("key", "")
    return True
