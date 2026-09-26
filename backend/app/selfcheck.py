"""本地启动自检：依赖、示例数据、流转环节配置三项齐备才允许对外服务。

用法：
    cd backend && .venv/bin/python -m app.selfcheck

自检通过会打印一行汇总并返回 0；发现问题会逐条列出缺什么、怎么修，并返回 1。
run.sh 与 FastAPI 启动钩子都会调用这里，保证任何入口都不会把服务停在半启动状态。

注意：本模块顶层只允许导入标准库，业务模块（app.*）的导入都放在各个检查函数里，
这样即使依赖没装齐，自检自身也能跑起来并给出修复说明。
"""
from __future__ import annotations

import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"


@dataclass
class Problem:
    """一项自检发现的问题：哪个检查项、缺什么、怎么修。"""

    check: str
    missing: str
    fix: str


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text)
    return tuple(int(part) for part in parts[:3])


def check_dependencies() -> list[Problem]:
    """对照 requirements.txt 逐条确认依赖已安装且版本达标。"""
    problems: list[Problem] = []
    if not REQUIREMENTS_FILE.exists():
        return [Problem(
            "依赖",
            "缺少依赖清单 backend/requirements.txt",
            "恢复 requirements.txt 后执行：cd backend && .venv/bin/pip install -r requirements.txt",
        )]
    install_fix = "cd backend && .venv/bin/pip install -r requirements.txt"
    for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0].strip()
        floor_match = re.search(r">=\s*([0-9][0-9A-Za-z.\-]*)", line)
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(Problem("依赖", f"未安装依赖包「{name}」", install_fix))
            continue
        if floor_match and _version_tuple(installed) < _version_tuple(floor_match.group(1)):
            problems.append(Problem(
                "依赖",
                f"依赖包「{name}」版本过低：已装 {installed}，要求 {line}",
                install_fix,
            ))
    return problems


def check_transfer_config() -> list[Problem]:
    """核对流转环节配置本身是否齐备、闭合。"""
    from app.services import transfer

    fix = "在 backend/app/services/transfer.py 中补齐后重新启动"
    problems: list[Problem] = []
    if not transfer.TRANSFER_STEPS:
        problems.append(Problem("流转环节配置", "流转环节可选集合 TRANSFER_STEPS 为空", fix))
    elif len(set(transfer.TRANSFER_STEPS)) != len(transfer.TRANSFER_STEPS):
        problems.append(Problem("流转环节配置", "流转环节可选集合 TRANSFER_STEPS 存在重复项", fix))
    if not transfer.HANDLERS:
        problems.append(Problem("流转环节配置", "交接人名册 HANDLERS 为空", fix))
    elif len(set(transfer.HANDLERS)) != len(transfer.HANDLERS):
        problems.append(Problem("流转环节配置", "交接人名册 HANDLERS 存在重复成员", fix))
    if not transfer.STATUS_ORDER:
        problems.append(Problem("流转环节配置", "状态序列 STATUS_ORDER 为空", fix))
    known = set(transfer.STATUS_ORDER)
    for status in transfer.TERMINAL_STATUSES:
        if status not in known:
            problems.append(Problem("流转环节配置", f"终态「{status}」不在状态序列 STATUS_ORDER 里", fix))
    if not transfer.ACTION_RULES:
        problems.append(Problem("流转环节配置", "动作规则 ACTION_RULES 为空", fix))
    for action, (target, sources) in transfer.ACTION_RULES.items():
        if target not in known:
            problems.append(Problem("流转环节配置", f"动作「{action}」的目标状态「{target}」不在状态序列里", fix))
        unknown = [status for status in sources if status not in known]
        if not sources or unknown:
            problems.append(Problem(
                "流转环节配置",
                f"动作「{action}」的前置状态为空或越界：{'、'.join(unknown) or '空'}",
                fix,
            ))
    if not transfer.CODE_PATTERN.match(transfer.next_code([])):
        problems.append(Problem("流转环节配置", "流转编号生成结果不符合编号格式 CODE_PATTERN", fix))
    return problems


def check_seed_data() -> list[Problem]:
    """核对示例数据：每个模块都有数据，样品流转示例与流转配置对得上。"""
    problems: list[Problem] = []
    try:
        from app.routers import ROUTERS
        from app.seed import SEED_ROWS
        from app.services import transfer
    except Exception as exc:  # 业务代码导不进来时，先报这个而不是让自检自己崩掉
        return [Problem(
            "示例数据",
            f"业务模块导入失败：{exc}",
            "先按依赖检查项的说明修复环境，再重新执行 python -m app.selfcheck",
        )]

    seed_fix = "在 backend/app/seed.py 的 SEED_ROWS 中补齐后重新启动"
    expected = sorted(module.router.prefix.rsplit("/", 1)[-1] for module in ROUTERS)
    for name in expected:
        if not SEED_ROWS.get(name):
            problems.append(Problem("示例数据", f"SEED_ROWS 缺少「{name}」模块的示例记录", seed_fix))

    sample_codes = {str(row.get("样品编号") or "") for row in SEED_ROWS.get("sample", [])}
    seen_codes: set[str] = set()
    for row in SEED_ROWS.get("stockin", []):
        label = str(row.get("流转编号") or f"id={row.get('id')}")
        code = str(row.get("流转编号") or "")
        if not transfer.CODE_PATTERN.match(code):
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的流转编号格式不对，应为 {transfer.CODE_PREFIX}-加四位数字",
                seed_fix,
            ))
        elif code in seen_codes:
            problems.append(Problem("示例数据", f"流转编号「{code}」在示例数据里重复", seed_fix))
        seen_codes.add(code)
        step = str(row.get("流转环节") or "")
        problem = transfer.validate_step(step)
        if problem:
            problems.append(Problem("示例数据", f"流转记录 {label}：{problem}", seed_fix))
        problem = transfer.validate_handler(str(row.get("交接人") or "").strip())
        if problem:
            problems.append(Problem("示例数据", f"流转记录 {label}：{problem}", seed_fix))
        status = str(row.get("status") or "")
        if status not in transfer.STATUS_ORDER:
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的状态「{status}」不在状态序列里",
                seed_fix,
            ))
            continue
        if bool(row.get("pending")) != (status not in transfer.TERMINAL_STATUSES):
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的 pending 标记与状态「{status}」不一致",
                seed_fix,
            ))
        if bool(row.get("abnormal")) != (status in transfer.ABNORMAL_STATUSES):
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的 abnormal 标记与状态「{status}」不一致",
                seed_fix,
            ))
        if str(row.get("流转状态") or "") != status:
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的流转状态与状态「{status}」对不上",
                seed_fix,
            ))
        sample = str(row.get("关联样品") or "")
        if sample not in sample_codes:
            problems.append(Problem(
                "示例数据",
                f"流转记录 {label} 的关联样品「{sample}」在样品受理示例数据里不存在",
                "把关联样品改成 sample 模块里存在的样品编号，或先在 sample 模块补上对应样品",
            ))
    return problems


def run() -> list[Problem]:
    """按 依赖 → 流转环节配置 → 示例数据 的顺序自检；依赖不齐时直接短路。"""
    problems = check_dependencies()
    if problems:
        return problems
    return check_transfer_config() + check_seed_data()


def format_report(problems: list[Problem]) -> str:
    lines = ["启动自检未通过，缺少以下配置："]
    for index, problem in enumerate(problems, start=1):
        lines.append(f"  {index}. [{problem.check}] {problem.missing}")
        lines.append(f"     修复：{problem.fix}")
    lines.append("全部补齐后重新启动即可。")
    return "\n".join(lines)


def summary() -> str:
    from app.seed import SEED_ROWS
    from app.services import transfer

    requirements = [
        line.strip()
        for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return (
        f"自检通过：依赖 {len(requirements)} 项、示例数据 {len(SEED_ROWS)} 个模块、"
        f"流转环节 {len(transfer.TRANSFER_STEPS)} 个、交接人 {len(transfer.HANDLERS)} 名均在位"
    )


def main() -> int:
    problems = run()
    if problems:
        print(format_report(problems), file=sys.stderr)
        return 1
    print(summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
