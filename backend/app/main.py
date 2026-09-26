"""实验室样品检测平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
启动自检：GET /api/selfcheck（启动时也会自动跑一遍，未通过则拒绝启动）
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import selfcheck
from app.config import settings
from app.routers import ROUTERS
from app.store import store

logger = logging.getLogger("app.selfcheck")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """启动自检：依赖、配置、示例数据与流转环节齐备才放行。

    未通过时抛出异常，uvicorn 会在监听端口前终止启动，不会把服务停在半启动状态。
    """
    results = selfcheck.run_selfcheck()
    report = selfcheck.format_report(results)
    if selfcheck.has_failures(results):
        logger.error("启动自检未通过：\n%s", report)
        raise RuntimeError(f"启动自检未通过，服务未启动：\n{report}")
    logger.info("启动自检通过：\n%s", report)
    yield


app = FastAPI(title="实验室样品检测平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/selfcheck")
def selfcheck_report() -> dict[str, object]:
    """启动自检报告：逐项列出依赖、配置、示例数据与流转环节是否齐备。"""
    results = selfcheck.run_selfcheck()
    return {
        "ok": not selfcheck.has_failures(results),
        "checks": [
            {
                "name": result.name,
                "ok": result.ok,
                "problems": [{"detail": p.detail, "fix": p.fix} for p in result.problems],
            }
            for result in results
        ],
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
