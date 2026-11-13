import { api } from '../api.js';
import { BRAND, ENUMS, priorityTone, visitTone, routeTone } from '../config.js';
import { badge, barList, emptyState, errorBox, errorMessage, esc, statStrip } from '../ui.js';

function timelineItems(day) {
  const visits = (day.visits || []).map((visit) => ({
    kind: 'visit',
    time: visit.eta_label,
    visit,
  }));
  const sessions = (day.sessions || []).map((session) => ({
    kind: 'session',
    time: session.start_label,
    session,
  }));
  return [...visits, ...sessions].sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

function renderDay(day) {
  const items = timelineItems(day)
    .map((item) => {
      if (item.kind === 'session') {
        const session = item.session;
        return `<div class="tl-item session">
          <div class="tl-time">${esc(session.start_label)}</div>
          <div class="tl-axis"><span class="tl-dot"></span></div>
          <div class="tl-body"><b>${esc(session.title)}</b><div class="muted">${esc(session.start_label)}-${esc(session.end_label)} · ${esc(session.hall)} · ${esc(session.speaker)}</div></div>
        </div>`;
      }
      const visit = item.visit;
      return `<div class="tl-item ${visit.conflict ? 'conflict' : ''}" data-visit="${visit.id}" title="展位 ${esc(visit.booth_no)}">
        <div class="tl-time">${esc(visit.eta_label)}</div>
        <div class="tl-axis"><span class="tl-dot"></span></div>
        <div class="tl-body">
          <b>${esc(visit.exhibitor_name)}</b>
          <span class="mono">${esc(visit.booth_no)}</span>
          <div class="muted">${esc(ENUMS.priority[visit.priority] || visit.priority)} · 停留 ${esc(visit.dwell_min)} 分 · ${esc(visit.status_label)}${visit.conflict ? ' · 冲突' : ''}</div>
        </div>
      </div>`;
    })
    .join('');
  return `<article class="day-col" data-testid="day-${day.day}">
    <div class="day-head"><b>${esc(day.label)}</b><span>${esc(day.date)} · ${day.visits.length} 站</span></div>
    <div class="timeline">${items || '<div class="tl-none">这一天还没有排入展位</div>'}</div>
  </article>`;
}

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">读取两日图纸…</div></div>';
    try {
      const data = await api.get('/api/overview');
      const latest = data.latest_run;
      const metrics = latest?.metrics || {};
      view.innerHTML = `
        ${statStrip([
          { label: '展商', value: data.exhibitors_total, hint: '8 个馆 · 官网名录清洗后' },
          { label: '两日到访', value: data.visits_total, hint: `${data.runs_total} 次排程累计` },
          { label: '冲突标记', value: data.conflicts, hint: `${data.deferred} 条已改期` },
          { label: '预约展商', value: data.appointment_total, hint: data.worker_alive ? 'worker 在岗' : 'worker 心跳超时' },
        ])}
        <div class="grid-side">
          <section class="panel">
            <div class="panel-head"><h2>两日路线时间轴</h2><span class="meta">${latest ? esc(latest.run_no) : 'no run'} · ${esc(BRAND.edition)}</span></div>
            <div class="panel-body">
              ${
                latest
                  ? `<div class="day-grid">${data.timeline.map(renderDay).join('')}</div>
                     <p class="note-line" style="margin-top:12px">实线为展位到访，方点为同期论坛；红色为预约冲突标记。</p>`
                  : emptyState({ title: '还没有路线', hint: '去「路线规划」跑一次两日排程。' })
              }
            </div>
          </section>
          <div style="display:grid;gap:16px">
            <section class="panel">
              <div class="panel-head"><h2>最新排程指标</h2><span class="meta">algorithm B</span></div>
              <div class="panel-body">
                ${
                  latest
                    ? `<div class="metrics-grid">
                        <div class="metric"><div class="k">总步行</div><div class="v">${esc(metrics.total_walk_m ?? '—')}<small>m</small></div></div>
                        <div class="metric"><div class="k">覆盖权重</div><div class="v">${esc(metrics.coverage_pct ?? '—')}<small>/100</small></div></div>
                        <div class="metric"><div class="k">冲突组</div><div class="v">${esc(metrics.conflict_pairs ?? 0)}</div></div>
                        <div class="metric"><div class="k">排入展商</div><div class="v">${esc(metrics.visit_count ?? 0)}<small>家</small></div></div>
                      </div>
                      <div class="kv" style="margin-top:10px">
                        <dt>状态</dt><dd>${badge(routeTone(latest.status), latest.status_label)}</dd>
                        <dt>覆盖</dt><dd class="mono">${esc(metrics.covered_weight ?? 0)}/${esc(metrics.total_weight ?? 0)} 权重</dd>
                        <dt>用时</dt><dd class="mono">${esc(metrics.total_dwell_min ?? 0)} 分停留 + ${esc(metrics.walk_minutes ?? 0)} 分步行</dd>
                      </div>`
                    : '<p class="muted">发起一次排程后这里显示步行距离与覆盖权重。</p>'
                }
              </div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>优先级结构</h2><span class="meta">priority</span></div>
              <div class="panel-body">${barList(data.priority.map((item) => ({ label: item.label, count: item.count })))}</div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>馆内展商数</h2><span class="meta">halls</span></div>
              <div class="panel-body">${barList(data.halls.map((item) => ({ label: item.key, count: item.count })), 'ok')}</div>
            </section>
          </div>
        </div>`;
      view.querySelectorAll('[data-visit]').forEach((node) => {
        node.addEventListener('click', () => {
          location.hash = '#/routing';
        });
      });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
    }
  },
};

export default overviewPage;
