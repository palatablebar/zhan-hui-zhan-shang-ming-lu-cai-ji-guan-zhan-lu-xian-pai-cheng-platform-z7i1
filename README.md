# 展会展商名录采集与观展路线排程台（`boothmap`）

> 数据工程 · 小型多模块项目。原生 HTML/CSS/JS 前端 + Python FastAPI 后端 + Celery worker + MySQL 8.0 + Redis，5 个容器一键起。

## 1. 场景

- **模拟客户**：南方工业自动化（120 人）市场部 5 人，参加「华南工业博览会（2026-11-18 ~ 11-19）」，2 天、8 个馆、1,860 家展商中筛出 186 家目标展商。
- **现有工作流**：官网名录复制到 Excel → 按兴趣标星 → 现场看纸质地图找展位 → 会后手工整理联系人。
- **三个痛点**：
  1. 名录字段不齐（展位号写成 `A1-023` 或 `A1馆23号`），展位难定位，跨馆走回头路；
  2. 没有路线，2 天走不完 186 家，P0 必看展商经常漏掉；
  3. 预约时段与同期论坛冲突，现场才发现撞车。
- **上下游**：展会官网/小程序名录 → 本系统（名录清洗 → 展位图 → 两日路线排程 → 联系人清单导出）→ 现场观展与会后跟进。
- **一天的工作剧本**：
  1. 09:10 管理员登录，名录按 P0 筛出 **34 家**必看展商；
  2. 09:20 在「展馆平面图」核对 A1/A2 馆展位坐标（`A1-023` 在第 02 排第 3 列）；
  3. 09:30 专员发起两日排程（候选 P0+P1，每天 480 分钟，步行 55 m/min）；
  4. 09:31 算法输出 76 站路线：总步行 **6,553m**、覆盖权重 **83.1/100**、冲突 **1 组**；
  5. 09:40 专员把冲突项（恒擎智能装备）改期到 Day2，路线自动重算 ETA；
  6. 09:50 导出 76 行观展清单 CSV（UTF-8 BOM，Excel 直接打开）；
  7. 10:00 管理员在审计日志核对排程/改期/导出四条记录；
  8. 现场按 Day1 / Day2 时间轴走位，同期论坛在时间轴上并列显示。

## 2. 角色与权限

| 角色 | 账号 | 权限 | 典型动作 |
|---|---|---|---|
| 展会管理员 `admin` | `admin@boothmap.io` | 名录维护 + 排程 + 复核 + 导出 + 审计 | 登记展商、改优先级、导出联系人、查审计 |
| 观展专员 `analyst` | `analyst@boothmap.io` | 排程 + 改序/改期 + 导出 | 发起两日排程、处理预约冲突、确认路线 |
| 业务只读 `viewer` | `viewer@boothmap.io` | 只读名录/路线（电话脱敏） | 看路线与名录，**不能**排程、改期、导出、看审计 |

密码统一：`Demo@2026`。低权角色调用高权接口返回 **403**（真实 HTTP 状态，不是前端隐藏）：

- `POST /api/exhibitors`、`PATCH /api/exhibitors/{id}` → 仅 admin，analyst/viewer 403；
- `POST /api/route-runs`、`PATCH /api/visits/{id}/review` → admin/analyst，viewer 403；
- `GET /api/exports/visits.csv` → admin/analyst，viewer 403；
- `GET /api/audit` → 仅 admin，analyst/viewer 403。

## 3. 功能模块（可串成链路）

1. **展商名录**：186 家展商（8 馆），按馆 / 优先级 / 品类 / 目标行业 / 是否有预约筛选；抽屉里看坐标、联系人、预约；管理员可登记与调优先级。
2. **展馆平面图**：SVG 网格按 `x = 列号 × 3.2m`、`y = 排号 × 2.4m` 画展位点，P0 荧光黄实心；右侧给「同馆成组」蛇形建议与馆内跨度。
3. **路线规划**：算法 B 真算两日路线，展示总步行、覆盖权重、冲突组、两日时间轴表；专员可确认 / 改期 / 顺延。
4. **论坛日程**：24 场同期论坛按天筛选，与路线时间轴并列，便于发现撞车。
5. **导出与审计**：观展清单 CSV（含展位、ETA、优先级、联系人电话）；登录、排程、改期、导出全量审计。

## 4. 快速启动

```bash
cp .env.example .env
docker compose up -d --build
# 等 5/5 healthy
open http://localhost:18201
```

首次启动 backend 自动建表并执行一次 seed（`SEED_DEMO=true`）。seed 幂等，可重复执行：

```bash
docker compose exec -T backend python -m scripts.seed_demo
```

## 5. 本地开发

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
# 前端是静态站点，任意静态服务器即可；接口默认 /api -> 8000
cd frontend/site && python -m http.server 5173
```

## 6. 访问地址

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:18201 |
| 后端 API 文档 | http://localhost:19201/docs |
| 健康检查 | http://localhost:19201/api/health |
| 数据库映射 | localhost:17701 |

## 7. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | 原生 HTML5 + CSS（oklch 令牌 / 蓝图网格）+ ES Modules；无框架、无打包 |
| 后端 | Python 3.11、FastAPI 0.115、SQLAlchemy 2.0、PyJWT、passlib(bcrypt) |
| 异步 | Celery 5.4 + Redis（worker 心跳、每日摘要） |
| 数据库 | MySQL 8.0（utf8mb4） |
| 部署 | Docker Compose，恰好 5 服务 |

## 8. 目录

```text
backend/
  src/{config,constants,controllers,middlewares,models,routes,schemas,services,utils}
  scripts/{seed_demo.py,demo_config.py,worker_healthcheck.sh}
  migrations/            # 人类可读 DDL 参考
  tests/                 # 算法/工具单测（pytest）
frontend/
  site/{index.html,css/{tokens,app}.css,js/{api,store,ui,config,app}.js,js/pages/*.js}
  nginx.conf
docker-compose.yml .env .env.example
```

## 9. 环境变量

见 `.env.example`：`COMPOSE_PROJECT_NAME`、`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT`、`DB_*`、`JWT_SECRET`、`REDIS_URL`、`SEED_DEMO`、`RATE_LIMIT_*`、`APP_TIMEZONE_OFFSET_MINUTES`。

## 10. 核心算法与口径

两个算法都在 `backend/src/services/`，纯 Python 函数、无数据库依赖、可单测（`backend/tests/`）。

### 算法 A｜展位坐标与步行距离（`booth_service.py`）

- **展位号解析**：`馆号-排号(两位)+列号(一位)`，`A1-023` → A1 馆第 02 排第 3 列；非法格式抛 `BoothFormatError`（接口 422）。
- **坐标**：`x = 列号 × 3.2m`，`y = 排号 × 2.4m`（馆门在原点）。
- **同馆距离**：`|Δx| + |Δy|`（曼哈顿，贴合展馆直道）。
- **跨馆距离**：`馆门距离(A) + 150m 换乘 + 馆门距离(B)`。
- **输出**：`GET /api/exhibitors/distance-matrix?ids=…` 的 N×N 矩阵（含 `same_hall` 标记），`GET /api/exhibitors/distance-groups` 的每馆蛇形顺序、馆内跨度、平均入场距离。
- **边界**：非法展位号进入 `invalid` 列表，不参与排程；同一展位号重复登记返回 409。

### 算法 B｜带时间窗的两日路线（`route_service.py`）

- **输入**：展商候选（展位坐标、优先级、停留时长、预约窗口）、`day_count`、`day_minutes`（默认 480）、`day_start_minute`（默认 540 = 09:00）、步行速度（默认 55 m/min）、候选优先级（默认 P0+P1）。
- **权重**：`P0=5`、`P1=3`、`P2=1`。
- **预约硬窗**：有预约的展商必须落在 `[appointment_start, appointment_end]` 内；窗口重叠 → 双方都打 `conflict` 标记，只保留权重高者，另一个 `status=deferred`。
- **贪心插入**：先按预约锚点落位，其余候选按「权重 / 插入增量距离」排序，逐个选插入位置使增量距离最小且当日仍可行。
- **2-opt 改进**：固定锚点位置，反转非锚点子序列，仅在硬窗与当日时长仍满足且总步行下降时接受。
- **输出指标**：`total_walk_m`、`total_dwell_min`、`walk_minutes`、`covered_weight / total_weight`、`coverage_pct`、`conflict_pairs`、`conflict_visits`、`deferred_*`、`by_day[]`。
- **失败态**：无候选 → `status=partial`；预约超出当日时长 → 标 `overtime` 并改期；算法异常 → run `status=failed` 且日志留痕。
- **可复现**：纯确定性，无随机数、无网络；同输入两次 `plan_routes` 结果逐字一致（单测覆盖）。
- **实测（seed 路线）**：候选 96 家 → 排入 **76 站**，总步行 **6,553m**，停留 806 分钟，覆盖权重 **296/356 = 83.1%**，冲突 **1 组**（标记 2 条 + 1 条改期），Day1 31 站 / Day2 45 站。

## 11. 共享枚举出现位置

| 枚举 | 后端 | 前端 |
|---|---|---|
| 角色 `admin/analyst/viewer` | `backend/src/constants/{roles,enums}.py` | `frontend/site/js/config.js` |
| 优先级 `P0/P1/P2` + 权重 5/3/1 | `backend/src/constants/enums.py`（`PRIORITY_WEIGHT`） | `frontend/site/js/config.js`（`ENUMS.priority`） |
| 馆号 `A1…D2` | `backend/src/constants/enums.py`（`HALL_LABELS/HALL_ORDER`） | `frontend/site/js/config.js`（`ENUMS.hall`） |
| 品类 `robot…metrology` | `backend/src/constants/enums.py`（`CATEGORY_LABELS`） | `frontend/site/js/config.js`（`ENUMS.category`） |
| 目标行业 `auto…pharma` | `backend/src/constants/enums.py`（`TARGET_INDUSTRY_LABELS`） | `frontend/site/js/config.js`（`ENUMS.industry`） |
| 预约冲突类型 `appointment/overtime` | `backend/src/constants/enums.py`（`CONFLICT_KIND_LABELS`） | `frontend/site/js/config.js`（`ENUMS.conflict`） |
| 到访状态 `planned/confirmed/adjusted/deferred` | `backend/src/constants/enums.py`（`VISIT_STATUS_LABELS`） | `frontend/site/js/config.js`（`ENUMS.visitStatus`） |
| 排程状态 `queued/running/success/partial/failed` | `backend/src/constants/enums.py`（`ROUTE_STATUS_LABELS`） | `frontend/site/js/config.js`（`ENUMS.routeStatus`） |

> seed 的 `SEED_SUMMARY` 沿用批次固定键名：`sources` = 展商名录条目数，`runs` = 路线排程次数，
> `findings` = 到访条目数（含冲突改期行），`pending` = 仍为 `planned` 的到访数。

## 12. Docker 说明

- 5 个服务：`frontend`(Nginx 静态站) / `backend`(uvicorn) / `worker`(Celery) / `db`(MySQL 8.0) / `redis`，全部带 healthcheck。
- 命名卷：`db_data`、`redis_data`。
- Nginx：`location /api/ { proxy_pass http://backend:8000/; }` + SPA 回落。
- 收尾：`docker compose down -v --remove-orphans`。

## License

内部演示项目，仅用于评测与教学。
