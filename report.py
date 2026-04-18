#!/usr/bin/env python3
"""
市场报告 Markdown 转换器
支持：网页版 (HTML)、微信公众号版 (WeChat)
单文件 / 批量 / 目录递归均可

用法：
  python3 report.py weekly/2026-W16.md              # 默认生成 html + wechat
  python3 report.py weekly/2026-W16.md -f html       # 只生成网页版
  python3 report.py weekly/2026-W16.md -f wechat     # 只生成公众号版
  python3 report.py weekly/                           # 批量处理整个目录
  python3 report.py weekly/ daily/ -f all            # 多目录批量
  python3 report.py weekly/ -r                       # 递归子目录
  python3 report.py weekly/ -r -o dist/              # 输出到指定目录
"""

import sys
import os
import re
import argparse
from pathlib import Path

try:
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
except ImportError:
    print("Installing markdown library...")
    os.system(f"{sys.executable} -m pip install markdown -q")
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension


# ================================================================
#  内联样式定义
# ================================================================

HTML_CSS = """
<style>
:root {
  --primary: #1a73e8;
  --green: #0d904f;
  --red: #d93025;
  --bg: #f8f9fa;
  --card: #ffffff;
  --text: #202124;
  --muted: #5f6368;
  --border: #dadce0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.8; padding: 0;
}
.container { max-width: 860px; margin: 0 auto; padding: 40px 24px; }
.report-header {
  background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
  color: #fff; padding: 48px 24px; text-align: center;
  margin-bottom: 32px; border-radius: 0 0 24px 24px;
}
.report-header h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.report-header h2 { font-size: 16px; font-weight: 400; opacity: 0.9; }
.card {
  background: var(--card); border-radius: 16px; padding: 32px;
  margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
}
h2 {
  font-size: 22px; font-weight: 700; color: var(--primary);
  margin: 32px 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #e8f0fe;
}
h2:first-child { margin-top: 0; }
h3 { font-size: 17px; font-weight: 600; color: var(--text); margin: 24px 0 12px 0; }
table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 14px; }
thead th {
  background: #e8f0fe; color: var(--primary); font-weight: 600;
  padding: 10px 14px; text-align: left; border-bottom: 2px solid var(--border);
}
tbody td { padding: 10px 14px; border-bottom: 1px solid #f1f3f4; }
tbody tr:hover { background: #f8f9fa; }
td:nth-child(4), td:nth-child(5) { font-weight: 600; font-variant-numeric: tabular-nums; }
ul, ol { margin: 12px 0; padding-left: 24px; }
li { margin: 6px 0; line-height: 1.7; }
strong { font-weight: 600; }
em { color: var(--muted); font-size: 13px; }
hr { border: none; height: 1px; background: var(--border); margin: 24px 0; }
.footer { text-align: center; color: var(--muted); font-size: 13px; padding: 24px; }
@media (max-width: 600px) {
  .container { padding: 20px 12px; }
  .card { padding: 20px; }
  .report-header { padding: 32px 16px; }
  .report-header h1 { font-size: 22px; }
  table { font-size: 13px; }
  thead th, tbody td { padding: 8px 10px; }
}
</style>
"""

WC_STYLES = {
    "wrapper": "max-width:677px;margin:0 auto;padding:20px;font-size:15px;color:#3f3f3f;line-height:1.8;letter-spacing:0.5px;font-family:-apple-system,system-ui,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;",
    "h1": "font-size:22px;font-weight:bold;color:#333;text-align:center;margin:30px 0 5px;",
    "h1_sub": "font-size:14px;color:#888;text-align:center;margin:0 0 30px;",
    "h2": "font-size:18px;font-weight:bold;color:#1a73e8;border-left:4px solid #1a73e8;padding-left:12px;margin:30px 0 15px;",
    "h3": "font-size:16px;font-weight:bold;color:#333;margin:25px 0 12px;",
    "p": "margin:10px 0;text-align:justify;",
    "strong": "color:#1a73e8;font-weight:bold;",
    "em": "color:#888;font-size:13px;",
    "ul": "margin:10px 0;padding-left:20px;",
    "li": "margin:6px 0;",
    "table": "width:100%;border-collapse:collapse;margin:15px 0;font-size:14px;",
    "th": "background:#1a73e8;color:#fff;font-weight:bold;padding:8px 10px;text-align:center;",
    "td": "padding:8px 10px;text-align:center;border-bottom:1px solid #eee;",
    "td_left": "padding:8px 10px;text-align:left;border-bottom:1px solid #eee;",
    "hr": "border:none;height:1px;background:linear-gradient(to right,#ddd,#aaa,#ddd);margin:25px 0;",
    "tag_red": "color:#d93025;font-weight:bold;",    # 涨
    "tag_green": "color:#0d904f;font-weight:bold;",  # 跌
    "footer": "text-align:center;color:#aaa;font-size:12px;margin:30px 0 10px;",
    "divider_emoji": "text-align:center;font-size:20px;margin:20px 0;color:#1a73e8;letter-spacing:8px;",
}

SECTION_EMOJIS = {
    "主要指数": "📊", "板块轮动": "🔄", "重要事件": "📌",
    "市场特征": "🔍", "下周展望": "🔮", "免责声明": "⚠️",
}


# ================================================================
#  辅助函数
# ================================================================

def colorize(text: str, red_up: bool = True) -> str:
    """A股涨跌标色（红涨绿跌）"""
    up, down = (WC_STYLES["tag_red"], WC_STYLES["tag_green"]) if red_up else ("color:#0d904f;", "color:#d93025;")
    text = re.sub(r'(\+\d+\.\d+%?)', lambda m: f'<span style="{up}">{m.group(1)}</span>', text)
    text = re.sub(r'(-\d+\.\d+%?)', lambda m: f'<span style="{down}">{m.group(1)}</span>', text)
    return text


def colorize_to_spans(text: str) -> str:
    """为 HTML 版本标色（返回 span 标签，用于 re.sub 替换）"""
    text = re.sub(r'>(\+\d+\.\d+%?)<', r'><span style="color:#d93025;font-weight:600">\1</span><', text)
    text = re.sub(r'>(-\d+\.\d+%?)<', r'><span style="color:#0d904f;font-weight:600">\1</span><', text)
    return text


def md_to_html(raw_md: str) -> str:
    """Markdown 转基础 HTML"""
    md = markdown.Markdown(
        extensions=[TableExtension(), FencedCodeExtension()],
        output_format='html5'
    )
    return md.convert(raw_md)


# ================================================================
#  网页版生成
# ================================================================

def build_html(raw_md: str, title: str, subtitle: str) -> str:
    body = md_to_html(raw_md)

    # 分段包裹成 card
    parts = re.split(r'(<h2.*?</h2>)', body)
    wrapped = []
    i = 0
    while i < len(parts):
        if parts[i].startswith('<h2'):
            section = parts[i]
            i += 1
            while i < len(parts) and not parts[i].startswith('<h2'):
                section += parts[i]
                i += 1
            wrapped.append(f'<div class="card">{section}</div>')
        else:
            if parts[i].strip():
                wrapped.append(parts[i])
            i += 1

    body = '\n'.join(wrapped)
    body = colorize_to_spans(body)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - {subtitle}</title>
{HTML_CSS}
</head>
<body>
<div class="report-header">
  <h1>{title}</h1>
  <h2>{subtitle}</h2>
</div>
<div class="container">
{body}
</div>
<div class="footer">
  Generated by Hermes Agent &middot; {subtitle}
</div>
</body>
</html>"""


# ================================================================
#  微信公众号版生成
# ================================================================

def add_emoji_headers(html: str) -> str:
    def replace_h2(m):
        title = m.group(1)
        emoji = ""
        for key, em in SECTION_EMOJIS.items():
            if key in title:
                emoji = em + " "
                break
        return f'<h2 style="{WC_STYLES["h2"]}">{emoji}{title}</h2>'
    return re.sub(r'<h2[^>]*>(.*?)</h2>', replace_h2, html, flags=re.DOTALL)


def convert_table(table_html: str) -> str:
    table_html = re.sub(
        r'<th>(.*?)</th>',
        lambda m: f'<th style="{WC_STYLES["th"]}">{colorize(m.group(1))}</th>',
        table_html, flags=re.DOTALL
    )
    table_html = re.sub(
        r'<td>(.*?)</td>',
        lambda m: f'<td style="{WC_STYLES["td"]}">{colorize(m.group(1))}</td>',
        table_html, flags=re.DOTALL
    )
    # 第一列左对齐
    table_html = re.sub(
        r'<tr>\s*<td style="([^"]*?)">(.*?)</td>',
        lambda m: f'<tr><td style="{WC_STYLES["td_left"]}">{m.group(2)}</td>',
        table_html, flags=re.DOTALL
    )
    return f'<table style="{WC_STYLES["table"]}">{table_html}</table>'


def build_wechat(raw_md: str, title: str, subtitle: str) -> str:
    # 去掉开头 h1+h2，后面手动拼
    body = md_to_html(raw_md)
    body = re.sub(r'^<h1>.*?</h1>\s*<h2>.*?</h2>\s*<hr\s*/?>\s*', '', body, flags=re.DOTALL)

    # 内联样式处理
    body = re.sub(r'<h1>(.*?)</h1>', lambda m: f'<h1 style="{WC_STYLES["h1"]}">{m.group(1)}</h1>', body)
    body = re.sub(r'<h2>(.*?)</h2>', lambda m: f'<h2 style="{WC_STYLES["h2"]}">{m.group(1)}</h2>', body)
    body = re.sub(r'<h3>(.*?)</h3>', lambda m: f'<h3 style="{WC_STYLES["h3"]}">{m.group(1)}</h3>', body)
    body = re.sub(r'<table>(.*?)</table>', lambda m: convert_table(m.group(0)), body, flags=re.DOTALL)
    body = re.sub(r'<ul>', f'<ul style="{WC_STYLES["ul"]}">', body)
    body = re.sub(r'<ol>', f'<ol style="{WC_STYLES["ul"]}">', body)
    body = re.sub(r'<li>', f'<li style="{WC_STYLES["li"]}">', body)
    body = re.sub(r'<p>(.*?)</p>', lambda m: f'<p style="{WC_STYLES["p"]}">{colorize(m.group(1))}</p>', body, flags=re.DOTALL)
    body = re.sub(r'<strong>(.*?)</strong>', lambda m: f'<strong style="{WC_STYLES["strong"]}">{m.group(1)}</strong>', body)
    body = re.sub(r'<em>(.*?)</em>', lambda m: f'<em style="{WC_STYLES["em"]}">{m.group(1)}</em>', body)
    body = re.sub(r'<hr\s*/?>', f'<div style="{WC_STYLES["hr"]}"></div>', body)
    body = colorize(body)
    body = add_emoji_headers(body)

    return f"""<section style="{WC_STYLES['wrapper']}">
<h1 style="{WC_STYLES['h1']}">{title}</h1>
<p style="{WC_STYLES['h1_sub']}">{subtitle}</p>
<div style="{WC_STYLES['divider_emoji']}">· · ·</div>
{body}
<div style="{WC_STYLES['footer']}">
  <p>— 报告由 Hermes Agent 生成 —</p>
  <p>{title} · {subtitle}</p>
</div>
</section>"""


# ================================================================
#  文件处理
# ================================================================

def extract_meta(md_text: str) -> tuple[str, str]:
    lines = md_text.strip().split('\n')
    title = lines[0].lstrip('# ').strip() if lines else "报告"
    subtitle = lines[1].lstrip('# ').strip() if len(lines) > 1 else ""
    return title, subtitle


def convert_file(md_path: Path, formats: list[str], out_dir: Path | None = None) -> list[str]:
    """转换单个 md 文件，返回生成的文件路径列表"""
    if not md_path.exists():
        print(f"  SKIP  {md_path} (not found)")
        return []

    raw = md_path.read_text(encoding='utf-8')
    title, subtitle = extract_meta(raw)
    results = []

    # 确定输出目录
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        base = out_dir / md_path.stem
    else:
        base = md_path.with_suffix('')  # 去掉 .md

    if 'html' in formats:
        html = build_html(raw, title, subtitle)
        out = base.with_suffix('.html')
        out.write_text(html, encoding='utf-8')
        size = len(html.encode('utf-8')) // 1024
        results.append(str(out))
        print(f"  HTML  {out} ({size}KB)")

    if 'wechat' in formats:
        html = build_wechat(raw, title, subtitle)
        out = base.with_name(base.name + '.wechat.html')
        out.write_text(html, encoding='utf-8')
        size = len(html.encode('utf-8')) // 1024
        results.append(str(out))
        print(f"  WX    {out} ({size}KB)")

    return results


def collect_md_files(paths: list[str], recursive: bool = False) -> list[Path]:
    """从路径列表收集所有 .md 文件"""
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.md':
            files.append(path)
        elif path.is_dir():
            pattern = '**/*.md' if recursive else '*.md'
            files.extend(sorted(path.glob(pattern)))
        else:
            print(f"  WARN  {p} is not a .md file or directory")
    return files


# ================================================================
#  CLI
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description='市场报告 Markdown 转换器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s weekly/2026-W16.md                  # 生成 html + wechat
  %(prog)s weekly/2026-W16.md -f html          # 只生成网页版
  %(prog)s weekly/2026-W16.md -f wechat        # 只生成公众号版
  %(prog)s weekly/                              # 批量处理目录
  %(prog)s weekly/ daily/ -r                   # 递归多目录
  %(prog)s weekly/ -r -o dist/                 # 输出到 dist 目录
"""
    )
    parser.add_argument('inputs', nargs='+', help='输入文件或目录')
    parser.add_argument('-f', '--format', default='all',
                        choices=['html', 'wechat', 'all'],
                        help='输出格式 (default: all)')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='递归处理子目录')
    parser.add_argument('-o', '--output', default=None,
                        help='输出目录 (默认与源文件同目录)')

    args = parser.parse_args()
    formats = ['html', 'wechat'] if args.format == 'all' else [args.format]
    out_dir = Path(args.output) if args.output else None

    files = collect_md_files(args.inputs, args.recursive)
    if not files:
        print("No .md files found.")
        sys.exit(1)

    print(f"Found {len(files)} file(s), format: {', '.join(formats)}")
    print()

    total = 0
    for f in files:
        print(f"[{f}]")
        results = convert_file(f, formats, out_dir)
        total += len(results)
        print()

    print(f"Done! Generated {total} file(s) from {len(files)} source(s).")


if __name__ == '__main__':
    main()
