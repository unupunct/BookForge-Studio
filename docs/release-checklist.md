# Release checklist

Run through this before tagging a release. Items marked (auto) are covered by `scripts\run_tests.bat`.

## Automated
- [ ] `scripts\run_tests.bat` – all tests pass (no skipped tests that are not explained)
- [ ] `scripts\build_windows.bat` – PyInstaller build completes and the packaged `--selftest` reports `"ok": true`
- [ ] Self-test JSON shows 13 templates, fonts embedded, Romanian diacritics present in the extracted PDF text

## Manual – on a clean Windows machine (no Python installed)
- [ ] Copy `dist\BookForgeStudio\` to the machine and start `BookForgeStudio.exe` (no console window, no errors)
- [ ] New book wizard for each category creates a project; preview shows pages
- [ ] Import one real DOCX, one TXT, one Markdown manuscript; read the import report
- [ ] Edit text, headings, lists, a poem, a code block, add an image with caption and a table
- [ ] Change template, page size, margins and body font; confirm the preview updates
- [ ] Validate (F7); double-click each issue and confirm navigation
- [ ] Export Digital PDF, Print PDF (bleed + crop marks) and Proof PDF; open them in a PDF reader; check page
      count, page numbers, bookmarks, links, Romanian diacritics, embedded fonts (document properties ▸ fonts)
- [ ] Export DOCX, HTML and Markdown and open them
- [ ] Save, close, reopen; compare; Save again and confirm a `.bak` exists; corrupt the file and recover from backup
- [ ] Kill the process while editing; reopen and accept the recovery prompt
- [ ] Export onto an existing file: confirm the prompt; export to a read-only folder: confirm the message
- [ ] Windows display scaling 100 % / 150 %; keyboard-only navigation of main areas; screen-reader names spot check

## Content
- [ ] README, CHANGELOG and `docs/limitations.md` reflect the shipped behaviour
- [ ] Version number updated in `app/__init__.py`, `pyproject.toml`, `CHANGELOG.md`
- [ ] Font licensing note reviewed for the fonts shipped/used by the built-in templates
