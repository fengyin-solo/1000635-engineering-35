#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# .venv 可能缺失，也可能是从别的机器/系统拷来的（解释器路径对不上），
# 先验证能跑再用，不能跑就重建，避免报出看不懂的 "not found"。
venv_usable() {
  [ -x .venv/bin/python ] && .venv/bin/python -c '' >/dev/null 2>&1
}

create_venv() {
  if python3 -m venv .venv >/dev/null 2>&1; then
    return
  fi
  # 有的系统（如 Debian 未装 python3-venv）缺 ensurepip，退化为手动引导 pip。
  echo "python3 无法直接创建带 pip 的虚拟环境，改用 --without-pip 并引导 pip…"
  rm -rf .venv
  python3 -m venv --without-pip .venv
  get_pip="$(mktemp)"
  .venv/bin/python -c "from urllib.request import urlretrieve; urlretrieve('https://bootstrap.pypa.io/get-pip.py', '$get_pip')"
  .venv/bin/python "$get_pip" -q
  rm -f "$get_pip"
}

if ! venv_usable; then
  if [ -d .venv ]; then
    echo "检测到 .venv 不可用（可能是在其他系统上创建的），正在重建…"
    rm -rf .venv
  else
    echo "未发现 .venv，正在创建虚拟环境…"
  fi
  create_venv
fi

.venv/bin/pip install -q -r requirements.txt

# 启动自检：依赖、示例数据、流转环节配置有任何缺失都会在这里报出并中止，
# 不会把服务停在半启动状态。
.venv/bin/python -m app.selfcheck

exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
