"""演示数据：3 账号 / 186 家展商（8 馆）/ 24 场论坛 / 1 次两日路线排程。

全部由固定常量确定，不随机、不联网；同一份代码两次生成的名单与排程完全一致。
"""
from __future__ import annotations

DEMO_PASSWORD = "Demo@2026"
ORG = "南方工业自动化 · 市场部"

DEMO_USERS = [
    ("admin@boothmap.io", "林可 · 展会管理员", "admin"),
    ("analyst@boothmap.io", "周棠 · 观展专员", "analyst"),
    ("viewer@boothmap.io", "陈默 · 业务只读", "viewer"),
]

# 8 个馆的展商数合计 186
HALL_LAYOUT = [
    ("A1", 24),
    ("A2", 24),
    ("B1", 23),
    ("B2", 23),
    ("C1", 23),
    ("C2", 23),
    ("D1", 23),
    ("D2", 23),
]

HALL_CATEGORY = {
    "A1": "robot",
    "A2": "vision",
    "B1": "drive",
    "B2": "electric",
    "C1": "software",
    "C2": "logistics",
    "D1": "metrology",
    "D2": "robot",
}

CATEGORIES = ["robot", "vision", "drive", "sensor", "software", "logistics", "electric", "metrology"]
INDUSTRIES = ["auto", "electronics", "energy", "food", "general", "pharma"]

BRANDS = [
    "澜川", "恒擎", "钧维", "拓垣", "睿驰", "承光", "泰枢", "启元", "沃驰", "宗岳",
    "昱科", "楷博", "沐辰", "岳衡", "矗峰", "熵行", "砺准", "泓测", "曦望", "祯图",
    "擎矽", "迅澜", "旌阳", "澜石", "砺芯", "韶光", "昀智", "榕基", "榕创", "毓秀",
    "沅启", "泓图", "澈明", "燧石", "磐拓",
]

SUFFIXES = ["智能装备", "视觉科技", "精密传动", "电气自动化", "工业软件", "物流系统"]

SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周", "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗"]
GIVEN = ["磊", "敏", "洋", "静", "波", "颖", "涛", "楠", "晨", "琪", "宇", "菲", "鹏", "倩", "航", "玥", "骁", "岚"]
TITLES = ["市场经理", "销售总监", "产品经理", "渠道经理", "技术总监"]

# (天, 当天第几分钟) —— 预约时段固定 30 分钟硬窗；首条被两位展商同时占用以制造冲突
CONFLICT_SLOT = (1, 630)  # Day1 10:30-11:00
APPOINTMENT_SLOTS = [
    (1, 570), (1, 660), (1, 690), (1, 720), (1, 750), (1, 780), (1, 810), (1, 840), (1, 870),
    (2, 570), (2, 600), (2, 660), (2, 720), (2, 780), (2, 840), (2, 900),
]

PRIORITY_PLAN = {"P0": 34, "P1": 62, "P2": 90}
PRIORITY_DWELL = {"P0": 13, "P1": 9, "P2": 6}


def _shuffled_indexes(total: int) -> list[int]:
    return sorted(range(total), key=lambda index: (index * 37 + 11) % total)


def build_exhibitors() -> list[dict]:
    """生成 186 家展商：优先级 34/62/90，18 个预约（含 1 组冲突）。"""
    rows: list[dict] = []
    for hall, count in HALL_LAYOUT:
        for offset in range(count):
            index = len(rows)
            row_no = offset // 9 + 1
            col_no = offset % 9 + 1
            category = HALL_CATEGORY[hall]
            if index % 7 == 0:
                category = CATEGORIES[(CATEGORIES.index(category) + 3) % len(CATEGORIES)]
            rows.append(
                {
                    "seed_key": f"exh-{hall}-{row_no:02d}{col_no}",
                    "name": f"{BRANDS[index % len(BRANDS)]}{SUFFIXES[index // len(BRANDS)]}",
                    "hall": hall,
                    "booth_no": f"{hall}-{row_no:02d}{col_no}",
                    "row_no": row_no,
                    "col_no": col_no,
                    "category": category,
                    "target_industry": INDUSTRIES[index % len(INDUSTRIES)],
                    "contact_name": f"{SURNAMES[index % len(SURNAMES)]}{GIVEN[(index * 5) % len(GIVEN)]}",
                    "contact_title": TITLES[index % len(TITLES)],
                    "contact_phone": f"1{3 + index % 4}{(index * 7919) % 10**9:09d}",
                    "note": "官网名录缺展位坐标，按现场图纸勘误" if index % 11 == 0 else None,
                }
            )

    order = _shuffled_indexes(len(rows))
    priorities: dict[int, str] = {}
    cursor = 0
    for priority in ("P0", "P1", "P2"):
        for _ in range(PRIORITY_PLAN[priority]):
            priorities[order[cursor]] = priority
            cursor += 1
    for index, row in enumerate(rows):
        priority = priorities[index]
        row["priority"] = priority
        row["dwell_min"] = PRIORITY_DWELL[priority]

    p0_ids = [index for index in range(len(rows)) if rows[index]["priority"] == "P0"]
    p1_ids = [index for index in range(len(rows)) if rows[index]["priority"] == "P1"]

    def _appoint(index: int, day: int, start_min: int) -> None:
        rows[index]["appointment_day"] = day
        rows[index]["appointment_start_min"] = start_min
        rows[index]["appointment_end_min"] = start_min + 30

    # 冲突组：同一时段两位展商，P0 权重高者保留，P1 转改期
    _appoint(p0_ids[0], *CONFLICT_SLOT)
    _appoint(p1_ids[0], *CONFLICT_SLOT)
    for position, (day, start_min) in enumerate(APPOINTMENT_SLOTS):
        target = p0_ids[1 + position] if position < 9 else p1_ids[1 + (position - 9)]
        _appoint(target, day, start_min)
    return rows


EXHIBITORS = build_exhibitors()


SESSION_VENUES = ["主论坛区 · 6.1 馆", "应用论坛区 A · 8.1 馆", "应用论坛区 B · 8.1 馆"]
SESSION_SLOTS = [(570, 610), (630, 670), (690, 730), (810, 850)]
SESSION_TITLES = [
    "AI 视觉质检在 3C 产线的落地边界",
    "国产伺服替代的三年路线图",
    "柔性产线换型：从 4 小时到 40 分钟",
    "工业软件订阅制的成本陷阱",
    "新能源电池模组装配的节拍优化",
    "AGV 与立库协同的调度算法",
    "精密测量如何支撑 0.01mm 公差",
    "工业以太网与 5G 的取舍",
    "机器人示教从编程到拖拽",
    "预测性维护的数据门槛",
    "出海设备的合规与认证",
    "中小工厂自动化的投资回收期",
    "机器视觉光源选型的五个误区",
    "数字孪生上线的真实成本",
    "协作机器人与人机共线安全",
    "仓储机器人密度与坪效",
    "在线检测的误判率治理",
    "工控安全从边界到产线",
    "压铸件毛刺打磨的自动化路径",
    "锂电极片分切的张力控制",
    "产线 OEE 数据可信度",
    "传感器标定的现场方法",
    "MES 与 ERP 的接口治理",
    "展会后的线索跟进节奏",
]
SESSION_SPEAKERS = [
    "华南理工大学 · 陈立", "澜川智能 · 周启", "恒擎传动 · 罗敏", "钧维视觉 · 张涛",
    "中国工控网 · 李颖", "拓垣软件 · 王骁", "睿驰物流 · 何岚", "承光电气 · 孙宇",
]


def build_sessions() -> list[dict]:
    sessions: list[dict] = []
    for day in (1, 2):
        for venue_index, venue in enumerate(SESSION_VENUES):
            for slot_index, (start, end) in enumerate(SESSION_SLOTS):
                index = len(sessions)
                sessions.append(
                    {
                        "seed_key": f"session-{day}-{venue_index}-{slot_index}",
                        "title": SESSION_TITLES[index],
                        "hall": venue,
                        "day": day,
                        "start_min": start,
                        "end_min": end,
                        "start_at_label": f"{start // 60:02d}:{start % 60:02d}",
                        "end_at_label": f"{end // 60:02d}:{end % 60:02d}",
                        "speaker": SESSION_SPEAKERS[index % len(SESSION_SPEAKERS)],
                        "track": ["主题论坛", "技术发布", "应用案例"][venue_index],
                    }
                )
    return sessions


SESSIONS = build_sessions()

# 初始化那次路线排程（算法 B 会真算；seed 只负责触发与留痕）
SEED_ROUTE_RUN = {
    "seed_key": "seed-route-run-d1",
    "operator": "analyst@boothmap.io",
    "trigger": "seed",
    "params": {
        "day_count": 2,
        "day_minutes": 480,
        "day_start_minute": 540,
        "walk_speed_m_per_min": 55.0,
        "priorities": ["P0", "P1"],
    },
}

SEED_AUDIT = [
    ("seed-audit-1", "admin@boothmap.io", "admin", "exhibitor.create", "exhibitor", {"name": "澜川智能装备", "booth_no": "A1-011"}),
    ("seed-audit-2", "analyst@boothmap.io", "analyst", "route.create", "route_run", {"seed": "seed-route-run-d1"}),
]
