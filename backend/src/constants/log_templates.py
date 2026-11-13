"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "exhibitor.create": "新增展商",
    "exhibitor.update": "修改展商",
    "route.create": "发起路线排程",
    "route.complete": "路线排程完成",
    "visit.review": "复核观展路线",
    "export.visits": "导出观展清单",
    "http.mutation": "写请求",
}
