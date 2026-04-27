#!/usr/bin/env python3
"""
Static build — converts all .md files into standalone HTML pages.
Supports grouped manifest: [{group, pages: [{file, title}]}] or flat [{file, title}].

Usage: python3 build.py
Output: dist/
"""

import json, os, pathlib, markdown

ROOT = pathlib.Path(__file__).parent
DIST = ROOT / "docs"
CONTENT = ROOT / "content"
STYLE = (ROOT / "assets" / "style.css").read_text()

TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{style}</style>
</head>
<body>
<nav class="sidebar"><h2>Pages</h2><ul>{nav}</ul></nav>
<main class="md-content">{body}</main>
</body>
</html>"""


def load_manifest():
    manifest_path = CONTENT / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text())
        # detect grouped format
        if data and isinstance(data[0], dict) and "group" in data[0]:
            return data
        # flat format -> wrap
        return [{"group": "Pages", "pages": data}]
    # fallback: auto-discover
    found = [{"file": f.name, "title": f.stem.capitalize()}
             for f in sorted(CONTENT.glob("**/*.md")) if f.name not in ("hello.md", "guide.md")]
    return [{"group": "Reports", "pages": found}] if found else []


def flat_pages(groups):
    result = []
    for g in groups:
        result.extend(g["pages"])
    return result


def build():
    groups = load_manifest()
    pages = flat_pages(groups)
    if not pages:
        print("No pages found.")
        return

    # clean dist
    import shutil
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(exist_ok=True)

    # GitHub Pages base path (change if deploying to custom domain)
    BASE = '/md-site'

    # build nav HTML (grouped) — use root-relative paths to avoid nesting issues
    def nav_html(active_file):
        items = []
        for g in groups:
            items.append(f'<li class="sidebar-group"><span class="sidebar-group-label">{g["group"]}</span>')
            items.append('<ul class="sidebar-group-items">')
            for p in g["pages"]:
                href = BASE + '/' + p["file"].replace(".md", ".html")
                cls = ' class="active"' if p["file"] == active_file else ""
                items.append(f'<li><a href="{href}"{cls}>{p["title"]}</a></li>')
            items.append('</ul></li>')
        return "\n".join(items)

    md = markdown.Markdown(extensions=["tables", "fenced_code"])

    for p in pages:
        src = CONTENT / p["file"]
        if not src.exists():
            print(f"  skip (not found): {p['file']}")
            continue
        md_src = src.read_text()
        body = md.convert(md_src)
        md.reset()
        html = TEMPLATE.format(
            title=p["title"],
            style=STYLE,
            nav=nav_html(p["file"]),
            body=body,
        )
        out = DIST / p["file"].replace(".md", ".html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"  built {out.relative_to(ROOT)}")

    # --- Build index.html (landing page) ---
    INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Reports</title>
<style>{style}
/* index-specific overrides */
.index-container {{ max-width: 720px; margin: 0 auto; padding: 64px 32px; }}
.index-header {{ text-align: center; margin-bottom: 48px; }}
.index-header h1 {{ font-size: 2.2em; margin-bottom: 8px; }}
.index-header p {{ color: var(--text-muted); font-size: 1.1em; }}
.index-group {{ margin-bottom: 32px; }}
.index-group h2 {{ font-size: 1.1em; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 12px; }}
.index-group ul {{ list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }}
.index-group li a {{ display: block; padding: 12px 16px; background: var(--bg-sidebar); border: 1px solid var(--border); border-radius: var(--radius); text-decoration: none; color: var(--text); font-size: 0.95em; transition: border-color 0.15s, box-shadow 0.15s; }}
.index-group li a:hover {{ border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }}
.index-footer {{ text-align: center; color: var(--text-muted); font-size: 0.85em; margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border); }}
@media (max-width: 480px) {{ .index-container {{ padding: 32px 16px; }} .index-group ul {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="index-container">
<div class="index-header">
  <h1>Market Reports</h1>
  <p>A-share, US stock, and weekly market analysis reports</p>
</div>
{groups}
<div class="index-footer">Auto-synced from market-reports · Updated {date}</div>
</div>
</body>
</html>"""

    import datetime
    today = datetime.date.today().isoformat()
    group_html = []
    for g in groups:
        links = []
        for p in g["pages"]:
            href = BASE + '/' + p["file"].replace(".md", ".html")
            links.append(f'<li><a href="{href}">{p["title"]}</a></li>')
        group_html.append(
            f'<div class="index-group"><h2>{g["group"]}</h2><ul>{"".join(links)}</ul></div>'
        )

    index_html = INDEX_TEMPLATE.format(
        style=STYLE,
        groups="\n".join(group_html),
        date=today,
    )
    (DIST / "index.html").write_text(index_html)
    print("  built docs/index.html")

    print(f"\nDone! {len(pages)} pages + index -> {DIST}/")


if __name__ == "__main__":
    build()
