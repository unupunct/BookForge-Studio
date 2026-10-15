import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path_factory, monkeypatch):
    """Keep tests away from the real user profile."""
    d = tmp_path_factory.mktemp("userdata")
    monkeypatch.setenv("BOOKFORGE_DATA_DIR", str(d))
    return d


def make_png(w=200, h=120, color=(200, 80, 40)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return make_png()


LOREM = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua. ")
RO = "Ștefan își ține ceaiul în căni țesute, în Șoimuș. ĂÂÎȘȚ ăâîșț „ghilimele” — …"


@pytest.fixture
def sample_book():
    from app.domain.book import BookProject
    from app.domain.content_blocks import (HeadingBlock, ParagraphBlock, PoetryBlock, Run)
    from app.domain.sections import Section
    b = BookProject()
    b.metadata.title = "Cartea de test"
    b.metadata.author = "Autor Țărănescu"
    b.sections = [Section("Title page", "title_page", show_title=False),
                  Section("Contents", "toc", in_toc=False)]
    for i in range(3):
        ch = Section(f"Capitolul {i + 1}", "chapter")
        ch.blocks = [ParagraphBlock(runs=[Run(LOREM * 8)]) for _ in range(6)]
        ch.blocks.insert(2, HeadingBlock(level=1, runs=[Run(f"Secțiunea {i + 1}")]))
        ch.blocks.append(ParagraphBlock(runs=[Run(RO)]))
        b.sections.append(ch)
    b.sections.append(Section("Poems", "chapter", blocks=[
        PoetryBlock(title="Poem", text="Roses are red\nViolets are blue\n\nSecond stanza\nends here")]))
    return b
