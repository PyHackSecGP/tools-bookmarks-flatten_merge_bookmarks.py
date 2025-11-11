#!/usr/bin/env python3

import argparse, os, sys, re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set


COMMON_TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
    "utm_id","gclid","fbclid","mc_cid","mc_eid","igshid","ref"
}

def normalize_url(u: str) -> str:
    try:
        s = urlsplit(u)
        scheme = s.scheme.lower()
        netloc = s.netloc.lower()
        path = s.path
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")
        query_pairs = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)]
        filtered = [(k, v) for (k, v) in query_pairs if k not in COMMON_TRACKING_PARAMS]
        query = urlencode(filtered, doseq=True)
        return urlunsplit((scheme, netloc, path, query, "")) or u
    except Exception:
        return u


@dataclass
class Bookmark:
    href: str
    title: str
    attrs: Dict[str, str] = field(default_factory=dict)

@dataclass
class Folder:
    name: str
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List[object] = field(default_factory=list)  # Bookmark | Folder


class NetscapeParser(HTMLParser):
    """
    Parses the common Netscape bookmark format:
      <DL><p>
        <DT><H3 ...>Folder</H3>
        <DL><p>...</DL><p>
        <DT><A HREF="...">Title</A>
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Folder("ROOT")
        self.stack: List[Folder] = [self.root]
        self._pending_folder_title: Optional[Tuple[str, Dict[str,str]]] = None
        self._collect_text_for: Optional[str] = None  # "H3" or "A"
        self._temp_attrs: Dict[str,str] = {}
        self._text_buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        t = tag.upper()
        if t == "H3":
            self._collect_text_for = "H3"
            self._temp_attrs = a
            self._text_buf = []
        elif t == "A":
            self._collect_text_for = "A"
            self._temp_attrs = a
            self._text_buf = []
        elif t == "DL":
            if self._pending_folder_title:
                name, fattrs = self._pending_folder_title
                folder = Folder(name=name, attrs=fattrs)
                self.stack[-1].children.append(folder)
                self.stack.append(folder)
                self._pending_folder_title = None
        elif t == "DT":
            pass

    def handle_endtag(self, tag):
        t = tag.upper()
        if t == "H3" and self._collect_text_for == "H3":
            name = "".join(self._text_buf).strip()
            self._pending_folder_title = (name, dict(self._temp_attrs))
            self._collect_text_for = None
            self._text_buf = []
            self._temp_attrs = {}
        elif t == "A" and self._collect_text_for == "A":
            title = "".join(self._text_buf).strip()
            href = self._temp_attrs.get("HREF") or self._temp_attrs.get("href") or ""
            bm = Bookmark(href=href, title=title, attrs=dict(self._temp_attrs))
            self.stack[-1].children.append(bm)
            self._collect_text_for = None
            self._text_buf = []
            self._temp_attrs = {}
        elif t == "DL":
            if len(self.stack) > 1:
                self.stack.pop()

    def handle_data(self, data):
        if self._collect_text_for in ("H3", "A"):
            self._text_buf.append(data)


NBSP = "\u00A0"

def norm_folder_name(name: str) -> str:
    """Case-insensitive; collapses whitespace (incl. nbsp) and trims light punctuation."""
    if name is None:
        name = ""
    n = name.replace(NBSP, " ")
    n = re.sub(r"\s+", " ", n).strip().lower()
    n = n.strip("/|-:.·;")
    return n

def escape_html(t: str) -> str:
    return (t.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))

def collect_flat_buckets(root: Folder) -> Dict[str, Dict]:
    """
    Traverse entire tree and build buckets by normalized folder name.
    Each bucket stores:
      - display_name: first seen original name to use in output
      - bookmarks: list of Bookmark (deduped later)
      - h3_attrs: the first seen H3 attributes for that name (optional)
    Also collect bookmarks found directly under ROOT into an 'unsorted' bucket.
    """
    buckets: Dict[str, Dict] = {}
    unsorted_key = "__unsorted__"
    buckets[unsorted_key] = {"display_name": "Unsorted", "bookmarks": [], "h3_attrs": {}}

    def add_to_bucket(folder_name: Optional[str], h3_attrs: Dict[str, str], items: List[object]):
        key = norm_folder_name(folder_name or "")
        if not key:
            key = unsorted_key
        if key not in buckets:
            buckets[key] = {
                "display_name": (folder_name or "Unsorted"),
                "bookmarks": [],
                "h3_attrs": dict(h3_attrs or {})
            }
        b = buckets[key]
        # keep first-seen display name / attrs
        if not b.get("h3_attrs"):
            b["h3_attrs"] = dict(h3_attrs or {})
        for it in items:
            if isinstance(it, Bookmark):
                b["bookmarks"].append(it)

    def walk(node: Folder, parent: Optional[Folder]):
        if node is not root:
            add_to_bucket(node.name, node.attrs, node.children)
        else:
            add_to_bucket(None, {}, node.children)

        for ch in node.children:
            if isinstance(ch, Folder):
                walk(ch, node)

    walk(root, None)
    return buckets

def dedupe_bookmarks_globally(buckets: Dict[str, Dict]) -> Tuple[Dict[str, Dict], Dict[str,int]]:
    seen: Set[str] = set()
    stats = {"urls_kept": 0, "urls_removed": 0, "folders_total": 0}

    for key, b in buckets.items():
        new_list: List[Bookmark] = []
        for bm in b["bookmarks"]:
            norm = normalize_url(bm.href)
            if norm and norm not in seen:
                seen.add(norm)
                new_list.append(bm)
                stats["urls_kept"] += 1
            else:
                stats["urls_removed"] += 1
        b["bookmarks"] = new_list
        if b["bookmarks"]:
            stats["folders_total"] += 1
    return buckets, stats


def dump_flat_html(buckets: Dict[str, Dict]) -> str:
    lines = []
    for key, b in buckets.items():
        if not b["bookmarks"]:
            continue
        name = escape_html(b["display_name"] or "Untitled")
        # keep a few attrs if present
        h3_attrs = []
        for k in ("ADD_DATE","LAST_MODIFIED","PERSONAL_TOOLBAR_FOLDER"):
            v = b["h3_attrs"].get(k) or b["h3_attrs"].get(k.lower())
            if v is not None:
                h3_attrs.append(f'{k}="{escape_html(str(v))}"')
        attrs_str = (" " + " ".join(h3_attrs)) if h3_attrs else ""
        lines.append(f'<DT><H3{attrs_str}>{name}</H3>')
        lines.append(f'<DL><p>')
        for bm in b["bookmarks"]:
            href = escape_html(bm.href or "")
            title = escape_html(bm.title or bm.href or "Untitled")
            a_attrs = [f'HREF="{href}"']
            for k in ("ADD_DATE", "ICON", "ICON_URI", "LAST_MODIFIED"):
                v = bm.attrs.get(k) or bm.attrs.get(k.lower())
                if v is not None:
                    a_attrs.append(f'{k}="{escape_html(str(v))}"')
            lines.append(f'  <DT><A {" ".join(a_attrs)}>{title}</A>')
        lines.append(f'</DL><p>')
    return "\n".join(lines)

def write_flat_file(buckets: Dict[str, Dict], out_path: str):
    header = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten. Do Not Edit! -->
<TITLE>Bookmarks (Flattened)</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""
    body = dump_flat_html(buckets)
    footer = "\n</DL><p>\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(body)
        f.write(footer)


def main():
    ap = argparse.ArgumentParser(description="Flatten bookmarks: merge same-named folders globally, remove subfolders, dedupe URLs.")
    ap.add_argument("input_html", help="Path to bookmarks HTML export (e.g., bookmarks_*.html)")
    ap.add_argument("-o", "--output", help="Output HTML path (default: alongside input with .flat.html)")
    args = ap.parse_args()

    if not os.path.isfile(args.input_html):
        print(f"Error: file not found: {args.input_html}", file=sys.stderr)
        sys.exit(1)

    with open(args.input_html, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    parser = NetscapeParser()
    parser.feed(text)

    # Build buckets (1 per folder name globally), then dedupe across all
    buckets = collect_flat_buckets(parser.root)
    buckets, stats = dedupe_bookmarks_globally(buckets)

    out_path = args.output or re.sub(r"\.html?$", "", args.input_html, flags=re.I) + ".flat.html"
    write_flat_file(buckets, out_path)

    print("Wrote flattened + merged HTML to:", out_path)
    print("Summary:")
    print(f"  Kept URLs:     {stats['urls_kept']}")
    print(f"  Removed URLs:  {stats['urls_removed']}")
    print(f"  Folders kept:  {stats['folders_total']} (unique names with at least one bookmark)")

if __name__ == "__main__":
    main()
