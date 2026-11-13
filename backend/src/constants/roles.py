"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "展会管理员",
    Role.ANALYST.value: "观展专员",
    Role.VIEWER.value: "业务只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护展商名录与优先级、批量导入、导出联系人、查看审计",
    Role.ANALYST.value: "运行路线排程、调整顺序、处理预约冲突、复核路线",
    Role.VIEWER.value: "只读查看名录与路线（联系人电话脱敏），不能运行或改序",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "exhibitor:read", "exhibitor:write",
        "session:read",
        "route:read", "route:create",
        "visit:read", "visit:review",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "exhibitor:read",
        "session:read",
        "route:read", "route:create",
        "visit:read", "visit:review",
        "export:read", "overview:read",
    },
    Role.VIEWER.value: {
        "exhibitor:read", "session:read", "route:read", "visit:read", "overview:read",
    },
}

EXHIBITOR_WRITE_ROLES = (Role.ADMIN.value,)
ROUTE_CREATE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())
