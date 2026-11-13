import { api } from '../api.js';
import { drawer, errorBox, errorMessage, esc, field, kv, table } from '../ui.js';

const state = { day: '', q: '' };

function openSession(item) {
  const { root } = drawer({
    title: item.title,
    subtitle: `${item.day_label} · ${item.start_label}-${item.end_label} · ${item.hall}`,
    body: kv([
      ['分会场', esc(item.hall)],
      ['主题', esc(item.track)],
      ['主讲', esc(item.speaker)],
      ['时段', `<span class="mono">${esc(item.start_label)}-${esc(item.end_label)}</span>`],
      ['提示', '同期论坛与展位预约可能冲突，排程只硬约束展商预约时段。'],
    ]),
  });
  root.querySelector('[data-close]')?.addEventListener('click', () => root.remove());
}

export const sessionsPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/sessions', { day: state.day, q: state.q, limit: 50 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => sessionsPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head"><h2>同期论坛日程</h2><span class="meta">${data.total} 场 · 2 天</span></div>
        <div class="panel-body">
          <div class="filter-bar" id="session-filters">
            ${field({ label: '天', name: 'day', value: state.day, options: [{ value: '', label: '全部' }, { value: '1', label: 'Day 1 · 11/18' }, { value: '2', label: 'Day 2 · 11/19' }] })}
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '主题 / 主讲' })}
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '没有匹配的论坛', hint: '换一天或换个关键词。' },
          columns: [
            { key: 'day_label', label: '日期', className: 'mono' },
            { key: 'start_label', label: '时段', render: (row) => `<span class="mono">${esc(row.start_label)}-${esc(row.end_label)}</span>` },
            { key: 'title', label: '主题', render: (row) => `<b>${esc(row.title)}</b>` },
            { key: 'hall', label: '分会场' },
            { key: 'track', label: '主题' },
            { key: 'speaker', label: '主讲' },
          ],
        })}
      </section>`;
    const filters = view.querySelector('#session-filters');
    filters?.addEventListener('change', () => {
      state.day = filters.querySelector('[name=day]').value;
      state.q = filters.querySelector('[name=q]').value.trim();
      sessionsPage.render(view, ctx);
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openSession(item);
      });
    });
  },
};

export default sessionsPage;
