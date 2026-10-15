# Architecture and design decisions

## The one rule: a single layout description

`app/layout` converts the semantic book into a `LayoutResult` (`layout/model.py`): pages with absolutely
positioned `Glyphs` (a run of text on one baseline, with its word-spacing for justification), `RectItem`,
`LineItem` and `ImageItem`, plus anchors, outline entries, issues and per-block page lists.

* The preview (`ui/preview/page_renderer.py`, QPainter) and the PDF exporter (`exporters/pdf_exporter.py`,
  ReportLab) both draw **this structure and nothing else**. Neither measures text or decides where a line breaks.
* Text is measured with ReportLab's font metrics on the same registered TrueType files that Qt loads for the
  preview, so the two renderers cannot disagree about line breaks or page breaks. Remaining differences are
  rasterisation only (hinting/anti-aliasing).
* `tests/test_pdf_export.py::test_pdf_text_positions_match_layout_exactly` compares word positions extracted from
  the generated PDF with the layout model.

## Pipeline

```
BookProject (domain)  ──page_builder──▶  Flows (Atoms: lines, rows, images)  ──Paginator──▶  LayoutResult
  semantic blocks         measured, with spacing + keep rules                  pages, labels, headers/footers
```

* **Flow / Atom** (`page_builder.py`): an atom is the smallest unbreakable unit (a line, a table row, an
  image+caption). A flow has `space_before/after`, `keep_with_next`, `keep_together`, widow/orphan counts and
  `header_atoms` (repeated table header / "(continued)" on continuation pages).
* **Paginator** (`pagination.py`): places atoms greedily; applies keep rules, widow/orphan control, chapter
  starts (new page / right-hand page with *intentional* blank leaves), mirrored margins, per-matter margins, page
  labels (roman front matter, arabic body), running headers/footers, and two passes so the table of contents
  carries true page numbers.
* **Never drop content:** when something cannot be placed validly it is placed anyway and reported as a
  `LayoutIssue` (`overflow`, `image_scaled`, `code_wrapped`, `poem_continues`, `accidental_blank_page`, …).
* **Cache:** `LayoutEngine` caches flows per section, keyed by a hash of the section, the styles/settings and the
  assets, so editing one chapter re-measures only that chapter.

## Document model (`app/domain`)

Typed dataclasses; every block has a stable id. Presentation lives in named `StyleDefinition`s with inheritance
(`based_on`); book-level typography settings are the root of the hierarchy (`BuildContext`), so changing the body
font or a style updates everything that inherits it. Styles the user edited carry `user_modified`, which protects
them when a template is applied. Projects are versioned (`SCHEMA_VERSION`) with a migration chain in
`persistence/migrations.py` (framework + tests; no production migrations exist yet because only version 1 exists).

## Editor (`app/ui/editor`)

`QTextDocument` is only a *view* of one section. `block_codec.py` converts blocks ⇄ text blocks; each text block
carries its semantic kind and the id of its model block, so edits keep ids and non-text properties (captions,
image assets, poem titles) are preserved. Images/tables/recipes/page breaks appear as protected placeholder
blocks edited through dialogs. Editing flushes into the model after a 450 ms pause and before saving, exporting
or searching. Pasting inserts plain text only.

## Threads

Layout, validation, import parsing and export run in `QThreadPool` tasks (`workers/task.py`) on a *snapshot* of
the project, so the UI never blocks and background code never reads live widgets. Layout is debounced,
single-flight and cancellable. Autosave snapshots on the UI thread (≈50 ms for 6000 blocks) and zips on a
background thread.

## Safety

* Imports treat files as untrusted: size limits, decompression limits, no script/macro execution, images only from
  the document's own folder, remote images never downloaded, external links never opened.
* `.bookforge` loading validates every archive member path (no absolute paths, `..`, backslashes, drive letters),
  member sizes and counts, and uses JSON only (no pickle).
* Saves and exports write to a temporary file in the destination folder, verify it, then `os.replace`.
* Logs contain event/exception types only.

## Measured performance (this machine, Python 3.13, 6000 blocks / ≈2100 pages, digital profile)

| Operation | Time |
|---|---|
| First full layout | ≈10 s (background) |
| Re-layout after editing one chapter | ≈2 s (background) |
| PDF render (2100 pages) | ≈7 s |
| Save + reopen | ≈0.35 s |
| Project snapshot for background work | ≈0.06 s |
| Import 1 MB TXT | ≈0.11 s |

These numbers come from `tests` helper scripts run during development, not from a benchmark suite; treat them as
orders of magnitude.

## Adding things

* **New block type:** add a dataclass in `content_blocks.py` (it registers itself), a flow builder in
  `page_builder.block_flows`, a codec spec in `block_codec`, and exporters.
* **New export format:** add a module in `app/exporters` and a branch in `services/export_service.py`.
* **New book category:** add a `BookProfile` in `services/project_service.py` and, if needed, a template JSON.
* **New template:** edit `scripts/generate_templates.py` and run it, or drop a JSON file in your templates folder.
