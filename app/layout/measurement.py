"""Text measurement and line breaking on top of font metrics."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain.content_blocks import Run
from ..domain.styles import ResolvedStyle
from .hyphenation import split_points
from .model import Glyphs
from .typography import fonts

_SPLIT = re.compile(r"(\s+)")


@dataclass
class Token:
    text: str
    font: str
    size: float
    color: str
    underline: bool
    link: str | None
    width: float
    is_space: bool = False
    forced_break: bool = False  # a hard line break follows this token
    rise: float = 0.0  # baseline shift in points (superscript > 0)
    strike: bool = False

    def sig(self) -> tuple:
        return (self.font, self.size, self.color, self.underline, self.link, self.rise, self.strike)


LINK_COLOR = "#1F4E9E"


def tokenize(runs: list[Run], style: ResolvedStyle, *, preserve_newlines: bool = True) -> list[Token]:
    tokens: list[Token] = []
    for run in runs:
        family = "mono" if run.code else style.font_family
        face = fonts.face(family, style.bold or run.bold, style.italic or run.italic)
        size = style.font_size * (0.92 if run.code and style.font_family != "mono" else 1.0)
        rise = 0.0
        if run.sup or run.sub:
            size *= 0.65
            rise = style.font_size * (0.38 if run.sup else -0.12)
        color = LINK_COLOR if run.link else style.color
        underline = run.underline or bool(run.link)
        text = run.text.upper() if style.uppercase else run.text

        def make(t: str, space: bool = False, forced: bool = False) -> Token:
            w = 0.0 if forced else fonts.width(t, face.key, size)
            return Token(t, face.key, size, color, underline, run.link, w, space, forced, rise,
                         run.strike)

        for piece in _SPLIT.split(text):
            if not piece:
                continue
            if piece.isspace():
                if preserve_newlines and "\n" in piece:
                    for _ in range(piece.count("\n")):
                        tokens.append(make("", True, True))
                    continue
                tokens.append(make(" ", True))
            else:
                tokens.append(make(piece))
    return tokens


def _split_long_word(tok: Token, width: float) -> list[Token]:
    """Break a word wider than the line so that no character is ever dropped."""
    parts: list[Token] = []
    cur = ""
    for ch in tok.text:
        trial = cur + ch
        if cur and fonts.width(trial, tok.font, tok.size) > width:
            parts.append(Token(cur, tok.font, tok.size, tok.color, tok.underline, tok.link,
                               fonts.width(cur, tok.font, tok.size), False, False, tok.rise, tok.strike))
            cur = ch
        else:
            cur = trial
    if cur:
        parts.append(Token(cur, tok.font, tok.size, tok.color, tok.underline, tok.link,
                           fonts.width(cur, tok.font, tok.size), False, False, tok.rise, tok.strike))
    return parts


@dataclass
class BrokenLine:
    tokens: list[Token]
    last: bool  # last line of paragraph or ends with a hard break


def _hyphenate(piece: Token, room: float, hyph) -> tuple[Token, Token] | None:
    """Split a word so that `head-` fits into `room`. Returns (head with hyphen, tail) or None."""
    word = piece.text
    for pos in reversed(split_points(hyph, word)):
        head_text = word[:pos] + "-"
        w = fonts.width(head_text, piece.font, piece.size)
        if w <= room:
            head = Token(head_text, piece.font, piece.size, piece.color, piece.underline, piece.link, w,
                         False, False, piece.rise, piece.strike)
            tail_text = word[pos:]
            tail = Token(tail_text, piece.font, piece.size, piece.color, piece.underline, piece.link,
                         fonts.width(tail_text, piece.font, piece.size), False, False, piece.rise, piece.strike)
            return head, tail
    return None


def break_lines(tokens: list[Token], first_width: float, rest_width: float, hyph=None,
                width_of=None) -> list[BrokenLine]:
    """Greedy line breaking. `width_of(n)`, when given, is the width of line n (0-based): it lets
    text run narrower beside a floated image and full width below it."""
    lines: list[BrokenLine] = []
    cur: list[Token] = []
    cur_w = 0.0
    avail = max(first_width, 1.0)
    rest_width = max(rest_width, 1.0)

    def flush(last: bool) -> None:
        nonlocal cur, cur_w, avail
        while cur and cur[-1].is_space:
            cur.pop()
        lines.append(BrokenLine(cur, last))
        cur, cur_w = [], 0.0
        avail = max(width_of(len(lines)), 1.0) if width_of else rest_width

    pending: list[Token] = []
    for tok in tokens:
        if tok.forced_break:
            flush(True)
            continue
        if tok.is_space:
            if cur:  # drop leading spaces on a line
                pending.append(tok)
            continue
        pieces = [tok]
        if tok.width > rest_width:
            pieces = _split_long_word(tok, min(avail, rest_width) if not cur else rest_width)
        for piece in pieces:
            space_w = sum(t.width for t in pending)
            if cur and hyph is not None and cur_w + space_w + piece.width > avail + 0.01:
                split = _hyphenate(piece, avail - cur_w - space_w, hyph)
                if split:  # fill the line with the first part and carry the rest over
                    head, tail = split
                    cur.extend(pending)
                    cur_w += space_w
                    pending = []
                    cur.append(head)
                    cur_w += head.width
                    flush(False)
                    piece = tail
                    space_w = 0.0
            if cur and cur_w + space_w + piece.width > avail + 0.01:
                pending = []
                flush(False)
            if cur:
                cur.extend(pending)
                cur_w += space_w
            pending = []
            cur.append(piece)
            cur_w += piece.width
    if cur or not lines:
        flush(True)
    return lines


def place_line(line: BrokenLine, x0: float, avail: float, align: str,
               block_id: str | None) -> tuple[list[Glyphs], float]:
    """Turn a broken line into positioned runs. Returns (items, natural width)."""
    toks = line.tokens
    natural = sum(t.width for t in toks)
    spaces = sum(len(t.text) for t in toks if t.is_space)
    extra = 0.0
    offset = 0.0
    if align == "justify" and not line.last and spaces > 0 and natural < avail:
        extra = (avail - natural) / spaces
    elif align == "center":
        offset = max((avail - natural) / 2, 0.0)
    elif align == "right":
        offset = max(avail - natural, 0.0)
    items: list[Glyphs] = []
    x = x0 + offset
    i = 0
    while i < len(toks):
        j = i
        text = ""
        w = 0.0
        sig = toks[i].sig()
        while j < len(toks) and toks[j].sig() == sig:
            text += toks[j].text
            w += toks[j].width + (extra * len(toks[j].text) if toks[j].is_space else 0.0)
            j += 1
        t0 = toks[i]
        items.append(Glyphs(x=x, y=-t0.rise, text=text, font=t0.font, size=t0.size, color=t0.color,
                            underline=t0.underline, link=t0.link, word_space=extra, width=w,
                            block_id=block_id, strike=t0.strike))
        x += w
        i = j
    return items, natural


def text_width(text: str, family: str, size: float, bold: bool = False,
               italic: bool = False) -> float:
    face = fonts.face(family, bold, italic)
    return fonts.width(text, face.key, size)
