import { api } from '../api.js';
import { ENUMS, priorityTone } from '../config.js';
import { badge, drawer, errorBox, errorMessage, esc, kv, toast } from '../ui.js';

const state = { hall: 'A1' };

function svgFor(items, hall) {
  const scale = 11;
  const padX = 46;
  const padY = 30;
  const maxX = Math.max(3.2, ...items.map((item) => Number(item.x) || 0));
  const maxY = Math.max(2.4, ...items.map((item) => Number(item.y) || 0));
  const width = maxX * scale + padX + 24;
  const height = maxY * scale + padY + 22;
  const colLines = [];
  for (let col = 1; col * 3.2 <= maxX + 0.1; col += 1) {
    const x = col * 3.2 * scale + padX;
    colLines.push(`<line x1="${x}" y1="${padY - 8}" x2="${x}" y2="${height - 18}" stroke="var(--rule)" stroke-width="0.6" stroke-dasharray="2 4" />
      <text x="${x}" y="${height - 6}" fill="var(--ink-faint)" font-size="7" font-family="monospace" text-anchor="middle">C${col}</text>`);
  }
  const rowLines = [];
  for (let row = 1; row * 2.4 <= maxY + 0.1; row += 1) {
    const y = row * 2.4 * scale + padY;
    rowLines.push(`<line x1="${padX - 10}" y1="${y}" x2="${width - 14}" y2="${y}" stroke="var(--rule)" stroke-width="0.6" stroke-dasharray="2 4" />
      <text x="${padX - 16}" y="${y + 3}" fill="var(--ink-faint)" font-size="7" font-family="monospace" text-anchor="end">R${String(row).padStart(2, '0')}</text>`);
  }
  const booths = items
    .map((item) => {
      const x = Number(item.x) * scale + padX;
      const y = Number(item.y) * scale + padY;
      return `<g class="booth ${esc(priorityTone(item.priority))}" data-id="${esc(item.id)}" transform="translate(${x - 17} ${y - 12})">
        <title>${esc(item.name)} · ${esc(item.booth_no)} · ${esc(item.priority)} ${esc(ENUMS.priority[item.priority] || '')}</title>
        <rect width="34" height="24" rx="1" />
        <text x="17" y="15" text-anchor="middle">${esc(item.booth_no.slice(-3))}</text>
      </g>`;
    })
    .join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(hall)} 馆展位平面图">
    <text x="${padX}" y="16" fill="var(--accent)" font-size="9" font-family="monospace" letter-spacing="1">${esc(hall)} / 1 GRID = 3.2m × 2.4m</text>
    ${colLines.join('')}
    ${rowLines.join('')}
    ${booths}
  </svg>`;
}

function openBooth(ctx, item) {
  const { root } = drawer({
    title: item.name,
    subtitle: `${item.booth_no} · ${item.hall_label}`,
    body: kv([
      ['坐标', `<span class="mono">x=${esc(item.x)}m / y=${esc(item.y)}m</span>`],
      ['优先级', badge(priorityTone(item.priority), `${item.priority} ${item.priority_label}`)],
      ['品类', esc(item.category_label)],
      ['目标行业', esc(item.target_industry_label)],
      ['停留', `${esc(item.dwell_min)} 分钟`],
      ['预约', esc(item.appointment_label || '无')],
      ['联系人', `${esc(item.contact_name)} <span class="mono">${esc(item.contact_phone)}</span>`],
      ['同馆步行', '<span class="mono">同馆曼哈顿距离；跨馆另加 150m 换乘</span>'],
    ]),
    footer: '<button class="btn ghost" data-close>关闭</button>',
  });
  root.querySelector('[data-close]')?.addEventListener('click', () => root.remove());
}

export const floorplanPage = {
  async render(view, ctx) {
    let data;
    let groups;
    try {
      [data, groups] = await Promise.all([
        api.get('/api/exhibitors', { hall: state.hall, limit: 200 }),
        api.get('/api/exhibitors/distance-groups'),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => floorplanPage.render(view, ctx));
      return;
    }
    const hallGroup = (groups.halls || []).find((item) => item.hall === state.hall);
    const order = (hallGroup?.order || []).slice(0, 14);
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>展馆平面图</h2>
          <span class="meta">同馆曼哈顿距离 · 跨馆 +150m 换乘</span>
        </div>
        <div class="panel-body">
          <div class="plan-tabs" id="hall-tabs">
            ${Object.keys(ENUMS.hall)
              .map((hall) => `<button data-hall="${esc(hall)}" class="${hall === state.hall ? 'on' : ''}">${esc(hall)}</button>`)
              .join('')}
          </div>
          <div class="grid-side" style="margin-top:12px">
            <div class="plan">
              ${svgFor(data.items, state.hall)}
              <div class="plan-legend">
                <span><i class="p0"></i>P0 必看</span>
                <span><i class="p1"></i>P1 重点</span>
                <span><i class="p2"></i>P2 顺访</span>
                <span>${esc(ENUMS.hall[state.hall] || state.hall)} · ${data.items.length} 家</span>
              </div>
            </div>
            <div style="display:grid;gap:12px">
              <section class="panel">
                <div class="panel-head"><h2>同馆成组建议</h2><span class="meta">snake order</span></div>
                <div class="panel-body">
                  ${
                    hallGroup
                      ? `<div class="kv" style="margin-bottom:8px">
                          <dt>馆内跨度</dt><dd class="mono">${esc(hallGroup.span_x_m)}m × ${esc(hallGroup.span_y_m)}m</dd>
                          <dt>蛇形步行</dt><dd class="mono">${esc(hallGroup.snake_walk_m)}m</dd>
                          <dt>平均入场</dt><dd class="mono">${esc(hallGroup.avg_gate_m)}m</dd>
                        </div>
                        <div class="walk-order">${order
                          .map(
                            (item, index) =>
                              `<div class="${esc(priorityTone(item.priority))}"><span>${String(index + 1).padStart(2, '0')} · ${esc(item.booth_no)}</span><span>${esc(item.priority)}</span></div>`,
                          )
                          .join('')}</div>`
                      : '<p class="muted">该馆暂无展商。</p>'
                  }
                </div>
              </section>
              <section class="panel">
                <div class="panel-head"><h2>距离口径</h2><span class="meta">algorithm A</span></div>
                <div class="panel-body">
                  <p class="note-line">馆内坐标 x = 列号 × 3.2m，y = 排号 × 2.4m；同馆取曼哈顿距离，跨馆加 150m 换乘并计入两侧馆门距离。</p>
                </div>
              </section>
            </div>
          </div>
        </div>
      </section>`;
    view.querySelectorAll('#hall-tabs button').forEach((button) => {
      button.addEventListener('click', () => {
        state.hall = button.dataset.hall;
        floorplanPage.render(view, ctx);
      });
    });
    view.querySelectorAll('.booth').forEach((node) => {
      node.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === node.dataset.id);
        if (item) openBooth(ctx, item);
      });
    });
  },
};

export default floorplanPage;
