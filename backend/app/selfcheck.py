"""启动自检：依赖、运行配置、示例数据与流转环节配置，缺什么报什么并给出修复说明。

用法：
    python -m app.selfcheck          # 打印报告，全部通过退出码 0，否则 1

设计约束：本模块只依赖标准库与 app 内部的纯数据模块（config / seed / transfer /
services），不 import fastapi。这样即使依赖没装齐，自检也能跑起来并明确报出
缺的是哪一步，而不是直接 ImportError 把人挡在门外。
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field

MIN_PYTHON = (3, 10)
REQUIRED_PACKAGES = ["fastapi", "uvicorn", "pydantic"]
SERVICE_MODULES = [
    "sample", "client", "project", "task", "execute", "result", "review",
    "instrument", "calibration", "reagent", "consume", "environment",
    "report", "issue", "qc", "complaint", "stockin", "settlement",
]


@dataclass
class Problem:
    detail: str  # 缺什么 / 哪里不对
    fix: str     # 怎么修


@dataclass
class CheckResult:
    name: str
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_python_version() -> CheckResult:
    result = CheckResult("Python 版本")
    current = sys.version_info
    if current < MIN_PYTHON:
        result.problems.append(Problem(
            detail=f"当前 Python {current.major}.{current.minor}.{current.micro}，低于要求的 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+",
            fix="安装 Python 3.10 或更高版本后重新执行 backend/run.sh",
        ))
    return result


def check_dependencies() -> CheckResult:
    result = CheckResult("后端依赖")
    for package in REQUIRED_PACKAGES:
        try:
            module = importlib.import_module(package)
            _ = getattr(module, "__version__", "")
        except ImportError:
            result.problems.append(Problem(
                detail=f"缺少依赖包「{package}」，接口服务无法启动",
                fix="执行 cd backend && ./run.sh 自动安装，或手动运行 .venv/bin/pip install -r requirements.txt",
            ))
    return result


def check_settings() -> CheckResult:
    from app.config import settings

    result = CheckResult("运行配置")
    if not (1 <= settings.port <= 65535):
        result.problems.append(Problem(
            detail=f"服务端口 {settings.port} 不在 1–65535 范围内",
            fix="修正 backend/app/config.py 中 Settings.port",
        ))
    if not settings.allowed_origins:
        result.problems.append(Problem(
            detail="跨域白名单 allowed_origins 为空，前端页面将无法访问接口",
            fix="在 backend/app/config.py 的 Settings.allowed_origins 里补上前端地址（如 http://127.0.0.1:5173）",
        ))
    if settings.page_size_default > settings.page_size_max:
        result.problems.append(Problem(
            detail=f"默认分页 {settings.page_size_default} 超过上限 {settings.page_size_max}",
            fix="调整 backend/app/config.py 中 page_size_default / page_size_max",
        ))
    return result


def check_seed_rows() -> CheckResult:
    from app.seed import SEED_ROWS

    result = CheckResult("示例数据")
    for name in SERVICE_MODULES:
        service = importlib.import_module(f"app.services.{name}")
        rows = SEED_ROWS.get(name)
        if not rows:
            result.problems.append(Problem(
                detail=f"模块「{name}」没有示例数据，列表页打开是空的",
                fix=f"在 backend/app/seed.py 的 SEED_ROWS 里补上「{name}」的示例记录",
            ))
            continue
        status_order = getattr(service, "STATUS_ORDER", [])
        required = getattr(service, "REQUIRED_FIELDS", [])
        for row in rows:
            label = f"模块「{name}」记录 id={row.get('id', '?')}"
            for key in ("id", "status", "pending", "abnormal"):
                if key not in row:
                    result.problems.append(Problem(
                        detail=f"{label} 缺少基础字段「{key}」",
                        fix=f"在 backend/app/seed.py 中给该记录补上「{key}」",
                    ))
            if status_order and row.get("status") not in status_order:
                result.problems.append(Problem(
                    detail=f"{label} 的状态「{row.get('status')}」不在状态序列 {status_order} 里",
                    fix="修正 backend/app/seed.py 中该记录的 status，或调整对应 service 的 STATUS_ORDER",
                ))
            for field_name in required:
                if not str(row.get(field_name) or "").strip():
                    result.problems.append(Problem(
                        detail=f"{label} 的必填字段「{field_name}」为空",
                        fix="在 backend/app/seed.py 中补全该记录的必填字段",
                    ))
    return result


def check_transfer_config() -> CheckResult:
    from app import transfer
    from app.seed import SEED_ROWS

    result = CheckResult("流转环节配置")
    if not transfer.FLOW_STEPS:
        result.problems.append(Problem(
            detail="流转环节可选集合 FLOW_STEPS 为空，登记流转记录时没有环节可选",
            fix="在 backend/app/transfer.py 的 FLOW_STEPS 里配置环节（如：采样接收、入库暂存、分发检测）",
        ))
    elif len(set(transfer.FLOW_STEPS)) != len(transfer.FLOW_STEPS):
        result.problems.append(Problem(
            detail=f"流转环节可选集合存在重复项：{transfer.FLOW_STEPS}",
            fix="去掉 backend/app/transfer.py 中 FLOW_STEPS 的重复环节",
        ))
    if not transfer.STAFF_ROSTER:
        result.problems.append(Problem(
            detail="人员名册 STAFF_ROSTER 为空，交接人归属校验无法执行",
            fix="在 backend/app/transfer.py 的 STAFF_ROSTER 里登记实验室人员",
        ))

    rows = SEED_ROWS.get("stockin", [])
    sample_ids = {str(row.get("样品编号", "")) for row in SEED_ROWS.get("sample", [])}
    seen_nos: set[str] = set()
    for row in rows:
        label = f"流转记录「{row.get('流转编号', '?')}」"
        step = str(row.get("流转环节", ""))
        if transfer.FLOW_STEPS and step not in transfer.FLOW_STEPS:
            result.problems.append(Problem(
                detail=f"{label} 的流转环节「{step}」不在可选集合 {transfer.FLOW_STEPS} 里，示例数据与流转列表对不上",
                fix="把 backend/app/seed.py 中该记录的流转环节改成 FLOW_STEPS 里的值，或在 backend/app/transfer.py 中补充该环节",
            ))
        for field_name in ("交接人", "接收人"):
            person = str(row.get(field_name, ""))
            if transfer.STAFF_ROSTER and person and person not in transfer.STAFF_ROSTER:
                result.problems.append(Problem(
                    detail=f"{label} 的{field_name}「{person}」不在人员名册里",
                    fix="把 backend/app/seed.py 中该人员改成 STAFF_ROSTER 名册成员，或在 backend/app/transfer.py 中补充名册",
                ))
        no = str(row.get("流转编号", ""))
        if no in seen_nos:
            result.problems.append(Problem(
                detail=f"流转编号「{no}」在示例数据里重复",
                fix="修改 backend/app/seed.py 中重复的流转编号",
            ))
        seen_nos.add(no)
        sample_ref = str(row.get("关联样品", ""))
        if sample_ids and sample_ref and sample_ref not in sample_ids:
            result.problems.append(Problem(
                detail=f"{label} 的关联样品「{sample_ref}」在样品模块里不存在",
                fix="把 backend/app/seed.py 中该记录的关联样品改成 sample 模块已有的样品编号",
            ))
    return result


CHECKS = [
    check_python_version,
    check_dependencies,
    check_settings,
    check_seed_rows,
    check_transfer_config,
]


def run_selfcheck() -> list[CheckResult]:
    return [check() for check in CHECKS]


def format_report(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for result in results:
        if result.ok:
            lines.append(f"  [通过] {result.name}")
        else:
            lines.append(f"  [缺失] {result.name}")
            for problem in result.problems:
                lines.append(f"      问题：{problem.detail}")
                lines.append(f"      修复：{problem.fix}")
    passed = sum(1 for result in results if result.ok)
    lines.append(f"自检结果：{passed}/{len(results)} 项通过")
    return "\n".join(lines)


def has_failures(results: list[CheckResult]) -> bool:
    return any(not result.ok for result in results)


def main() -> int:
    print("启动自检：")
    results = run_selfcheck()
    print(format_report(results))
    if has_failures(results):
        print("存在缺失项，请按上面的修复说明处理后再启动服务。")
        return 1
    print("全部就绪，可以启动服务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
