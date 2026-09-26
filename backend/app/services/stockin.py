"""样品流转业务规则：编号生成、环节与交接人校验、状态判定统一走 transfer 共用实现。"""
from __future__ import annotations

from typing import Any

from app.services import transfer
from app.store import store

MODULE = "stockin"
REQUIRED_FIELDS = ["关联样品", "流转环节"]
OPTIONAL_FIELDS = ["交接人", "接收人", "交接时间", "存放位置"]
STATUS_ORDER = transfer.STATUS_ORDER


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
        step = str(values.get("流转环节") or "").strip()
        if step:
            problem = transfer.validate_step(step)
            if problem:
                problems.append(problem)
        handler = str(values.get("交接人") or "").strip()
        if handler:
            problem = transfer.validate_handler(handler)
            if problem:
                problems.append(problem)
        code = str(values.get("流转编号") or "").strip()
        if code:
            problem = transfer.validate_code(code, rows)
            if problem:
                problems.append(problem)
        if problems:
            return None, problems
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["流转编号"] = code or transfer.next_code(rows)
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = value
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
        outcome = transfer.decide_action(entry, action, values)
        if isinstance(outcome, str):
            return None, outcome
        entry["status"] = outcome.status
        entry["流转状态"] = outcome.status
        entry["pending"] = outcome.pending
        entry["abnormal"] = outcome.abnormal
        entry.update(outcome.updates)
        return entry, f"流转记录已{action}"
