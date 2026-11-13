"""批次补录控制器：登记、发布（整批校验 + 一次性切换）、回滚、隔离行与版本查询。

发布在单个数据库事务内完成；内部用 SAVEPOINT 包裹切换动作，使「发布失败」也能
持久化批次失败标记，而名录与旧版本指针随事务回滚保持原样，不丢任何数据。
"""
from __future__ import annotations

import os
import tempfile

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.import_batch import BATCH_PUBLISHED, ImportBatch
from src.services import audit_service
from src.services.batch_import import importer, readers
from src.services.batch_import.normalizer import REASON_LABELS
from src.utils.errors import AppError


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def register_from_rows(
    db: Session,
    rows: list[dict],
    *,
    batch_code: str,
    source_name: str,
    source_sha256: str,
    mode: str,
    principal: dict,
) -> dict:
    batch = importer.register_batch(
        db,
        rows,
        source_name=source_name,
        source_sha256=source_sha256,
        batch_code=batch_code,
        mode=mode,
        created_by=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="import.register",
        entity="import_batch",
        entity_id=batch.id,
        detail={
            "batch_code": batch_code,
            "mode": mode,
            "source_rows": batch.total_rows,
            "valid": batch.valid_count,
            "quarantine": batch.quarantine_count,
        },
    )
    db.commit()
    return importer.serialize_batch(db, batch)


def register_from_upload(db: Session, content: bytes, filename: str, *, batch_code: str, mode: str, principal: dict) -> dict:
    """把上传字节落到独立临时目录再解析（来源文件视为不可信数据）。"""
    suffix = os.path.splitext(filename)[1] or ".csv"
    with tempfile.TemporaryDirectory(prefix="boothmap_import_") as tmpdir:
        path = os.path.join(tmpdir, f"source{suffix}")
        with open(path, "wb") as handle:
            handle.write(content)
        rows = readers.read_rows(path)
        sha = readers.source_sha256(path)
    return register_from_rows(
        db,
        rows,
        batch_code=batch_code,
        source_name=filename,
        source_sha256=sha,
        mode=mode,
        principal=principal,
    )


def publish(db: Session, batch_id: int, principal: dict, request: Request) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise AppError("NOT_FOUND", 404, {"entity": "import_batch", "id": batch_id})

    # 幂等快路径：已发布直接回传，重复重跑不新增、不覆盖
    if batch.status == BATCH_PUBLISHED and batch.published_version_id:
        version = importer.get_version(db, batch.published_version_id)
        return {"batch": importer.serialize_batch(db, batch), "version": _version_brief(version), "idempotent": True}

    # 整批校验在 SAVEPOINT 之外：结构性失败时 FAILED 标记可独立提交，名录完全不动
    try:
        batch, reconciliation = importer.precheck_publish(db, batch_id)
    except Exception:
        db.commit()
        raise

    # 切换动作放进 SAVEPOINT：任何异常只回滚切换，旧版本保持 active、展商行不丢失
    savepoint = db.begin_nested()
    try:
        version = importer.apply_publish(
            db, batch, reconciliation, created_by=principal["email"], principal=principal, ip=_client_ip(request)
        )
    except AppError:
        savepoint.rollback()
        db.commit()
        raise
    except Exception as exc:  # 转成统一业务异常，避免穿透中间件 TaskGroup
        savepoint.rollback()
        batch.status = "failed"
        batch.error_text = "发布过程异常，已回滚到旧版名录，未产生数据丢失"
        db.commit()
        raise AppError("INTERNAL", 500, {"message": batch.error_text, "reason": str(exc)[:200]})
    savepoint.commit()
    db.commit()
    return {"batch": importer.serialize_batch(db, batch), "version": _version_brief(version), "idempotent": False}


def rollback(db: Session, version_id: int, principal: dict, request: Request) -> dict:
    version = importer.rollback_to_version(
        db, version_id, created_by=principal["email"], principal=principal, ip=_client_ip(request)
    )
    db.commit()
    return _version_brief(version)


def list_batches(db: Session) -> dict:
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
    return {"items": [importer.serialize_batch(db, batch) for batch in batches], "total": len(batches)}


def get_batch(db: Session, batch_id: int) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise AppError("NOT_FOUND", 404, {"entity": "import_batch", "id": batch_id})
    data = importer.serialize_batch(db, batch)
    data["staging"] = importer.list_staging(db, batch_id)
    data["quarantine_reason_labels"] = REASON_LABELS
    return data


def list_versions(db: Session) -> dict:
    return {"items": importer.list_versions(db), "active": _active_brief(db)}


def _active_brief(db: Session) -> dict | None:
    version = importer.get_active_version(db)
    return _version_brief(version) if version else None


def _version_brief(version) -> dict | None:
    if version is None:
        return None
    return {
        "id": version.id,
        "version_no": version.version_no,
        "label": version.label,
        "status": version.status,
        "exhibitor_count": version.exhibitor_count,
    }
