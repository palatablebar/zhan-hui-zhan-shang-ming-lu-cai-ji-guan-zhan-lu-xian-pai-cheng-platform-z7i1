"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.exhibitors import router as exhibitors_router
from src.routes.exports import router as exports_router
from src.routes.health import router as health_router
from src.routes.overview import router as overview_router
from src.routes.route_runs import router as route_runs_router
from src.routes.sessions import router as sessions_router
from src.routes.visits import router as visits_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(exhibitors_router)
api_router.include_router(sessions_router)
api_router.include_router(route_runs_router)
api_router.include_router(visits_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)
