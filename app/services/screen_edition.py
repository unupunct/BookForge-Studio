"""A reading edition for screens: phone, tablet and computer.

The print layout (facing pages, gutters, blank leaves to fill signatures) is wrong on a
screen, so the screen PDF is laid out again on a tall single-page format with small even
margins. The book itself is not modified: a copy with adjusted settings is returned.
"""
from __future__ import annotations

import copy

from ..domain.book import BookProject
from ..domain.layouts import Margins

SCREEN_WIDTH_MM = 108.0   # 9:16, close to a phone screen; scales cleanly on tablets and monitors
SCREEN_HEIGHT_MM = 192.0
SCREEN_MARGINS = Margins(top=11.0, bottom=13.0, inner=9.0, outer=9.0)
MIN_BODY_PT = 11.0


def screen_edition(book: BookProject) -> BookProject:
    """Shallow copy of `book` (sections and assets shared, read-only) with screen settings."""
    ed = copy.copy(book)
    st = copy.deepcopy(book.settings)
    st.page_size, st.width_mm, st.height_mm, st.landscape = "Custom", SCREEN_WIDTH_MM, SCREEN_HEIGHT_MM, False
    st.margins = copy.copy(SCREEN_MARGINS)
    st.matter_margins = {}
    st.facing_pages = False
    st.mirrored_margins = False
    st.gutter_mm = 0.0
    st.page_multiple = 0
    st.chapter_right_page = False
    st.hyphenate = True  # narrow columns look gappy without it
    st.body_size = max(st.body_size, MIN_BODY_PT)
    st.line_height = max(st.line_height, 1.4)
    st.footer_position = "center" if st.footer_position != "none" else "none"
    st.export_profile = "digital"
    ed.settings = st
    return ed
