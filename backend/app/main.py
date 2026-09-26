"""实验室样品检测平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
启动自检：GET /api/selfcheck（启动前也会自动执行，未通过则拒绝启动）
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import selfcheck
from app.config import settings
from app.routers import ROUTERS
from app.store import store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动前先跑自检：缺依赖、缺示例数据或流转环节配置不齐时直接拒绝启动。

    在 lifespan 里抛异常会让 uvicorn 启动失败并整体退出，不会把服务停在
    端口已监听但数据没就绪的半启动状态。
    """
    problems = selfcheck.run()
    if problems:
        raise RuntimeError(
            "启动自检未通过，服务不会以半启动状态对外提供：\n" + selfcheck.format_report(problems)
        )
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
def selfcheck_status() -> dict[str, object]:
    """启动自检结果：依赖、示例数据、流转环节配置缺什么、怎么修，一目了然。"""
    problems = selfcheck.run()
    return {"ok": not problems, "problems": [asdict(problem) for problem in problems]}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
