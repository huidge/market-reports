#!/bin/bash
# sync-reports.sh — 提交并推送 market-reports 目录的变更到 GitHub
# 用法: bash  ~/.hermes/scripts/sync-reports.sh

set -e
REPORTS_DIR="/Users/huidge/market-reports"
cd "$REPORTS_DIR"

# 检查是否有变更
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "没有新的报告变更，跳过同步"
    exit 0
fi

# 获取今天的日期作为 commit message
TODAY=$(date +%Y-%m-%d)

# 添加所有变更
git add -A
git commit -m "市场报告更新 $TODAY"

# 推送到远程
git push origin main

echo "同步完成: $(git log -1 --oneline)"
