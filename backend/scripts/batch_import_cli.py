"""批次补录命令行：登记 → 整批校验 → 一次性发布切换；失败自动回滚旧版名录。

用法（在 backend 目录、已配置好数据库环境变量）：

    python -m scripts.batch_import_cli register /path/to/batch.csv --code B20261113-01
    python -m scripts.batch_import_cli publish  B20261113-01
    python -m scripts.batch_import_cli run      /path/to/batch.csv --code B20261113-01   # 登记+发布
    python -m scripts.batch_import_cli batches
    python -m scripts.batch_import_cli staging  B20261113-01 --status quarantine
    python -m scripts.batch_import_cli versions
    python -m scripts.batch_import_cli rollback <version_id>

来源文件按不可信数据处理：路径只作为参数传入，本脚本不切换到该目录执行任何代码。
重复批次（同 --code）重跑为幂等 no-op：不新增、不覆盖人工修改。
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from src.config.database import session_scope
from src.models.import_batch import ImportBatch
from src.services.batch_import import importer, readers

SYSTEM_PRINCIPAL = {"email": "cli@boothmap.io", "role": "admin"}


def _find_batch(db, code_or_id: str) -> ImportBatch:
    if code_or_id.isdigit():
        batch = db.get(ImportBatch, int(code_or_id))
    else:
        batch = db.scalar(select(ImportBatch).where(ImportBatch.batch_code == code_or_id))
    if batch is None:
        raise SystemExit(f"找不到批次：{code_or_id}")
    return batch


def cmd_register(args) -> None:
    rows = readers.read_rows(args.file)
    sha = readers.source_sha256(args.file)
    with session_scope() as db:
        batch = importer.register_batch(
            db,
            rows,
            source_name=args.file,
            source_sha256=sha,
            batch_code=args.code,
            mode=args.mode,
            created_by=SYSTEM_PRINCIPAL["email"],
        )
        data = importer.serialize_batch(db, batch)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"[register] 批次 {args.code}：来源 {data['total_rows']} 行，"
          f"好行 {data['valid_count']}，隔离 {data['quarantine_count']}")


def cmd_publish(args) -> None:
    with session_scope() as db:
        batch = _find_batch(db, args.code)
        if batch.status == "published" and batch.published_version_id:
            version = importer.get_version(db, batch.published_version_id)
            print(f"[publish] 批次 {batch.batch_code} 已发布（幂等 no-op），版本 v{version.version_no}")
            return
        try:
            version = importer.publish_batch(db, batch.id, created_by=SYSTEM_PRINCIPAL["email"],
                                             principal=SYSTEM_PRINCIPAL)
        except Exception as exc:  # noqa: BLE001 - CLI 需要把失败原因打印出来
            db.rollback()
            print(f"[publish] 发布失败，已保持/恢复旧版名录，无数据丢失：{exc}", file=sys.stderr)
            raise SystemExit(2)
        data = importer.serialize_batch(db, batch)
        print(json.dumps({"batch": data, "version_no": version.version_no,
                          "member_count": version.exhibitor_count}, ensure_ascii=False, indent=2))
        print(f"[publish] 已切换到 v{version.version_no}：新增 {data['inserted_count']}，"
              f"合并跳过 {data['merged_count']}，隔离 {data['quarantine_count']}")


def cmd_run(args) -> None:
    cmd_register(args)
    cmd_publish(args)


def cmd_batches(_args) -> None:
    with session_scope() as db:
        rows = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
        for batch in rows:
            print(f"#{batch.id} {batch.batch_code} [{batch.status}] mode={batch.mode} "
                  f"来源={batch.total_rows} 好行={batch.valid_count} 隔离={batch.quarantine_count} "
                  f"新增={batch.inserted_count} 合并={batch.merged_count} 版本={batch.published_version_id}")


def cmd_staging(args) -> None:
    with session_scope() as db:
        batch = _find_batch(db, args.code)
        items = importer.list_staging(db, batch.id, status=args.status)
    print(json.dumps(items, ensure_ascii=False, indent=2))


def cmd_versions(_args) -> None:
    with session_scope() as db:
        for item in importer.list_versions(db):
            flag = " *ACTIVE*" if item["is_active"] else ""
            print(f"v{item['version_no']} (#{item['id']}) [{item['status']}]{flag} "
                  f"成员={item['exhibitor_count']} {item['label']}")


def cmd_rollback(args) -> None:
    with session_scope() as db:
        version = importer.rollback_to_version(db, int(args.version_id),
                                               created_by=SYSTEM_PRINCIPAL["email"], principal=SYSTEM_PRINCIPAL)
        print(f"[rollback] 已回滚到 v{version.version_no}，成员 {version.exhibitor_count} 家（展商行未删除）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="展商名录批次补录与版本切换")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_code(sp):
        sp.add_argument("--code", required=True, help="批次业务编号（幂等键，重复重跑不新增/覆盖）")
        sp.add_argument("--mode", choices=["supplement", "snapshot"], default="supplement")

    sp_register = sub.add_parser("register", help="登记批次（清洗/隔离/查重，不写正式名录）")
    sp_register.add_argument("file")
    add_code(sp_register)
    sp_register.set_defaults(func=cmd_register)

    sp_publish = sub.add_parser("publish", help="整批校验通过后一次性发布切换")
    sp_publish.add_argument("code")
    sp_publish.set_defaults(func=cmd_publish)

    sp_run = sub.add_parser("run", help="登记并发布（一步到位，失败回滚）")
    sp_run.add_argument("file")
    add_code(sp_run)
    sp_run.set_defaults(func=cmd_run)

    sp_batches = sub.add_parser("batches", help="列出全部批次与核对数量")
    sp_batches.set_defaults(func=cmd_batches)

    sp_staging = sub.add_parser("staging", help="查看批次暂存/隔离行及原因")
    sp_staging.add_argument("code")
    sp_staging.add_argument("--status", choices=["valid", "quarantine"], default=None)
    sp_staging.set_defaults(func=cmd_staging)

    sp_versions = sub.add_parser("versions", help="列出名录版本")
    sp_versions.set_defaults(func=cmd_versions)

    sp_rollback = sub.add_parser("rollback", help="回滚到指定名录版本")
    sp_rollback.add_argument("version_id", type=int)
    sp_rollback.set_defaults(func=cmd_rollback)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
