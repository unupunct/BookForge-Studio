import json
import zipfile

import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import (Block, CodeBlock, HeadingBlock, ImageBlock, ListBlock,
                                       ParagraphBlock, PoetryBlock, RecipeBlock, Run, TableBlock)
from app.domain.sections import Section
from app.persistence.migrations import MigrationError, migrate
from app.persistence.project_archive import (ProjectFormatError, backup_path, load_project,
                                             recover_from_backup, relink_asset, save_project)
from tests.conftest import RO, make_png


def test_add_remove_and_stable_ids():
    b = BookProject()
    c1, c2 = Section("One"), Section("Two")
    b.add_section(c1)
    b.add_section(c2)
    ids = (c1.id, c2.id)
    sub = b.add_section(Section("Sub", "section"), parent_id=c1.id)
    assert [s.title for s in b.walk()] == ["One", "Sub", "Two"]
    b.remove_section(c1.id)
    assert [s.title for s in b.walk()] == ["Two"]
    assert c2.id == ids[1] and len(set(ids)) == 2
    assert b.find_section(sub.id) is None


def test_reorder_move_duplicate():
    b = BookProject()
    a, c, d = Section("A"), Section("B"), Section("C")
    for s in (a, c, d):
        b.add_section(s)
    assert b.move_up_down(d.id, -1)
    assert [s.title for s in b.sections] == ["A", "C", "B"]
    b.move_section(d.id, a.id, 0)
    assert [s.title for s in a.children] == ["C"]
    with pytest.raises(ValueError):
        b.move_section(a.id, d.id, 0)  # into own descendant
    copy = b.duplicate_section(a.id)
    assert copy.id != a.id and copy.children[0].id != a.children[0].id


def test_block_roundtrip_all_types():
    blocks = [ParagraphBlock(runs=[Run("a", bold=True), Run("b", link="http://x")]),
              HeadingBlock(level=2, runs=[Run("H")]), ListBlock(ordered=True, items=[[Run("i")]]),
              CodeBlock(text="x = 1\n  y"), PoetryBlock(text="a\nb\n\nc", title="T"),
              TableBlock(rows=[["a", "b"]]), RecipeBlock(title="R", ingredients=["x"]),
              ImageBlock(asset="abc", caption=[Run("cap")])]
    for blk in blocks:
        again = Block.from_dict(json.loads(json.dumps(blk.to_dict())))
        assert again == blk and again.id == blk.id


def test_unknown_block_type_is_preserved_as_text():
    b = Block.from_dict({"type": "hologram", "text": "xyz"})
    assert "hologram" in b.plain_text()


def test_save_and_reopen_preserves_everything(tmp_path, sample_book, png_bytes):
    a = sample_book.add_asset(png_bytes, "pic.png")
    sample_book.sections[2].blocks.append(ImageBlock(asset=a.id, alt="alt", caption=[Run("Fig")]))
    sample_book.sources["orig.txt"] = b"original"
    p = tmp_path / "book.bookforge"
    save_project(sample_book, p)
    again = load_project(p)
    assert again.to_dict() == sample_book.to_dict()
    assert again.assets[a.id].data == png_bytes
    assert again.sources["orig.txt"] == b"original"
    assert again.metadata.author == "Autor Țărănescu"
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
    assert "manifest.json" in names and any(n.startswith("assets/") for n in names)


def test_backup_and_recover(tmp_path, sample_book):
    p = tmp_path / "b.bookforge"
    save_project(sample_book, p)
    sample_book.metadata.title = "Second"
    save_project(sample_book, p)
    assert backup_path(p).exists()
    assert recover_from_backup(p).metadata.title == "Cartea de test"
    p.write_bytes(b"corrupt")
    with pytest.raises(ProjectFormatError):
        load_project(p)
    assert recover_from_backup(p).metadata.title == "Cartea de test"


def test_corrupt_and_unsafe_archives(tmp_path):
    bad = tmp_path / "x.bookforge"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ProjectFormatError):
        load_project(bad)
    no_manifest = tmp_path / "y.bookforge"
    with zipfile.ZipFile(no_manifest, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(ProjectFormatError):
        load_project(no_manifest)
    traversal = tmp_path / "z.bookforge"
    with zipfile.ZipFile(traversal, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "bookforge", "project": {}}))
        z.writestr("../evil.txt", "x")
    with pytest.raises(ProjectFormatError, match="Unsafe"):
        load_project(traversal)
    wrong = tmp_path / "w.bookforge"
    with zipfile.ZipFile(wrong, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "other", "project": {}}))
    with pytest.raises(ProjectFormatError):
        load_project(wrong)


def test_newer_schema_is_rejected(tmp_path, sample_book):
    p = tmp_path / "n.bookforge"
    save_project(sample_book, p)
    with zipfile.ZipFile(p) as z:
        m = json.loads(z.read("manifest.json"))
    m["project"]["schema_version"] = 99
    q = tmp_path / "newer.bookforge"
    with zipfile.ZipFile(q, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
    with pytest.raises(ProjectFormatError, match="newer"):
        load_project(q)


def test_migration_chain():
    migrations = {0: lambda d: {**d, "renamed": d.pop("old")},
                  1: lambda d: {**d, "extra": True}}
    out = migrate({"schema_version": 0, "old": 5}, target=2, migrations=migrations)
    assert out["schema_version"] == 2 and out["renamed"] == 5 and out["extra"] is True
    with pytest.raises(MigrationError):
        migrate({"schema_version": 0, "old": 1}, target=3, migrations=migrations)
    with pytest.raises(MigrationError):
        migrate({"schema_version": 5}, target=2, migrations=migrations)


def test_old_project_is_migrated_on_open_with_backup(tmp_path, sample_book, monkeypatch):
    from app.persistence import migrations as mig
    from app.persistence import project_archive as pa
    p = tmp_path / "old.bookforge"
    save_project(sample_book, p)
    with zipfile.ZipFile(p) as z:
        m = json.loads(z.read("manifest.json"))
    m["project"]["schema_version"] = 0
    m["project"]["metadata"]["title"] = "Legacy"
    old = tmp_path / "legacy.bookforge"
    with zipfile.ZipFile(old, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
    monkeypatch.setitem(mig.MIGRATIONS, 0, lambda d: {**d, "metadata": {**d["metadata"], "title": "Migrated"}})
    book = pa.load_project(old)
    assert book.metadata.title == "Migrated"
    assert list(tmp_path.glob("legacy.bookforge.v0.bak"))


def test_missing_asset_and_relink(tmp_path, sample_book, png_bytes):
    a = sample_book.add_asset(png_bytes, "pic.png")
    p = tmp_path / "m.bookforge"
    save_project(sample_book, p)
    with zipfile.ZipFile(p) as z:
        members = {n: z.read(n) for n in z.namelist() if not n.startswith("assets/")}
    stripped = tmp_path / "stripped.bookforge"
    with zipfile.ZipFile(stripped, "w") as z:
        for n, d in members.items():
            z.writestr(n, d)
    loaded = load_project(stripped)
    assert loaded.assets[a.id].data == b""
    new = tmp_path / "new.png"
    new.write_bytes(make_png(50, 50))
    relink_asset(loaded, a.id, new)
    assert loaded.assets[a.id].data and loaded.assets[a.id].width == 50


def test_atomic_save_leaves_no_temp_files(tmp_path, sample_book):
    p = tmp_path / "t.bookforge"
    save_project(sample_book, p)
    save_project(sample_book, p)
    assert not list(tmp_path.glob("*.tmp"))


def test_save_failure_keeps_previous_file(tmp_path, sample_book, monkeypatch):
    p = tmp_path / "keep.bookforge"
    save_project(sample_book, p)
    before = p.read_bytes()
    import app.persistence.project_archive as pa
    monkeypatch.setattr(pa.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        save_project(sample_book, p)
    assert p.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_romanian_text_survives_save(tmp_path, sample_book):
    sample_book.sections[2].blocks[0] = ParagraphBlock(runs=[Run(RO)])
    p = tmp_path / "ro.bookforge"
    save_project(sample_book, p)
    assert load_project(p).sections[2].blocks[0].plain_text() == RO


def test_decompression_bomb_image_rejected():
    from PIL import Image
    import io
    b = BookProject()
    buf = io.BytesIO()
    Image.new("1", (12000, 12000)).save(buf, "PNG")
    with pytest.raises(ValueError):
        b.add_asset(buf.getvalue(), "huge.png")
