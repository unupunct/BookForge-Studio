# Known limitations and remaining scope (0.4.0)

Honest list of what is **not** implemented or only partly implemented. Nothing here is hidden behind a button.

## Not implemented (planned)

* **RTF import.** No reliable offline RTF parser is bundled; the import dialog tells you to save as DOCX/TXT.
* **OCR.** Scanned PDF pages are detected and reported, never converted to text.
* **Footnotes at the page bottom.** Footnotes/endnotes are supported as *end notes* (a footnote block you place at
  the end of a chapter; DOCX imports collect them into a "Notes" section). No per-page footnote reservation.
* **Automatic generation** of index, bibliography, list of figures/tables, figure numbering and cross-references.
  Bibliography/Index/Glossary sections exist and are edited manually (nothing is fabricated).
* **Kerning pairs beyond the font's own metrics, drop caps, page backgrounds other than covers and designed
  photo pages. Text does not flow around *pinned* items (see below); wrapping works for floated images only.
* **Poetry:** one-poem-per-page and "(continued)" markers exist; separation pages between poems do not.
* **Interface localisation.** The UI is English; strings are not yet routed through `tr()`. The document engine is
  Unicode throughout and tested with Romanian diacritics.
* **PDF/X or other print-standard compliance.** The Print profile adds bleed, crop marks, trim/bleed boxes and
  high-resolution images and reports fonts/resolution, but is **not** validated against PDF/X and is not labelled
  as such. Run your printer's preflight.

## Partial / behaviours to know

* **EPUB 3** is reflowable only (no fixed-layout), with cover, contents, images, poems with line breaks and an NCX
  for older readers. It is checked structurally by the app (package, manifest, spine, XHTML well-formedness,
  link and image targets) but **not** with the W3C EpubCheck tool: run EpubCheck before submitting to a store.
  Fonts are not embedded; page numbers, headers and print margins do not apply.
* **Hyphenation** uses pyphen's pattern dictionaries (many languages incl. Romanian and English); it applies to
  body paragraphs only (not poems, headings or code), words of 6+ letters, at least 2 letters before and 3 after
  the break. Words with digits, apostrophes or hyphens are never split. Dictionary licences differ per language
  (pyphen is MPL/LGPL/GPL; dictionaries come from LibreOffice).
* **Typography cleanup** rules are language-agnostic apart from the quote style you choose; it cannot know whether a
  dash in your text is a minus sign, so only ' - ' between words, '--' and dialogue dashes are converted.

* **Poetry detection is a heuristic** (short lines, little end punctuation, varying indents, centring, soft line
  breaks, runs of short stanzas). The import report says how many poems were found; use the Poetry option
  ("whole text is poetry" / "no poetry") when a file is misjudged. Three or more blank lines in a row start a new
  poem. Bold/italic *inside* a poem's lines is not kept (poems are plain text with line breaks).
* **DOCX fidelity:** character formatting (bold, italic, underline, strike, super/subscript, links, monospace),
  alignment, indents, spacing, lists, tables, images, captions and breaks are kept. Font names, font sizes, colours
  and line spacing from Word are deliberately *not* imported: the template's typography governs the book.
  Indents/spacing used by most paragraphs are treated as the document's body default and dropped.
* **Cover designer:** layered with presets, palettes, patterns and image filters. Text effects are limited to
  shadow, upper-case and fit-to-box (no outline, curved text or letter spacing). The wrap-around spine width is an
  *estimate* from your paper thickness; spine text is rotated top-to-bottom and appears when the spine is at least
  8 mm. Confirm width and the printer's own template before ordering. Cover exports are not PDF/X.

* **Fonts** come from the machine (see README). PDFs embed font subsets; verify licence permission yourself.
  Bold/italic faces are used when installed, otherwise the regular face (no synthetic bold).
* **Editor round-trip:** pasting inserts plain text (formatting is dropped on purpose). Converting a heading back to
  a paragraph resets inline formatting of that block. Selection-spanning deletes can remove image/table
  placeholders; Ctrl+Z restores them. Several lines turned into Poetry/Code merge into one block.
* **DOCX import:** headings, bold/italic/underline, hyperlinks, lists, tables (merged/nested cells flattened,
  reported), images, captions, page and section breaks (as page breaks), footnotes/endnotes (collected as notes),
  tracked insertions accepted / deletions dropped (reported). Not imported (reported): text boxes, equations,
  comments, macros (never run), shapes without pictures, EMF/WMF images.
* **Markdown/HTML import:** nested lists are flattened; raw HTML is kept as plain text with a warning.
* **Table cells** are plain text (no per-cell rich formatting, no merged cells in the model). A table row taller
  than a page is reported as overflow, not split.
* **Page preview** uses Qt rasterisation: text is identical in position to the PDF but anti-aliasing differs.
* **Schema migrations:** only schema version 1 exists. The framework is tested with synthetic migrations.
* **Search/replace** is literal text (no regular expressions). Replace-all never touches locked blocks.
* **Large books:** layout of a 2000-page book takes about ten seconds in the background; the UI stays responsive
  but the preview updates after that.
* Tested on Windows 11 with Python 3.13 and PySide6 6.12. Other Windows versions and a clean-machine install of the
  built `.exe` have not been tested.

## Page layouts (0.4.0)

* **Columns** (1-4 per section): the section title spans the page and the text below it runs in columns. Columns are
  filled one after the other, not balanced, so the last page of a section may end with a short second column.
  Generated pages (contents, title page, copyright, covers) are always single-column. Images and tables take the
  width of one column; nothing spans several columns. In a very narrow column (three or four columns on a small
  page) the "(continued)" marker of a poem can be wider than the column.
* **Per-section page size and margins** are honoured by the PDF, the preview and the layout checks. A change of size
  or margins always starts a new page. EPUB, HTML and Markdown are reflowable and ignore them; DOCX uses the book's
  page size. The *screen* PDF ignores them on purpose (every page of a screen edition has the same format). Blank
  pages inserted for facing pages or for a page-count multiple take the size of the page before them.
* **Floated images** (text wraps beside them) wrap the paragraphs that directly follow the image; a heading, list
  or other block ends the wrapping. The image, its caption and the lines beside it are kept together on one page and
  an image is limited to 60 % of the text height. Text beside the image is not hyphenated differently from the rest.
* **Pinned images and text boxes** sit at an exact place on the page where the block stands and take no room in the
  text flow: text is not pushed away, so overlap is yours to avoid. Drawing order follows block order (a block placed
  earlier is drawn underneath). Text boxes hold plain text in one font and size (shrunk to fit if "shrink" is on).
  In reflowable formats a pinned image becomes an ordinary image and a text box becomes paragraphs.
* **Designed pages** (photo page with overlay, image beside text, image over text, quote page) use plain text that
  shrinks (down to 6 pt, then a warning) to fit its area. A full-page photo is unnumbered and has no margins; it does
  not count as a numbered page. In DOCX these pages become an image followed by their text.
* **Preview editing** moves and resizes pinned images and text boxes (corner handle, arrow keys nudge, Esc deselects).
  Rotation, opacity and exact numbers are set in the block's dialog (double-click its line in the editor). Flowing text
  and floated images cannot be dragged: their position follows from the text.
* **Search/replace and Typography cleanup** do not look inside text boxes or designed pages.
