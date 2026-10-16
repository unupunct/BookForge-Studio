# BookForge Studio

A local-first Windows desktop application that turns manuscripts into professionally formatted books and
validated PDFs. Everything runs offline; manuscripts and images never leave your computer.

**Status: 0.3.2.** See [docs/limitations.md](docs/limitations.md) for exactly what is
and is not implemented.

## Quick start

Requirements: Windows 10/11, Python 3.11+ (developed and tested on Python 3.13).

```bat
scripts\run_windows.bat          :: creates .venv on first run, installs requirements, starts the app
scripts\run_tests.bat            :: runs the automated test suite headlessly
scripts\build_windows.bat        :: builds dist\BookForgeStudio\BookForgeStudio.exe and self-tests it
```

Manual equivalent:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py                       :: start
.venv\Scripts\python main.py path\to\book.bookforge
.venv\Scripts\python main.py --selftest out-folder :: headless end-to-end check (also works in the built .exe)
```

## What you can do

| Step | How |
|---|---|
| Create a book | **File ▸ New book** – wizard with 10 category profiles and 33 templates (incl. 10 novel and 10 poetry designs). **File ▸ New book from manuscript** builds a finished book straight from a DOCX/TXT/Markdown file |
| Import a manuscript | **Import** (Ctrl+I): DOCX, TXT (any encoding), Markdown, HTML, text of PDFs. You see an import report before anything is added. Originals are never modified; a snapshot is stored in the project. Bold/italic/underline/strike, super/subscript, centring, indents and spacing that differ from the body text are kept; poems are recognised (or forced via the Poetry option) and keep every line, indentation and blank line; "Chapter N" lines become chapters when the file has no Heading styles. Collections exported one post per poem (bold header, poem, hashtag, separator) are split into individual poems; numbered date headers can be kept, shortened to the number (default) or removed, and a hashtag repeated on every post is dropped (default) |
| Organise | Book navigator: add / rename / duplicate / hide / remove, drag-and-drop or Alt+↑/↓, nested sections |
| Write | Rich-text editor on structured blocks: headings, bold/italic/underline, inline code, links, lists, quotes, code blocks, poetry (line breaks kept), scene breaks, images with captions, tables, recipes, textbook callouts, find & replace |
| Design | **Book** tab: page size, margins (mirrored, gutter), typography, running headers/footers, numbering. **Styles** tab: edit any named style. **Templates**: preview, apply, duplicate, import/export, save your setup as a template |
| Cover | **Book ▸ Cover design**: layered designer (text, images, rectangles, ellipses, lines, frames, 6 generated patterns), 10 presets, 8 palettes, image filters (B&W, sepia, brightness, contrast, saturation, blur, colour wash, flip), drag/resize/rotate, front and back. Exports: front PNG/PDF (digital), print front+back with bleed and crop marks, and a print wrap-around (back + spine + front) using your paper thickness |
| Preview | **Preview** tab (F5): thumbnails, single page or two-page spread, zoom, click a block to jump to it, pages with problems are outlined |
| Polish | **Book ▸ Typography cleanup**: typographic quotes (Romanian „ ”, English, German, French), dashes, ellipses, spacing, undoable. **Hyphenation** (Book tab, book language). **Pad page count** to a multiple of 2/4/8/16/32 for printers. **List of poems** in the contents. **Statistics**. **Go to** (Ctrl+G): page, chapter, heading or poem by name. Search supports **regular expressions**. Navigator ▸ **Organise**: split a long section into one section per poem or at headings, merge sections |
| Check | **Validate** (F7): missing images, missing glyphs, low-resolution images, overflow, accidental blank pages … double-click an issue to jump to it |
| Export | **Export** (Ctrl+E): Digital / Print / Proof PDF, **EPUB 3**, DOCX, HTML, Markdown; **Export all formats** (Ctrl+Shift+E) writes a whole set into one folder, one format failing never stops the rest. Validate → review → write to a temp file → verify → atomic finalise. Existing files are never overwritten silently |
| Save | `.bookforge` project (ZIP: JSON manifest + assets + original sources). Atomic saves keep a `.bak`; autosave + crash recovery |

Keyboard shortcuts: **Help ▸ Keyboard shortcuts**.

## Architecture in brief

```
app/domain        semantic document model (no Qt, no ReportLab): blocks, sections, styles, settings
app/layout        measurement, flows, pagination → LayoutResult (the ONE shared page description)
app/exporters     pdf (ReportLab) / docx / html / markdown – the PDF exporter only draws the LayoutResult
app/ui/preview    QPainter renderer of the same LayoutResult
app/importers     txt / markdown / html / docx / pdf → blocks + import report
app/persistence   .bookforge archive, atomic save, path-traversal-safe load, schema migrations
app/services      project/template/import/export/validation/search/autosave services
app/workers       background tasks and the debounced layout controller
app/ui            PySide6 widgets (navigator, editor, properties, preview, dialogs, theme)
app/templates     built-in templates as JSON (data, not code)
```

Details and design decisions: [docs/architecture.md](docs/architecture.md).

## Testing

`scripts\run_tests.bat` (or `pytest`) runs 300 tests that inspect real output: PDFs are opened with PyMuPDF
(page size, metadata, extracted text incl. Romanian diacritics, embedded fonts, bookmarks, links, image bounding
boxes, text positions versus the layout model), DOCX files are re-read with python-docx, archives are attacked
with traversal / corruption / interruption scenarios, and the UI is driven headlessly with Qt's offscreen platform.

## Fonts

Layout uses TrueType fonts found on the machine (Windows ships Georgia, Cambria, Times New Roman, Segoe UI, Arial,
Calibri, Consolas …); ReportLab's Vera fonts are the last-resort fallback. Fonts are embedded as subsets in PDFs.
**You are responsible for checking that your fonts' licences permit embedding.** The validator warns when a font
lacks glyphs used by your text. Put extra `.ttf` files in `assets/fonts/` or point `BOOKFORGE_FONT_DIR` at a folder
(file names must match the table in `app/layout/typography.py`).

## Data locations

`%APPDATA%\BookForgeStudio\` – `settings.json`, `window.ini`, `templates\` (your templates), `recovery\`
(autosave), `bookforge.log` (events only, no manuscript text). Override with `BOOKFORGE_DATA_DIR`.
