#!/usr/bin/env bash
set -euo pipefail

# 进入仓库根目录（脚本位于 script/ 下）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REQ_FILE="$ROOT_DIR/requirements.txt"
VENV_DIR="$ROOT_DIR/.venv"
PY="$VENV_DIR/bin/python"

# pip 源：避免本地默认镜像超时，默认用官方源；如需自定义可在环境变量覆盖
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
}

ensure_deps() {
  if [[ ! -f "$REQ_FILE" ]]; then
    echo "ERROR: 未找到 $REQ_FILE" >&2
    exit 2
  fi

  ensure_venv

  local stamp_file="$VENV_DIR/.requirements.sha256"
  local req_sum
  req_sum="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"

  local old_sum=""
  if [[ -f "$stamp_file" ]]; then
    old_sum="$(cat "$stamp_file" 2>/dev/null || true)"
  fi

  if [[ "$req_sum" != "$old_sum" ]]; then
    "$PY" -m pip install -U pip -i "$PIP_INDEX_URL" >/dev/null
    "$PY" -m pip install -r "$REQ_FILE" -i "$PIP_INDEX_URL"
    echo "$req_sum" > "$stamp_file"
  fi
}

# 输出路径：默认为 market-reports/daily/YYYY-MM-DD.md
TODAY="$(date +%F)"
OUT_DIR="../daily"
OUT_FILE="$OUT_DIR/$TODAY.md"

# mkdir -p "$OUT_DIR"

# 日志（可选）
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily-report.$TODAY.log"

# 执行
ensure_deps
"$PY" "$ROOT_DIR/script/a-share-daily-report.py" "$OUT_FILE" 2>&1 | tee "$LOG_FILE"

echo "OK: $OUT_FILE"
echo "LOG: $LOG_FILE"