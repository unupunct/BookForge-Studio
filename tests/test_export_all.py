import zipfile

import pymupdf
import pytest
from docx import Document

from app.domain.content_blocks import ImageBlock
from app.services.epub_check import check_epub
from app.services.export_all import FORMATS, export_all, safe_name
from app.services.export_service import ExportError
from app.ui.dialogs.export_all_dialog import ExportAllDialog
from tests.test_ui import qapp, wait_until, window  # noqa: F401  (fixtures)


def test_all_formats_written_and_valid(tmp_path, sample_book):
    keys = [k for k, _, _ in FORMATS]
    progress = []
    res = export_all(sample_book, tmp_path, None, keys, progress=lambda d, t, l: progress.append((d, t)))
    assert all(r.ok for r in res), [r.message for r in res if not r.ok]
    names = sorted(p.name for p in tmp_path.iterdir())
    base = safe_name(sample_book.metadata.title)
    assert names == sorted([f"{base}.pdf", f"{base} (print).pdf", f"{base} (screen).pdf", f"{base}.epub",
                            f"{base}.docx", f"{base}.html",
                            f"{base}.md", f"{base} (cover).pdf"])
    assert pymupdf.open(str(tmp_path / f"{base}.pdf")).page_count == next(r.pages for r in res if r.key == "pdf_digital")
    assert check_epub(tmp_path / f"{base}.epub") == []
    assert Document(str(tmp_path / f"{base}.docx")).core_properties.title == sample_book.metadata.title
    assert progress[0] == (0, 8) and progress[-1] == (8, 8)
    assert not list(tmp_path.glob(".*.tmp"))


def test_default_selection_and_unusual_titles(tmp_path, sample_book):
    sample_book.metadata.title = 'Ce? "Titlu": a/b*'
    res = export_all(sample_book, tmp_path)
    assert [r.key for r in res] == ["pdf_digital", "pdf_print", "pdf_screen", "epub", "docx"] and all(r.ok for r in res)
    assert {p.suffix for p in tmp_path.iterdir()} == {".pdf", ".epub", ".docx"}
    assert all(not set('<>:"/\\|?*') & set(p.name) for p in tmp_path.iterdir())


def test_one_failure_does_not_stop_the_others(tmp_path, sample_book):
    sample_book.sections[2].blocks.append(ImageBlock(asset="ghost"))  # validation error: PDFs blocked
    res = {r.key: r for r in export_all(sample_book, tmp_path, None, ["pdf_digital", "epub", "docx"])}
    assert not res["pdf_digital"].ok and "validation" in res["pdf_digital"].message.lower()
    assert res["epub"].ok and res["docx"].ok
    forced = {r.key: r for r in export_all(sample_book, tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
                                           None, ["pdf_digital"], allow_errors=True)}
    assert forced["pdf_digital"].ok


def test_existing_files_are_protected_per_format(tmp_path, sample_book):
    base = safe_name(sample_book.metadata.title)
    (tmp_path / f"{base}.docx").write_bytes(b"precious")
    res = {r.key: r for r in export_all(sample_book, tmp_path, None, ["epub", "docx"])}
    assert res["epub"].ok and not res["docx"].ok and "already exists" in res["docx"].message
    assert (tmp_path / f"{base}.docx").read_bytes() == b"precious"
    res2 = {r.key: r for r in export_all(sample_book, tmp_path, None, ["docx"], overwrite=True)}
    assert res2["docx"].ok and (tmp_path / f"{base}.docx").read_bytes() != b"precious"


def test_cancel_and_missing_folder(tmp_path, sample_book):
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    res = export_all(sample_book, tmp_path, None, ["epub", "docx", "html", "markdown"], cancel=cancel)
    assert any(r.message == "Cancelled" for r in res)
    with pytest.raises(ExportError, match="does not exist"):
        export_all(sample_book, tmp_path / "nope", None, ["epub"])


def test_dialog_exports_into_a_book_folder(window, tmp_path):
    dlg = ExportAllDialog(window.state, window)
    dlg.folder.setText(str(tmp_path))
    for k, cb in dlg.boxes.items():
        cb.setChecked(k in ("epub", "docx"))
    dlg.start_export()
    assert wait_until(lambda: dlg.results, 60)
    target = tmp_path / safe_name(window.state.project.metadata.title)
    assert sorted(p.suffix for p in target.iterdir()) == [".docx", ".epub"]
    assert "2 of 2 exported" in dlg.log.toPlainText() and not dlg.open_btn.isHidden()
    dlg.close()
