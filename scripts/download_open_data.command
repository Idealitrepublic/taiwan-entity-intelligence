#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 Python 3。請先安裝 Python 3，再重新執行。"
  exit 1
fi

echo "T.E.I. 正在從政府資料開放平臺下載公開資料..."
python3 scripts/download_open_data.py

echo ""
echo "下載完成。資料會放在："
pwd
printf '/data/raw\n'
echo "按 Enter 關閉視窗。"
read -r
