import { api } from '../api.js';
import { errorBox, errorMessage, esc, fmtTime, table } from '../ui.js';

export const auditPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/audit', { limit: 100 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => auditPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>审计日志</h2>
          <span class="meta">${data.total} 条 · 最近 100 条</span>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '还没有审计记录', hint: '登录、排程、改期、导出都会留痕。' },
          columns: [
            { key: 'created_at', label: '时间', render: (row) => fmtTime(row.created_at) },
            { key: 'actor_email', label: '操作人', className: 'mono' },
            { key: 'actor_role', label: '角色' },
            { key: 'action_label', label: '动作' },
            { key: 'entity', label: '对象' },
            { key: 'layer', label: '层', render: (row) => `<span class="badge">${esc(row.layer)}</span>` },
            { key: 'detail', label: '详情', render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>` },
          ],
        })}
      </section>`;
  },
};

export default auditPage;
