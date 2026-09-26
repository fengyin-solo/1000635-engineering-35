"""样品流转共用规则：环节集合、编号生成、交接人校验与状态判定只维护这一份。

之前这些规则散在路由、服务和前端页面里，改一处漏一处。现在统一收拢到本模块：
- FLOW_STEPS：流转环节的可选集合，登记与自检都以此为准；
- STAFF_ROSTER：交接人/接收人的归属名册，归属校验的唯一依据；
- next_transfer_no / validate_transfer_no：流转编号生成与校验；
- validate_handover：交接人、接收人的归属校验；
- resolve_transition：发起交接、确认接收、取消交接、退回样品共用同一套状态判定。
"""
from __future__ import annotations

import re
from typing import Any

MODULE = "stockin"

# 流转环节的可选集合：登记流转记录时只能从这里选，自检会核对示例数据是否都用集合内的值。
FLOW_STEPS = ["采样接收", "入库暂存", "分发检测", "留样归档"]

# 实验室人员名册：交接人与接收人必须归属在册，且不能是同一个人。
STAFF_ROSTER = ["张伟", "李娜", "王强", "赵敏", "陈杰"]

STATUS_ORDER = ["待交接", "流转中", "已接收", "已退回"]
TERMINAL_STATUSES = {"已接收", "已退回"}

# 动作 -> 目标状态；取消交接与退回样品也走这张表，不再各自特判。
ACTION_RULES = {
    "发起交接": "流转中",
    "确认接收": "已接收",
    "取消交接": "待交接",
    "退回样品": "已退回",
}

# 状态判定：当前状态允许执行哪些动作。终态（已接收、已退回）不再允许任何动作。
ALLOWED_TRANSITIONS = {
    "待交接": ["发起交接"],
    "流转中": ["确认接收", "取消交接", "退回样品"],
    "已接收": [],
    "已退回": [],
}

NEGATIVE_ACTIONS: list[str] = []

TRANSFER_NO_PREFIX = "STOC"
TRANSFER_NO_PATTERN = re.compile(r"^STOC-(\d{4,})$")


def next_transfer_no(rows: list[dict[str, Any]]) -> str:
    """按既有流转记录生成下一个流转编号：取最大序号加一，格式 STOC-0001。"""
    highest = 0
    for row in rows:
        match = TRANSFER_NO_PATTERN.match(str(row.get("流转编号", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{TRANSFER_NO_PREFIX}-{highest + 1:04d}"


def validate_transfer_no(transfer_no: str, rows: list[dict[str, Any]]) -> list[str]:
    """手工指定流转编号时的校验：格式要符合 STOC-数字，且不能与既有记录重复。"""
    problems: list[str] = []
    if not TRANSFER_NO_PATTERN.match(transfer_no):
        problems.append(f"流转编号「{transfer_no}」格式不正确，应为 {TRANSFER_NO_PREFIX}-数字（如 {TRANSFER_NO_PREFIX}-0004）")
    elif any(str(row.get("流转编号", "")) == transfer_no for row in rows):
        problems.append(f"流转编号「{transfer_no}」已存在，请留空由系统自动生成或换一个编号")
    return problems


def validate_flow_step(step: str) -> list[str]:
    """流转环节必须落在可选集合 FLOW_STEPS 里。"""
    if step not in FLOW_STEPS:
        return [f"流转环节「{step}」不在可选集合里，可选值：{'、'.join(FLOW_STEPS)}"]
    return []


def validate_handover(handover: str, receiver: str) -> list[str]:
    """交接人归属校验：两人都要在册，且交接人与接收人不能是同一个人。"""
    problems: list[str] = []
    for label, person in (("交接人", handover), ("接收人", receiver)):
        if not person:
            problems.append(f"{label}不能为空")
        elif person not in STAFF_ROSTER:
            problems.append(f"{label}「{person}」不在实验室人员名册里，名册：{'、'.join(STAFF_ROSTER)}")
    if handover and receiver and handover == receiver:
        problems.append("交接人与接收人不能是同一个人")
    return problems


def resolve_transition(entry: dict[str, Any], action: str) -> tuple[str | None, str]:
    """状态判定：返回 (目标状态, 错误说明)；动作非法或当前状态不允许时目标状态为 None。

    发起交接、确认接收、取消交接、退回样品全部走这里，保证判定口径只有一份。
    """
    if action not in ACTION_RULES:
        return None, f"动作「{action}」不属于样品流转可执行范围，可执行：{'、'.join(ACTION_RULES)}"
    current = str(entry.get("status", ""))
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        return None, f"当前状态「{current}」不在允许的状态序列里"
    if action not in allowed:
        return None, f"当前状态「{current}」不能执行「{action}」，可执行：{'、'.join(allowed) or '无（已终态）'}"
    return ACTION_RULES[action], ""
