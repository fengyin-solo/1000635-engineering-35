#!/usr/bin/env bash
# 本地启动入口：自动补齐虚拟环境与依赖，跑完启动自检再拉起服务。
# 任何一步缺失都会明确报出原因并退出，不会把服务停在半启动状态。
set -euo pipefail
cd "$(dirname "$0")"

PY_BIN="${PYTHON:-python3}"

venv_usable() {
  # .venv 目录存在不代表可用：从别的机器/系统拷贝来的 venv 解释器是悬空的
  [ -x .venv/bin/python ] && .venv/bin/python -c '' >/dev/null 2>&1
}

if ! venv_usable; then
  if [ -d .venv ]; then
    echo "[run] 现有 .venv 无法在当前环境运行（可能是在其他机器上创建的），自动重建…"
    rm -rf .venv
  fi
  if ! "$PY_BIN" -m venv .venv 2>/dev/null; then
    echo "[run] 创建虚拟环境失败：请先安装 Python 3.10+ 及 venv 组件"
    echo "      Debian/Ubuntu: sudo apt install python3-venv"
    exit 1
  fi
fi

echo "[run] 安装/校验依赖…"
if ! .venv/bin/pip install -q -r requirements.txt; then
  echo "[run] 依赖安装失败：请检查网络或 requirements.txt 后重试"
  exit 1
fi

echo "[run] 启动自检…"
if ! .venv/bin/python -m app.selfcheck; then
  echo "[run] 启动自检未通过，服务未启动。"
  exit 1
fi

exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
