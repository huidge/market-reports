#!/usr/bin/env bash
# sync-reports.sh — Sync markdown from market-reports to md-site, build, and push to GitHub.
set -euo pipefail

MARKET_DIR="/Users/huidge/market-reports"
SITE_DIR="/Users/huidge/md-site"
CONTENT_DIR="$SITE_DIR/content"

# Only sync these directories (relative to MARKET_DIR)
SYNC_DIRS=("daily" "us-stock/daily" "weekly")

# Files to always ignore
IGNORE_FILES=("readme.md" "hello.md" "guide.md")

echo "=== Sync reports to md-site ==="

# 1. Clean content/ synced dirs (keep manifest.json and hello.md)
for dir in "${SYNC_DIRS[@]}"; do
  rm -rf "$CONTENT_DIR/$dir"
done

# 2. Copy .md files from specified directories
cd "$MARKET_DIR"
for dir in "${SYNC_DIRS[@]}"; do
  [ -d "$dir" ] || continue
  find "$dir" -name "*.md" -type f | while read -r src; do
    base=$(basename "$src" | tr '[:upper:]' '[:lower:]')
    # skip ignored files
    skip=false
    for ign in "${IGNORE_FILES[@]}"; do
      [ "$base" = "$ign" ] && skip=true && break
    done
    $skip && continue
    dest="$CONTENT_DIR/$src"
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "  synced: $src"
  done
done

# 3. Generate manifest.json — grouped by directory
python3 - "$CONTENT_DIR" "${SYNC_DIRS[@]}" <<'PYEOF'
import os, sys, json

content_dir = sys.argv[1]
sync_dirs = sys.argv[2:]
ignore = {'readme.md', 'hello.md', 'guide.md'}

groups = {}  # dir_label -> [{file, title}]

for sdir in sync_dirs:
    walk_root = os.path.join(content_dir, sdir)
    if not os.path.isdir(walk_root):
        continue
    for root, dirs, files in sorted(os.walk(walk_root)):
        for f in sorted(files):
            if not f.endswith('.md') or f.lower() in ignore:
                continue
            rel = os.path.relpath(os.path.join(root, f), content_dir).replace('\\', '/')
            # group label from directory path
            parts = rel.split('/')
            if len(parts) == 1:
                label = sdir.replace('/', ' / ').replace('-', ' ').title()
            else:
                label = ' / '.join(p.replace('-', ' ').title() for p in parts[:-1])
            title = f.replace('.md', '')
            if not title[0].isdigit():
                title = title.replace('-', ' ').title()
            groups.setdefault(label, []).append({'file': rel, 'title': title})

# build manifest with group headers
manifest = []
for label, items in groups.items():
    manifest.append({'group': label, 'pages': items})

with open(os.path.join(content_dir, 'manifest.json'), 'w') as fp:
    json.dump(manifest, fp, indent=2, ensure_ascii=False)
total = sum(len(g['pages']) for g in manifest)
print(f"  manifest: {total} pages in {len(manifest)} groups")
PYEOF

# 4. Run static build
echo "=== Building static site ==="
cd "$SITE_DIR"
pip install markdown -q 2>/dev/null || true
python3 build.py

# 5. Git commit & push
echo "=== Sync to GitHub ==="
TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
git add -A
if git diff --cached --quiet; then
  echo "  nothing to commit"
else
  CHANGED=$(git diff --cached --stat | tail -1)
  git commit -m "sync: update reports $(date +%Y-%m-%d)"
  git push -q
  echo "  pushed: $CHANGED"
fi

echo "=== Done ==="
