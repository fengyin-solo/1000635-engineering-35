"""样品流转共用规则：流转环节可选集合、交接人名册、流转编号生成与状态判定。

之前这些规则散在路由、服务与示例数据里各写一份，换环境就对不上。现在统一收在
这里：登记流转记录、执行发起交接/确认接收/取消交接/退回样品，以及启动自检，
都引用同一份配置与同一套判定函数。
"""
from __future__ import annotations

import re
from typing import Any, NamedTuple

# 流转环节的可选集合：登记流转记录时只能从这里选，自检也会核对示例数据是否都在集合内。
TRANSFER_STEPS = ["收样登记", "前处理", "检测分析", "留样保存", "样品处置"]

# 交接人名册：归属校验只认名册内成员，不在名册里的交接人会被拦下。
HANDLERS = ["张伟", "李静", "王强", "赵敏"]

# 流转编号规则：前缀 + 四位序号，例如 STOC-0001；留空由系统按现有记录续号。
CODE_PREFIX = "STOC"
CODE_PATTERN = re.compile(rf"^{CODE_PREFIX}-\d{{4}}$")

# 样品流转的状态序列与终态：进入终态后不再有待办。
STATUS_ORDER = ["待交接", "流转中", "已接收", "已退回"]
TERMINAL_STATUSES = ["已接收", "已退回"]

# 动作 → (目标状态, 允许的前置状态)。取消交接与退回样品同样走这张表判定。
ACTION_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "发起交接": ("流转中", ("待交接",)),
    "确认接收": ("已接收", ("流转中",)),
    "取消交接": ("待交接", ("流转中",)),
    "退回样品": ("已退回", ("待交接", "流转中")),
}

# 会让记录进入异常态的动作；异常状态集合由它推导，示例数据自检也按这个口径核对。
NEGATIVE_ACTIONS = ["退回样品"]
ABNORMAL_STATUSES = sorted({ACTION_RULES[action][0] for action in NEGATIVE_ACTIONS})


class Decision(NamedTuple):
    """一次动作判定结果：目标状态、待办与异常标记，以及需要一并落库的字段。"""

    status: str
    pending: bool
    abnormal: bool
    updates: dict[str, Any]


def next_code(rows: list[dict[str, Any]]) -> str:
    """按现有记录生成下一个流转编号，保证不重号。"""
    used = []
    for row in rows:
        code = str(row.get("流转编号") or "")
        if CODE_PATTERN.match(code):
            used.append(int(code.rsplit("-", 1)[1]))
    return f"{CODE_PREFIX}-{max(used, default=0) + 1:04d}"


def validate_code(code: str, rows: list[dict[str, Any]]) -> str | None:
    """校验手工指定的流转编号；合法返回 None，否则返回错误说明。"""
    if not CODE_PATTERN.match(code):
        return f"流转编号「{code}」格式不对，应为 {CODE_PREFIX}-加四位数字（如 {CODE_PREFIX}-0001），留空可自动生成"
    if any(str(row.get("流转编号") or "") == code for row in rows):
        return f"流转编号「{code}」已被占用，请更换或留空自动生成"
    return None


def validate_step(step: str) -> str | None:
    """校验流转环节是否在可选集合内；合法返回 None，否则返回错误说明。"""
    if step not in TRANSFER_STEPS:
        return f"流转环节「{step}」不在可选集合里，可选：{'、'.join(TRANSFER_STEPS)}"
    return None


def validate_handler(name: str) -> str | None:
    """交接人归属校验：必须在名册内；合法返回 None，否则返回错误说明。"""
    if not name:
        return "交接人不能为空，请从名册中选择：" + "、".join(HANDLERS)
    if name not in HANDLERS:
        return f"交接人「{name}」不在名册里，可选：{'、'.join(HANDLERS)}"
    return None


def decide_action(
    entry: dict[str, Any],
    action: str,
    values: dict[str, Any] | None = None,
) -> Decision | str:
    """统一的状态判定：发起交接、确认接收、取消交接、退回样品都走这里。

    合法时返回 Decision；不可执行时返回错误说明字符串。
    """
    rule = ACTION_RULES.get(action)
    if rule is None:
        return f"动作「{action}」不属于样品流转可执行范围"
    target, sources = rule
    if target not in STATUS_ORDER:
        return f"目标状态「{target}」不在允许的状态序列里"
    current = str(entry.get("status") or "")
    if current not in sources:
        return f"当前状态「{current or '未知'}」不能执行「{action}」，需要先处于：{'、'.join(sources)}"
    updates: dict[str, Any] = {}
    if action == "发起交接":
        # 交接人以动作提交值优先、记录登记值兜底，两种来源都按同一份名册校验。
        handler = str((values or {}).get("交接人") or entry.get("交接人") or "").strip()
        problem = validate_handler(handler)
        if problem:
            return problem
        updates["交接人"] = handler
    return Decision(
        status=target,
        pending=target not in TERMINAL_STATUSES,
        abnormal=target in ABNORMAL_STATUSES,
        updates=updates,
    )
