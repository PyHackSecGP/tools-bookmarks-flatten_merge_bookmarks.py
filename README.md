# browser-bookmark-tools — CLI utilities to flatten + merge + dedupe browser bookmarks

Two single-file Python 3 scripts that eat Netscape-format bookmark exports
(the `.html` file every browser spits out) and emit a smaller, saner one:
duplicates gone, tracking params stripped, same-named folders merged,
optional full flattening.

Zero dependencies. Stdlib only.

## 60-Second Overview

Every browser can export bookmarks to the same ancient Netscape HTML format
(`<DL><DT><A HREF=...>`). After a few years of using multiple browsers on
multiple machines you end up with:

- Five exports named `bookmarks_7_12_24.html`, `bookmarks_chrome.html`,
  `firefox_bookmarks.html`...
- The same URL saved 4-10 times across folders.
- Twenty folders called `Dev`, `dev`, `Dev `, `Dev/`, `Development`.
- Deeply nested trees (`Other Bookmarks > Imported > Imported > Bar`) that no
  one navigates.
- Tracking garbage (`?utm_source=...`, `?gclid=...`) that makes "same URL"
  comparisons fail.

Two tools fix this:

| Tool | Does |
|------|------|
| `dedupe_chromium_bookmarks.py` | Preserves folder tree, removes duplicate URLs, prunes empty folders. |
| `dedupe_merge_netscape_bookmarks.py` | Flattens every subtree, merges folders by normalized name, dedupes globally. |

Re-import the output into any browser.

## For Interviewers

### Problem Statement

Bookmark hoarding is a universal digital-hygiene problem. Everyone has
thousands of bookmarks spread across Chrome, Firefox, Edge, Brave, Safari and
various machines. Browser-native "manage bookmarks" UIs cannot merge
exports, cannot dedupe, cannot flatten, and cannot normalize URLs. Online
"bookmark manager" SaaS exists but requires uploading your browsing history
to a third party. These two scripts solve the problem offline in ~200 lines
each.

### Skills Demonstrated

- **HTML parsing of a quirky legacy format.** Netscape bookmark HTML is not
  well-formed XHTML — stray `<p>` tags, missing closers, mixed case
  attributes. `html.parser.HTMLParser` (stdlib) handles it with a small
  state machine.
- **Chromium / Netscape format literacy.** Chromium exports Netscape HTML
  (not the internal `Bookmarks` JSON file); the parser treats both scripts'
  input identically.
- **Deduplication heuristics.** URLs are canonicalized before comparison:
  lowercase scheme + host, strip trailing slash, drop a known-bad set of
  tracking params (`utm_*`, `gclid`, `fbclid`, `mc_cid`, `mc_eid`, `igshid`,
  `ref`). Keeps semantic uniqueness without needing a URL distance metric.
- **Folder-name normalization.** Case-insensitive, whitespace-collapsed
  (including NBSP), punctuation-trimmed — so `Dev `, `dev`, `Dev/` all merge.
- **Tree traversal & pruning.** Depth-first walk, empty-folder pruning,
  streaming output in canonical Netscape format for round-tripping back into
  any browser.
- **CLI design.** `argparse`, sensible default output paths
  (`foo.html` -> `foo.dedup.html` / `foo.flat.html`), stderr for errors,
  stats summary to stdout.

### Architecture

```
    bookmarks.html (Netscape export)
            |
            v
    +---------------------+
    |  NetscapeParser     |     html.parser.HTMLParser subclass
    |  (shared pattern)   |     state machine: H3/A/DL/DT
    +---------------------+
            |
            v
    Folder tree (Folder/Bookmark dataclasses)
            |
     +------+------+
     |             |
     v             v
  prune_and     collect_flat_buckets
  _dedupe       + dedupe_bookmarks_globally
  (keeps        (flattens all subtrees,
   tree)        merges by normalized name)
     |             |
     v             v
   write_netscape_html / write_flat_file
            |
            v
    bookmarks.dedup.html  OR  bookmarks.flat.html
```

### Design Decisions

- **Stdlib only.** `argparse`, `html.parser`, `urllib.parse`, `dataclasses`,
  `re`. No `beautifulsoup4`, no `lxml`. The format is simple enough and
  installing a dep for a one-shot cleanup tool is wrong.
- **Two scripts, not one with a flag.** The tree-preserving dedupe and the
  flatten-everything merge are different user intents. Flattening is
  destructive (loses nesting). Separating them keeps each script < 300 lines
  with a single argparse surface.
- **URL normalization is a tracking-param blacklist, not a scheme-aware
  rewriter.** Keeps the "same URL" set honest without needing a per-site
  rule engine.
- **First-occurrence wins.** When duplicate URLs are found, the first one
  encountered in a depth-first walk is kept. Predictable and preserves the
  earliest-saved title.
- **Round-trippable output.** Writes canonical Netscape HTML (DOCTYPE,
  `<TITLE>`, `<H1>`, `<DL><p>` structure). Preserves `ADD_DATE`,
  `LAST_MODIFIED`, `ICON`, `ICON_URI`, `PERSONAL_TOOLBAR_FOLDER` attributes
  so re-import into any browser keeps timestamps and favicons.
- **No in-place writes.** Output always goes to a new file. Original export
  stays untouched.

### Metrics

- **LOC:** `dedupe_chromium_bookmarks.py` 208 lines; `dedupe_merge_netscape_bookmarks.py` 262 lines.
- **Deps:** 0 third-party. Python 3.8+ (dataclasses + typing).
- **Formats supported:** Netscape bookmark HTML (DOCTYPE
  `NETSCAPE-Bookmark-file-1`). This is the export format for Chrome,
  Chromium, Edge, Brave, Firefox, Safari, Opera and Vivaldi — i.e. all of
  them.
- **Typical reduction:** my own ~4,800-bookmark export collapsed to ~1,900
  after dedupe, ~1,600 after flatten+merge.

## Quick Start

```bash
git clone <this-repo> tools-bookmarks
cd tools-bookmarks

# Export your bookmarks from the browser first:
#   Chrome:  Bookmark Manager -> ... menu -> Export bookmarks
#   Firefox: Library -> Bookmarks -> Manage -> Import/Export -> Export to HTML

# Dedupe one export, keep tree:
python3 dedupe_chromium_bookmarks.py bookmarks.html
# -> writes bookmarks.dedup.html

# Flatten + merge same-named folders:
python3 dedupe_merge_netscape_bookmarks.py bookmarks.html
# -> writes bookmarks.flat.html
```

Then re-import the output file into your browser.

## Tools

| Script | Purpose | Input Format | Output |
|--------|---------|--------------|--------|
| `dedupe_chromium_bookmarks.py` | Remove duplicate URLs, prune empty folders, preserve tree. | Netscape HTML export | `<input>.dedup.html` |
| `dedupe_merge_netscape_bookmarks.py` | Flatten all nesting, merge folders by normalized name, dedupe URLs globally. | Netscape HTML export | `<input>.flat.html` |

Both scripts share the same parser and URL-normalization logic.

## Examples

### 1. Dedupe a Chrome / Chromium export (keep folder tree)

```bash
python3 dedupe_chromium_bookmarks.py ~/Downloads/bookmarks_10_28_26.html
# Wrote deduped HTML to: ~/Downloads/bookmarks_10_28_26.dedup.html
# Summary:
#   Kept URLs:      1872
#   Removed URLs:   2914
#   Folders pruned: 37
```

Re-import `.dedup.html` into Chrome. Same tree, zero duplicates.

### 2. Merge two Netscape exports from different machines

The scripts take a single file at a time. To merge multiple exports,
concatenate the body of the second file into the first inside the top-level
`<DL><p>` block, then dedupe:

```bash
# naive concat — works because both files share the same DOCTYPE wrapper
cat laptop_bookmarks.html desktop_bookmarks.html > merged.html

python3 dedupe_chromium_bookmarks.py merged.html
# -> merged.dedup.html with every unique URL across both machines
```

The parser tolerates the duplicate `<!DOCTYPE>` and `<DL>` wrappers; the
dedupe pass across the combined tree does the merge.

### 3. Flatten a deeply nested bookmark tree

```bash
python3 dedupe_merge_netscape_bookmarks.py bookmarks.html -o flat.html
# Wrote flattened + merged HTML to: flat.html
# Summary:
#   Kept URLs:     1612
#   Removed URLs:  3174
#   Folders kept:  42 (unique names with at least one bookmark)
```

Every bookmark now lives in exactly one folder, named by the normalized
folder name of its deepest original parent. Twenty folders called `Dev`,
`dev `, `DEV`, `Dev/` collapse into one.

## Technical Reference

### Install

```bash
# Python 3.8+ (uses dataclasses + typing). No dependencies.
python3 --version
git clone <this-repo> tools-bookmarks
cd tools-bookmarks
chmod +x dedupe_chromium_bookmarks.py dedupe_merge_netscape_bookmarks.py
```

### `dedupe_chromium_bookmarks.py` CLI

```
usage: dedupe_chromium_bookmarks.py [-h] [-o OUTPUT] input_html

positional arguments:
  input_html            Path to bookmarks HTML export (e.g., bookmarks_*.html)

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output HTML path (default: alongside input with .dedup.html)
```

### `dedupe_merge_netscape_bookmarks.py` CLI

```
usage: dedupe_merge_netscape_bookmarks.py [-h] [-o OUTPUT] input_html

positional arguments:
  input_html            Path to bookmarks HTML export (e.g., bookmarks_*.html)

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output HTML path (default: alongside input with .flat.html)
```

### Format details

- **Input:** Netscape bookmark HTML. DOCTYPE
  `<!DOCTYPE NETSCAPE-Bookmark-file-1>`. Folders are `<DT><H3>Name</H3>`
  followed by `<DL><p>...</DL><p>`. Bookmarks are
  `<DT><A HREF="url" ADD_DATE="..." ICON="...">Title</A>`. Stray `<p>` tags
  are tolerated.
- **Output:** Same format. Preserves `ADD_DATE`, `LAST_MODIFIED`, `ICON`,
  `ICON_URI`, `PERSONAL_TOOLBAR_FOLDER` attributes.
- **URL normalization:** scheme + host lowercased, trailing slash on
  non-root paths stripped, these query params removed:
  `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`,
  `utm_id`, `gclid`, `fbclid`, `mc_cid`, `mc_eid`, `igshid`, `ref`.
- **Folder-name normalization (flatten script only):** case-insensitive,
  whitespace collapsed (including NBSP), trimmed of `/|-:.·;` punctuation
  on the ends.

### Extending

Add tracking params to strip: edit `COMMON_TRACKING_PARAMS` at the top of
either script.

Change the dedupe winner (currently first-seen): modify `prune_and_dedupe`
in `dedupe_chromium_bookmarks.py` or `dedupe_bookmarks_globally` in
`dedupe_merge_netscape_bookmarks.py` to compare `Bookmark.attrs["ADD_DATE"]`
and keep the newest/oldest.

Preserve more attributes in output: add the attribute name to the lists in
`dump_folder` / `dump_flat_html` (currently `ADD_DATE`, `ICON`, `ICON_URI`,
`LAST_MODIFIED`).

## Why This Was Built

Personal digital hygiene. Four browsers across three machines over roughly a
decade produces an export file that no human can meaningfully browse. Every
browser's built-in bookmark manager can delete bookmarks one at a time; none
can dedupe, merge or flatten. The SaaS options want your entire browsing
graph in their cloud. Two Python scripts and an afternoon beat that.

Secondary reason: Netscape bookmark HTML has survived unchanged since 1996.
A small, dependency-free parser for it is a useful artefact to have around.

## FAQ

**Q: Does this work on Firefox / Safari / Edge exports?**
A: Yes. All of them emit the same Netscape HTML format. Chromium's internal
`Bookmarks` JSON file is not supported — export via the UI first.

**Q: Will I lose folders or metadata?**
A: `dedupe_chromium_bookmarks.py` preserves the tree and the common
attributes (`ADD_DATE`, `LAST_MODIFIED`, `ICON`, `ICON_URI`,
`PERSONAL_TOOLBAR_FOLDER`). `dedupe_merge_netscape_bookmarks.py`
intentionally destroys nesting — only one level of folders in the output.
Both preserve bookmark attributes on surviving entries.

**Q: How are duplicates decided?**
A: URLs are canonicalized (lowercase scheme + host, strip trailing slash,
drop known tracking params) and compared as strings. First occurrence in a
depth-first walk wins.

**Q: Can I merge exports from two browsers?**
A: Yes — see Example 2. Concatenate the files and run the dedupe script
over the result.

**Q: What's the Chromium internal `Bookmarks` JSON format?**
A: `~/.config/google-chrome/Default/Bookmarks` on Linux. Not consumed by
these scripts — use the browser's "Export bookmarks" UI, which emits
Netscape HTML, which both scripts read.

## License

MIT. Do what you want.
