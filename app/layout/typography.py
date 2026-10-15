"""Font discovery, registration and glyph-coverage checks.

Logical families (serif / sans / mono) map to the best installed font. Fonts are
registered with ReportLab, which embeds a subset into every generated PDF.
Font licences are not inspected: only use fonts you are permitted to embed.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
PROJECT_FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REPORTLAB_FONTS = Path(reportlab.__file__).parent / "fonts"

# family -> (regular, bold, italic, bold-italic) file names
FONT_FILES: dict[str, tuple[str, str, str, str]] = {
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "Palatino Linotype": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    "Book Antiqua": ("BOOKOS.TTF", "BOOKOSB.TTF", "BOOKOSI.TTF", "BOOKOSBI.TTF"),
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "Consolas": ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
    "Courier New": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "Constantia": ("constan.ttf", "constanb.ttf", "constani.ttf", "constanz.ttf"),
    "Candara": ("Candara.ttf", "Candarab.ttf", "Candarai.ttf", "Candaraz.ttf"),
    "Corbel": ("corbel.ttf", "corbelb.ttf", "corbeli.ttf", "corbelz.ttf"),
    "Tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "DejaVu Serif": ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf",
                     "DejaVuSerif-BoldItalic.ttf"),
    "DejaVu Sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf",
                    "DejaVuSans-BoldOblique.ttf"),
    "DejaVu Sans Mono": ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
                         "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf"),
    "Bitstream Vera Sans": ("Vera.ttf", "VeraBd.ttf", "VeraIt.ttf", "VeraBI.ttf"),
    "Bitstream Vera Serif": ("VeraSe.ttf", "VeraSeBd.ttf", "VeraSe.ttf", "VeraSeBd.ttf"),
    "Bitstream Vera Mono": ("VeraMono.ttf", "VeraMoBd.ttf", "VeraMoIt.ttf", "VeraMoBI.ttf"),
}

LOGICAL_FAMILIES: dict[str, list[str]] = {
    "serif": ["Georgia", "Times New Roman", "Cambria", "DejaVu Serif", "Bitstream Vera Serif"],
    "sans": ["Segoe UI", "Arial", "Calibri", "DejaVu Sans", "Bitstream Vera Sans"],
    "mono": ["Consolas", "Courier New", "DejaVu Sans Mono", "Bitstream Vera Mono"],
}

SEARCH_DIRS = [PROJECT_FONTS, WIN_FONTS, REPORTLAB_FONTS]


def _find(filename: str) -> Path | None:
    extra = os.environ.get("BOOKFORGE_FONT_DIR")
    for d in ([Path(extra)] if extra else []) + SEARCH_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


@dataclass(frozen=True)
class FontFace:
    key: str
    family: str
    path: Path
    bold: bool = False
    italic: bool = False


class FontManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._faces: dict[str, FontFace] = {}
        self._glyphs: dict[str, set[int]] = {}
        self._widths: dict[tuple[str, str, float], float] = {}

    def installed_families(self) -> list[str]:
        out = []
        for fam, files in FONT_FILES.items():
            if _find(files[0]):
                out.append(fam)
        return out

    def resolve_family(self, family: str) -> str:
        """Map a logical or concrete family name onto an installed family."""
        candidates = LOGICAL_FAMILIES.get(family.lower()) if family else None
        if candidates is None:
            candidates = [family] + LOGICAL_FAMILIES["serif"]
        for fam in candidates:
            files = FONT_FILES.get(fam)
            if files and _find(files[0]):
                return fam
        raise RuntimeError("No usable font found; install a TrueType font or set BOOKFORGE_FONT_DIR")

    def face(self, family: str, bold: bool = False, italic: bool = False) -> FontFace:
        actual = self.resolve_family(family)
        idx = (1 if bold else 0) + (2 if italic else 0)
        order = [idx, 1 if bold else 0, 2 if italic else 0, 0]
        files = FONT_FILES[actual]
        path = None
        chosen = 0
        for i in order:
            path = _find(files[i])
            if path:
                chosen = i
                break
        assert path is not None
        key = f"bf:{actual}:{path.name}"
        with self._lock:
            if key not in self._faces:
                if key not in pdfmetrics.getRegisteredFontNames():
                    if path.suffix.lower() == ".ttc":
                        pdfmetrics.registerFont(TTFont(key, str(path), subfontIndex=0))
                    else:
                        pdfmetrics.registerFont(TTFont(key, str(path)))
                self._faces[key] = FontFace(key, actual, path, chosen in (1, 3), chosen in (2, 3))
        return self._faces[key]

    def by_key(self, key: str) -> FontFace | None:
        return self._faces.get(key)

    def width(self, text: str, key: str, size: float) -> float:
        k = (text, key, size)
        w = self._widths.get(k)
        if w is None:
            w = pdfmetrics.stringWidth(text, key, size)
            if len(self._widths) > 200_000:
                self._widths.clear()
            self._widths[k] = w
        return w

    def glyph_set(self, key: str) -> set[int]:
        if key not in self._glyphs:
            font = pdfmetrics.getFont(key)
            self._glyphs[key] = set(font.face.charToGlyph.keys())
        return self._glyphs[key]

    def missing_glyphs(self, family: str, text: str) -> set[str]:
        """Characters of `text` the family's regular face cannot draw."""
        face = self.face(family)
        have = self.glyph_set(face.key)
        return {c for c in set(text) if not c.isspace() and ord(c) >= 32 and ord(c) not in have}


fonts = FontManager()
