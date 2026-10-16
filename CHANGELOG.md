# Changelog

## 0.3.2 – template covers, live template preview, screen PDF options

- **Every template has its own cover** (19 cover presets x 14 palettes; all 33 templates are distinct). New books get the
  template's cover; applying a template later replaces the cover only if you have not designed your own.
  Templates you save remember their cover.
- **Cover and title page match the interior**: cover text uses the template's heading font, the title page uses the
  same font and the template's chapter ornament. Cover titles shrink so no word is ever broken in the middle.
- **Template library preview shows the cover and the first two pages with the text of your own book** (switchable
  to a sample), laid out by the same engine as the export.
- **Screen PDF**: phone, tablet or computer (A4) page size, and a dark-pages variant (lightness-flipped ink on a dark
  page, covers unchanged). Export dialog options; Export all offers all four.
  Limitation: the dark variant recolours text and shapes, not photographs.

## 0.3.1 – book language, screen PDF, template gallery

- **Generated text follows the book's language** (`app/i18n.py`): "(continued)" becomes "(continuare)" in
  Romanian, and Contents, Index of poems, Chapter/Part labels, recipe and exercise labels are translated
  (en, ro, fr, de, es, it, pt, hu, pl, nl) in the layout, PDF and EPUB.
- **Language detection on import** (stop-word scoring, offline). The manuscript dialog has a Language box
  prefilled with the guess; an explicit choice always wins. Detection returns nothing when unsure.
- **Screen PDF** (phone / tablet / computer): re-laid out on a 108x192 mm single-page format with small margins,
  no facing pages, gutters, blank leaves or print marks. Part of Export all and the Export dialog.
- `scripts/make_template_gallery.py` renders every template (cover + two pages) to images and a gallery PDF.
  Limitation: the cover design is the default one, not template-specific.

## 0.3.0 – ten improvements

1. **Typography cleanup** (Book menu): Romanian/English/German/French quotes, dashes, ellipses, spacing; counts first,
   one undoable step, formatting kept, code/locked blocks untouched.
2. **List of poems**: contents page can list every poem (titles with numbers, or first lines) with real page
   numbers and links; collections of 10+ poems get it automatically on import. Chapters whose title is not printed
   are no longer listed.
3. **EPUB 3 export** with cover, contents (incl. poem index), images (WebP converted), poems with line breaks,
   split of very long sections into several files, and a structural checker that runs after every export.
4. **Hyphenation** (pyphen) for justified body text in the book's language: fewer rivers, measured by tests.
5. **Page-count padding** to multiples of 2/4/8/16/32 with unnumbered blank leaves before the back cover.
6. **Regular-expression** search and replace (groups \1, per-line anchors in poems, clear error messages).
7. **Organise sections**: split a section per poem or at headings, merge with next; undoable.
8. **Book statistics** dialog (words, characters, pages, poems, verse lines, reading time, longest sections).
9. **Export all formats** in one step (digital PDF, print PDF, EPUB, Word, HTML, Markdown, print cover), each format
   isolated from the others' failures.
10. **Go to** (Ctrl+G): jump to a page (printed or sheet number), chapter, heading, poem or recipe by name, ignoring
    diacritics and case.

Also: the sample 168-poem collection now imports with a contents page that lists all poems (poem 9, the word
"Photos", was removed on request); 300 automated tests; self-test also checks EPUB and hyphenation dictionaries.

## 0.2.3

### Added
- "Every poem starts on a new page" (Book tab) now also tidies the result: a poem that only slightly overflows its
  page has its line spacing tightened (never below 1.2) so it stays on one page, and a poem that must continue
  keeps at least 4 lines on its last page instead of 1-2 stray lines. Sample collection: 429 -> 482 pages, 35
  poems on a single page, shortest continuation page 4 lines, all 37,372 words present and in order.


## 0.2.2

### Fixed
- A poem number (title) could be left alone at the top or bottom of a page while its poem started on the next page,
  when the title plus the poem did not fit on one page. Such poems now split normally and keep their title with the
  first lines (checked on all 169 poems of the sample collection: no stranded numbers).
- "New book from manuscript" no longer creates an empty copyright page when there is no author, year, publisher,
  ISBN or rights text (the page is disabled; enable it after filling in the details).


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
