# Known limitations and remaining scope (0.1.0)

Honest list of what is **not** implemented or only partly implemented. Nothing here is hidden behind a button.

## Not implemented (planned)

* **EPUB export.** Not attempted: it cannot be validated within this release.
* **RTF import.** No reliable offline RTF parser is bundled; the import dialog tells you to save as DOCX/TXT.
* **OCR.** Scanned PDF pages are detected and reported, never converted to text.
* **Print wrap-around cover** (back + spine + front as one artwork). The cover dialog gives front/back cover
  design, front-cover PNG export and an *estimated* spine width (pages ÷ 2 × the leaf thickness you enter); it
  does not produce spine artwork. Confirm spine width and cover templates with your printer.
* **Footnotes at the page bottom.** Footnotes/endnotes are supported as *end notes* (a footnote block you place at
  the end of a chapter; DOCX imports collect them into a "Notes" section). No per-page footnote reservation.
* **Automatic generation** of index, bibliography, list of figures/tables, figure numbering and cross-references.
  Bibliography/Index/Glossary sections exist and are edited manually (nothing is fabricated).
* **Hyphenation**, kerning pairs beyond the font's own metrics, drop caps, text wrapping around images, text
  overlays on images, free-positioned (fixed-layout) elements, page backgrounds other than covers.
* **Poetry:** one-poem-per-page and "(continued)" markers exist; separation pages between poems do not.
* **Interface localisation.** The UI is English; strings are not yet routed through `tr()`. The document engine is
  Unicode throughout and tested with Romanian diacritics.
* **Cover layers and drag-resizing.** The cover is generated from a form (colours, image, text sizes), not a
  free-form layer canvas.
* **PDF/X or other print-standard compliance.** The Print profile adds bleed, crop marks, trim/bleed boxes and
  high-resolution images and reports fonts/resolution, but is **not** validated against PDF/X and is not labelled
  as such. Run your printer's preflight.

## Partial / behaviours to know

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
