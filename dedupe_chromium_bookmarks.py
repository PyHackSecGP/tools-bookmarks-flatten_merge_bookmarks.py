#!/usr/bin/env python3
import argparse, os, sys, time, re
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
    Minimal parser for Netscape bookmark format:
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
        if tag.upper() == "H3":
            self._collect_text_for = "H3"
            self._temp_attrs = a
            self._text_buf = []
        elif tag.upper() == "A":
            self._collect_text_for = "A"
            self._temp_attrs = a
            self._text_buf = []
        elif tag.upper() == "DL":
            # Opening a child list: if we have a pending folder title, create it now
            if self._pending_folder_title:
                name, fattrs = self._pending_folder_title
                folder = Folder(name=name, attrs=fattrs)
                self.stack[-1].children.append(folder)
                self.stack.append(folder)
                self._pending_folder_title = None
        elif tag.upper() == "DT":
            # No action; structure marker
            pass

    def handle_endtag(self, tag):
        if tag.upper() == "H3" and self._collect_text_for == "H3":
            name = "".join(self._text_buf).strip()
            self._pending_folder_title = (name, dict(self._temp_attrs))
            self._collect_text_for = None
            self._text_buf = []
            self._temp_attrs = {}
        elif tag.upper() == "A" and self._collect_text_for == "A":
            title = "".join(self._text_buf).strip()
            href = self._temp_attrs.get("HREF") or self._temp_attrs.get("href") or ""
            bm = Bookmark(href=href, title=title, attrs=dict(self._temp_attrs))
            self.stack[-1].children.append(bm)
            self._collect_text_for = None
            self._text_buf = []
            self._temp_attrs = {}
        elif tag.upper() == "DL":
            # Close current folder if we are inside one (but not the root)
            if len(self.stack) > 1:
                self.stack.pop()
        # Many exports include stray <p> tags; we can ignore them.

    def handle_data(self, data):
        if self._collect_text_for in ("H3", "A"):
            self._text_buf.append(data)

def prune_and_dedupe(folder: Folder, seen: Set[str], stats: Dict[str,int]) -> Optional[Folder]:
    new_children: List[object] = []
    for ch in folder.children:
        if isinstance(ch, Bookmark):
            norm = normalize_url(ch.href)
            if norm and norm not in seen:
                seen.add(norm)
                new_children.append(ch)
                stats["urls_kept"] += 1
            else:
                stats["urls_removed"] += 1
        elif isinstance(ch, Folder):
            pruned = prune_and_dedupe(ch, seen, stats)
            if pruned and pruned.children:
                new_children.append(pruned)
            else:
                stats["folders_pruned"] += 1
        else:
            # Unknown node; skip to keep output tidy
            pass
    folder.children = new_children
    return folder

def escape_html(t: str) -> str:
    return (t.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))

def dump_folder(folder: Folder, indent: int=0) -> str:
    out = []
    ind = "  " * indent
    for ch in folder.children:
        if isinstance(ch, Folder):
            name = escape_html(ch.name or "Untitled")
            # Preserve a couple of common attributes if present
            h3_attrs = []
            for k in ("ADD_DATE","LAST_MODIFIED","PERSONAL_TOOLBAR_FOLDER"):
                v = ch.attrs.get(k) or ch.attrs.get(k.lower())
                if v is not None:
                    h3_attrs.append(f'{k}="{escape_html(str(v))}"')
            attrs_str = (" " + " ".join(h3_attrs)) if h3_attrs else ""
            out.append(f'{ind}<DT><H3{attrs_str}>{name}</H3>')
            out.append(f'{ind}<DL><p>')
            out.append(dump_folder(ch, indent+1))
            out.append(f'{ind}</DL><p>')
        elif isinstance(ch, Bookmark):
            href = escape_html(ch.href or "")
            title = escape_html(ch.title or ch.href or "Untitled")
            a_attrs = [f'HREF="{href}"']
            # Preserve ADD_DATE / ICON if available
            for k in ("ADD_DATE", "ICON", "ICON_URI", "LAST_MODIFIED"):
                v = ch.attrs.get(k) or ch.attrs.get(k.lower())
                if v is not None:
                    a_attrs.append(f'{k}="{escape_html(str(v))}"')
            out.append(f'{ind}<DT><A {" ".join(a_attrs)}>{title}</A>')
    return "\n".join(out)

def write_netscape_html(folder: Folder, out_path: str):
    header = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten. Do Not Edit! -->
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""
    body = dump_folder(folder, 1)
    footer = "\n</DL><p>\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(body)
        f.write(footer)

def main():
    ap = argparse.ArgumentParser(description="De-duplicate Netscape/HTML bookmark export and keep first occurrence of each URL.")
    ap.add_argument("input_html", help="Path to bookmarks HTML export (e.g., bookmarks_*.html)")
    ap.add_argument("-o", "--output", help="Output HTML path (default: alongside input with .dedup.html)")
    args = ap.parse_args()

    if not os.path.isfile(args.input_html):
        print(f"Error: file not found: {args.input_html}", file=sys.stderr)
        sys.exit(1)

    with open(args.input_html, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    parser = NetscapeParser()
    parser.feed(text)

    stats = {"urls_kept": 0, "urls_removed": 0, "folders_pruned": 0}
    root = parser.root
    pruned = prune_and_dedupe(root, seen=set(), stats=stats)

    out_path = args.output or re.sub(r"\.html?$", "", args.input_html, flags=re.I) + ".dedup.html"
    write_netscape_html(pruned, out_path)

    print("Wrote deduped HTML to:", out_path)
    print("Summary:")
    print(f"  Kept URLs:      {stats['urls_kept']}")
    print(f"  Removed URLs:   {stats['urls_removed']}")
    print(f"  Folders pruned: {stats['folders_pruned']}")

if __name__ == "__main__":
    main()
