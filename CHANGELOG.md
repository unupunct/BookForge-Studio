# Changelog

## 0.2.1 (found by importing a real 169-poem Facebook export)

### Fixed
- A whole collection was imported as ONE poem (521 pages). Poems are now split at bold header lines; right-aligned
  signature/hashtag lines end a poem and are printed right-aligned *with* it (new `signature` field, editable in
  Block properties); lone dash/asterisk separator lines are not imported as text (reported).
- Centred opening lines (title, subtitle, note) become the book's title page text instead of a fake poem.
- A tool name in the document properties ("python-docx") is no longer used as the author / copyright holder.
- A page break right after the title block no longer leaves an empty page; a single chapter named like the book no
  longer repeats the title above the poems.
- A poem title could be stranded at the bottom of a page when the poem is longer than a page.
- Validation lists repeated informational notes (poem continues, wrapped code) once with a count.

### Added
- Import options "Post headers" (keep / keep only the number / remove) and "Signatures" (drop repeated boilerplate /
  keep / remove). Defaults give a clean book: numbered titles, no boilerplate hashtag.
- 10 more regression tests (collection structure, defaults, options, signature layout, orphan titles).


## 0.2.0

### Added
- Importers keep text formatting: strike, super/subscript, alignment, indents and spacing deviating from the body
  text, soft line breaks; "Chapter N" lines promoted to chapters when no Heading styles exist; author and title read
  from DOCX properties.
- Poetry: automatic verse detection for DOCX, TXT, Markdown and HTML (or force/disable it); every line, leading
  indentation and blank line is kept; blank lines map to stanza gaps (template-controlled, `stanza_gap`);
  poem alignment (left/centre), optional one-poem-per-page rule.
- **New book from manuscript** (Ctrl+Shift+N): file + kind of book + template -> a finished project with cover, title
  page, copyright, contents, chapters, page numbers and the template's design.
- 10 novel templates and 10 poetry templates (33 in total) with chapter numbering (arabic/Roman, custom label),
  chapter drop, title ornaments, uppercase heads, running heads and folio styles; Constantia, Candara, Corbel and
  Tahoma added to the font table.
- Layered cover designer with presets, palettes, shapes, frames, patterns, image filters, rotation, opacity,
  shadow, fit-to-box text, canvas drag/resize; digital front cover PNG/PDF, print front+back with bleed and crop
  marks, and wrap-around print artwork with spine.
- Editor: alignment tools, super/subscript, strike; DOCX/HTML exports keep them.
- 232 automated tests.

### Changed
- Chapter titles at the top of a page honour `chapter_drop` (previously ignored at page top).
- Removed unused settings (`list_of_figures`, `list_of_tables`).


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
