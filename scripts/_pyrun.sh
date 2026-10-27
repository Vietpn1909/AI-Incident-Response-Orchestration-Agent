#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

# Chọn Python >= 3.10. Script log dùng cú pháp `X | None` (3.10+) và
# `datetime.UTC` (3.11+), nên một `python3` cũ sẽ CRASH — mà hook gọi kèm
# `|| true` nên push vẫn qua và KHÔNG BÁO GÌ. Hậu quả: AI log chỉ ghi vào máy,
# không bao giờ gửi lên server chấm.
#
# Đã xảy ra thật ngày 26/08 trên macOS: `python3` trên PATH là 3.9.6 của Xcode,
# trong khi repo có .venv 3.11.4. Mất deliverable mà không ai biết.
_du_moi() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=""
for cand in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/.venv/Scripts/python.exe" python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && _du_moi "$cand"; then PY="$cand"; break; fi
done

if [ -n "$PY" ]; then
  : # đã tìm được bản đủ mới
elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
  echo "⚠️  _pyrun.sh: chỉ tìm thấy $(python3 -V 2>&1), cần >= 3.10 — AI log SẼ KHÔNG GỬI ĐƯỢC." >&2
  PY=python3
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
  PY=python
elif command -v py >/dev/null 2>&1 && py -3 --version >/dev/null 2>&1; then
  PY="py -3"
else
  # PATH lookup failed — probe standard Windows install locations.
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
