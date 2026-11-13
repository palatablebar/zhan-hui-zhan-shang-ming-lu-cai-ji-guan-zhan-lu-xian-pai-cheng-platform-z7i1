"""批次补录路由：登记（上传/JSON）、发布切换、回滚、隔离行与名录版本查询。

全部为名录维护动作，仅 admin 可访问（analyst/viewer 由 RBAC 依赖返回真实 403）。
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EXHIBITOR_WRITE_ROLES
from src.controllers import batch_import_controller as controller
from src.middlewares.rbac import require_roles
from src.models.import_batch import IMPORT_MODES, MODE_SUPPLEMENT
from src.utils.errors import AppError

router = APIRouter(prefix="/imports", tags=["batch-import"])


class BatchRegisterIn(BaseModel):
    batch_code: str = Field(min_length=2, max_length=64)
    source_name: str = Field(default="", max_length=255)
    mode: str = MODE_SUPPLEMENT
    rows: list[dict] = Field(min_length=1)

    def validated_mode(self) -> str:
        if self.mode not in IMPORT_MODES:
            raise AppError("VALIDATION", 422, {"field": "mode", "message": "mode 仅支持 supplement / snapshot"})
        return self.mode


@router.post("/batches", status_code=201)
def register_batch(
    payload: BatchRegisterIn,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    sha = hashlib.sha256(repr(sorted((row or {}).items() for row in payload.rows)).encode("utf-8")).hexdigest()
    return controller.register_from_rows(
        db,
        payload.rows,
        batch_code=payload.batch_code,
        source_name=payload.source_name or f"json:{payload.batch_code}",
        source_sha256=sha,
        mode=payload.validated_mode(),
        principal=principal,
    )


@router.post("/batches/upload", status_code=201)
async def upload_batch(
    request: Request,
    file: UploadFile = File(...),
    batch_code: str = Form(...),
    mode: str = Form(default=MODE_SUPPLEMENT),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    if mode not in IMPORT_MODES:
        raise AppError("VALIDATION", 422, {"field": "mode", "message": "mode 仅支持 supplement / snapshot"})
    content = await file.read()
    if not content:
        raise AppError("VALIDATION", 422, {"field": "file", "message": "上传文件为空"})
    return controller.register_from_upload(
        db, content, file.filename or "source.csv", batch_code=batch_code, mode=mode, principal=principal
    )


@router.get("/batches")
def list_batches(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return controller.list_batches(db)


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return controller.get_batch(db, batch_id)


@router.get("/batches/{batch_id}/staging")
def list_staging(
    batch_id: int,
    status: str | None = None,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    from src.services.batch_import import importer

    controller.get_batch(db, batch_id)  # 存在性校验
    return {"items": importer.list_staging(db, batch_id, status=status)}


@router.post("/batches/{batch_id}/publish")
def publish_batch(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return controller.publish(db, batch_id, principal, request)


@router.get("/directory/versions")
def list_versions(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return controller.list_versions(db)


@router.post("/directory/versions/{version_id}/rollback")
def rollback_version(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return controller.rollback(db, version_id, principal, request)
