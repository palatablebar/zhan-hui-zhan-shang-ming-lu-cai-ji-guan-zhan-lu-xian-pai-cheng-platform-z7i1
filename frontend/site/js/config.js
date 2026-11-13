/**
 * 项目品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README §11 列出全部出现位置。
 */
export const BRAND = {
  short: 'boothmap',
  title: '展会展商名录采集与观展路线排程台',
  org: '南方工业自动化 · 市场部',
  edition: 'HALL PLAN · 2026',
  subtitle: '186 家展商 · 8 个馆 · 2 天 960 分钟，把名录变成能走完的路线',
  loginLead: '把官网名录、展位坐标、预约时段和同期论坛放到一张图纸上，算出两天走得完的路线。',
  loginPoints: [
    ['01', '名录按馆/排/列定位展位号，跨馆步行距离含 150m 换乘。'],
    ['02', '预约时段是硬窗，冲突双方都打标记，只保留权重高者。'],
    ['03', '两日路线由后端排程，专员可改期、确认，清单导出给现场。'],
  ],
  halls: [
    ['A1', '工业机器人'],
    ['A2', '机器视觉'],
    ['B1', '传动伺服'],
    ['B2', '电气配电'],
    ['C1', '工业软件'],
    ['C2', '物流自动化'],
    ['D1', '检测测量'],
    ['D2', '新材料'],
  ],
  schematic: [
    ['展商', '186'],
    ['展馆', '8'],
    ['论坛', '24'],
    ['Day1/2', '480min'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/exhibitors', no: '02', label: '展商名录', permission: 'exhibitor:read' },
  { to: '#/floorplan', no: '03', label: '展馆平面图', permission: 'exhibitor:read' },
  { to: '#/routing', no: '04', label: '路线规划', permission: 'route:read' },
  { to: '#/sessions', no: '05', label: '论坛日程', permission: 'session:read' },
  { to: '#/audit', no: '06', label: '审计日志', permission: 'audit:read' },
];

export const ROLE_LABELS = {
  admin: '展会管理员',
  analyst: '观展专员',
  viewer: '业务只读',
};

export const PERMISSIONS = {
  admin: [
    'overview:read', 'exhibitor:read', 'exhibitor:write', 'session:read',
    'route:read', 'route:create', 'visit:read', 'visit:review', 'export:read', 'audit:read',
  ],
  analyst: [
    'overview:read', 'exhibitor:read', 'session:read',
    'route:read', 'route:create', 'visit:read', 'visit:review', 'export:read',
  ],
  viewer: ['overview:read', 'exhibitor:read', 'session:read', 'route:read', 'visit:read'],
};

export const ENUMS = {
  priority: { P0: '必看', P1: '重点', P2: '顺访' },
  hall: {
    A1: 'A1 · 工业机器人与智能装备',
    A2: 'A2 · 机器视觉与传感',
    B1: 'B1 · 传动与伺服',
    B2: 'B2 · 电气与配电',
    C1: 'C1 · 工业软件与数字化',
    C2: 'C2 · 物流自动化与仓储',
    D1: 'D1 · 检测测量与仪器',
    D2: 'D2 · 新材料与工艺',
  },
  category: {
    robot: '工业机器人',
    vision: '机器视觉',
    drive: '传动伺服',
    sensor: '传感仪表',
    software: '工业软件',
    logistics: '物流自动化',
    electric: '电气配电',
    metrology: '检测测量',
  },
  industry: {
    auto: '汽车零部件',
    electronics: '3C 电子',
    energy: '新能源',
    food: '食品饮料',
    general: '通用制造',
    pharma: '医药包装',
  },
  routeStatus: {
    queued: '排队中',
    running: '排程中',
    success: '成功',
    partial: '部分成功',
    failed: '失败',
  },
  visitStatus: {
    planned: '待确认',
    confirmed: '已确认',
    adjusted: '已调整',
    deferred: '已改期',
  },
  conflict: {
    appointment: '预约重叠',
    overtime: '超出当日',
  },
  trigger: { manual: '手动', schedule: '定时', seed: '初始化' },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function priorityTone(priority) {
  return { P0: 'p0', P1: 'p1', P2: 'p2' }[priority] || 'info';
}

export function visitTone(status) {
  return { planned: 'pending', confirmed: 'ok', adjusted: 'adjusted', deferred: 'danger' }[status] || 'info';
}

export function routeTone(status) {
  return { success: 'ok', partial: 'warn', failed: 'danger', running: 'info', queued: 'info' }[status] || 'info';
}
