# tools-bookmarks-flatten_merge_bookmarks.py
Bookmark Cleanup Tools  Two Python utilities to clean up browser bookmark exports
# 🧹 Bookmark Cleanup Tools

Two Python utilities to clean up browser bookmark exports (`.html` files):

## 1. `dedupe_merge_netscape_bookmarks.py`
- Removes duplicate URLs.
- Merges same-named folders (sibling or global with `--merge-scope global`).
- Writes `*.dedup.html`.

## 2. `flatten_merge_bookmarks.py`
- Merges all same-named folders (anywhere).
- Flattens everything (no subfolders).
- Removes duplicates globally.
- Writes `*.flat.html`.

### Example
```bash
python3 tools/bookmarks/flatten_merge_bookmarks.py bookmarks.html
