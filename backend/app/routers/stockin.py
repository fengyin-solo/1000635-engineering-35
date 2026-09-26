"""样品流转接口：维护流转记录，覆盖发起交接、确认接收、取消交接、退回样品等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services import transfer
from app.services.stockin import StockinService

router = APIRouter(prefix="/api/stockin", tags=["样品流转"])

service = StockinService()

LIST_FIELDS = ["流转编号", "关联样品", "流转环节", "交接人", "接收人", "交接时间", "存放位置", "流转状态"]
STATUSES = transfer.STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按流转编号检索"),
    status: str | None = Query(default=None, description="待交接、流转中、已接收、已退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按流转编号与状态过滤样品流转列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出样品流转清单：返回当前过滤条件下的全量数据。

    必须声明在 /{entry_id} 之前，否则 "export" 会被当成记录 id 抢走。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "stockin", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条流转记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"流转记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条流转记录：流转编号留空自动生成，环节与交接人按共用规则校验。"""
    entry, problems = service.create_entry(payload.values)
    if problems:
        return ActionResult(ok=False, message="；".join(problems))
    return ActionResult(ok=True, message="流转记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条流转记录执行发起交接、确认接收、取消交接、退回样品；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
