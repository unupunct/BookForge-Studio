# Changelog

## 0.1.0 – first usable release (MVP)

### Added
- Semantic, versioned document model (paragraph, heading, list, image, table, code, quote, poetry, recipe,
  exercise, scene/page break, footnote) with stable ids, named styles with inheritance and template overrides.
- `.bookforge` project archive (JSON manifest + assets + original-source snapshots), atomic saves with `.bak`,
  traversal-safe loading, schema migration framework, autosave and crash recovery, recent files.
- Importers: TXT (encoding detection, chapter patterns, title detection, poetry mode), Markdown, HTML, DOCX
  (headings, formatting, lists, tables, images, captions, links, breaks, notes), PDF text (scans reported);
  structured import report; originals never modified.
- Layout engine: font metrics, wrapping with justification, widow/orphan control, keep-with-next, splittable
  tables with repeated headers, poetry with stanza spacing and continuation, code wrapping without character
  loss, image scaling with preserved aspect, chapter-start rules with intentional blank pages, mirrored margins,
  gutters, per-matter margins, roman/arabic numbering, running headers/footers, two-pass table of contents.
- PDF export (Digital / Print with bleed and crop marks / Proof): embedded fonts, Unicode, metadata, bookmarks,
  internal links, verification pass, atomic finalise, overwrite protection. DOCX, HTML and Markdown export.
- PySide6 application: dark charcoal / muted orange theme, book navigator with drag-and-drop, rich-text editor
  on structured blocks, properties panel (section, block, book, styles), page preview (thumbnails, spreads,
  zoom, issue outlines, click-to-navigate), new-book wizard (10 profiles), 13 templates with preview and
  library, cover designer, validation report with navigation, book-wide search & replace, undo/redo,
  background jobs with progress and cancellation.
- Windows packaging with PyInstaller and a headless `--selftest`.
- 149 automated tests.

### Known limitations
See `docs/limitations.md`.
