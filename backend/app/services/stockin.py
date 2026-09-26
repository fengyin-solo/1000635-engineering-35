"""样品流转业务规则：状态流转、字段校验与筛选口径都收在这里。

环节集合、编号生成、交接人归属与状态判定统一走 app.transfer 的共用实现，
本模块只负责列表筛选、登记组装与动作编排。
"""
from __future__ import annotations

from typing import Any

from app import transfer
from app.store import store

MODULE = transfer.MODULE
REQUIRED_FIELDS = ["关联样品", "流转环节"]
OPTIONAL_FIELDS = ["交接人", "接收人", "交接时间", "存放位置"]
STATUS_ORDER = transfer.STATUS_ORDER
ACTION_RULES = transfer.ACTION_RULES
NEGATIVE_ACTIONS = transfer.NEGATIVE_ACTIONS


class StockinService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("流转编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        rows = store.rows(MODULE)
        problems: list[str] = []
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            problems.append(f"缺少必填字段：{'、'.join(missing)}")

        transfer_no = str(values.get("流转编号") or "").strip()
        if transfer_no:
            problems.extend(transfer.validate_transfer_no(transfer_no, rows))
        else:
            transfer_no = transfer.next_transfer_no(rows)

        step = str(values.get("流转环节") or "").strip()
        if step:
            problems.extend(transfer.validate_flow_step(step))

        handover = str(values.get("交接人") or "").strip()
        receiver = str(values.get("接收人") or "").strip()
        if handover or receiver:
            problems.extend(transfer.validate_handover(handover, receiver))

        if problems:
            return None, problems

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["流转编号"] = transfer_no
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry.update({field: values.get(field) for field in OPTIONAL_FIELDS if values.get(field) is not None})
        entry["status"] = STATUS_ORDER[0]
        entry["流转状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"流转记录 {entry_id} 不存在或已归档"
        target, error = transfer.resolve_transition(entry, action)
        if target is None:
            return None, error

        values = values or {}
        if action == "发起交接":
            handover = str(values.get("交接人") or entry.get("交接人") or "").strip()
            receiver = str(values.get("接收人") or entry.get("接收人") or "").strip()
            problems = transfer.validate_handover(handover, receiver)
            if problems:
                return None, "；".join(problems)
            entry["交接人"] = handover
            entry["接收人"] = receiver

        entry["status"] = target
        entry["流转状态"] = target
        entry["pending"] = target not in transfer.TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"流转记录已{action}"
