import { api } from '../api.js';
import { ENUMS, can, priorityTone } from '../config.js';
import { badge, drawer, emptyState, errorBox, errorMessage, esc, field, fmtTime, kv, table, toast } from '../ui.js';

const state = { q: '', hall: '', priority: '', category: '', appointment: '' };

function options(entries, allLabel = '全部') {
  return [{ value: '', label: allLabel }, ...entries.map(([value, label]) => ({ value, label }))];
}

function openDetail(view, ctx, item) {
  const editable = can(ctx.user.role, 'exhibitor:write');
  const { root, close } = drawer({
    title: item.name,
    subtitle: `${item.booth_no} · ${item.hall_label}`,
    body: `${kv([
      ['展位', `<span class="mono">${esc(item.booth_no)}</span> · 第 ${esc(item.row_no)} 排第 ${esc(item.col_no)} 列`],
      ['坐标', `<span class="mono">x=${esc(item.x)}m / y=${esc(item.y)}m</span>`],
      ['优先级', badge(priorityTone(item.priority), `${item.priority} ${item.priority_label}`)],
      ['品类', esc(item.category_label)],
      ['目标行业', esc(item.target_industry_label)],
      ['停留', `${esc(item.dwell_min)} 分钟`],
      ['预约', esc(item.appointment_label || '无')],
      ['联系人', `${esc(item.contact_name)} · ${esc(item.contact_title)}`],
      ['电话', `<span class="mono">${esc(item.contact_phone || '—')}</span>${item.phone_masked ? ' <span class="muted">（只读角色脱敏）</span>' : ''}`],
      ['备注', esc(item.note || '—')],
      ['更新', fmtTime(item.updated_at)],
    ])}`,
    footer: editable
      ? `<form id="priority-form" style="display:grid;gap:10px">
          ${field({ label: '调整优先级', name: 'priority', value: item.priority, options: Object.entries(ENUMS.priority).map(([value, label]) => ({ value, label: `${value} · ${label}` })) })}
          ${field({ label: '停留分钟', name: 'dwell_min', value: item.dwell_min, type: 'number', attrs: 'min="3" max="60"' })}
          <button class="btn accent" type="submit">保存调整</button>
        </form>`
      : '<span class="mono muted">只读角色仅可查看名录</span>',
  });
  root.querySelector('#priority-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.patch(`/api/exhibitors/${item.id}`, {
        priority: form.priority.value,
        dwell_min: Number(form.dwell_min.value),
      });
      toast('展商优先级已更新');
      close();
      await exhibitorsPage.render(view, ctx);
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

function openCreate(view, ctx) {
  const { root, close } = drawer({
    title: '登记展商',
    subtitle: '展位号决定坐标：A1-023 = A1 馆第 02 排第 3 列',
    body: `<form id="exhibitor-form" style="display:grid;gap:11px">
      ${field({ label: '展商名称', name: 'name', placeholder: '例如：澜川智能装备' })}
      ${field({ label: '馆号', name: 'hall', options: Object.keys(ENUMS.hall).map((value) => ({ value, label: ENUMS.hall[value] })) })}
      ${field({ label: '展位号', name: 'booth_no', placeholder: 'A1-024' })}
      ${field({ label: '品类', name: 'category', options: Object.entries(ENUMS.category).map(([value, label]) => ({ value, label })) })}
      ${field({ label: '目标行业', name: 'target_industry', options: Object.entries(ENUMS.industry).map(([value, label]) => ({ value, label })) })}
      ${field({ label: '优先级', name: 'priority', value: 'P2', options: Object.entries(ENUMS.priority).map(([value, label]) => ({ value, label: `${value} · ${label}` })) })}
      ${field({ label: '联系人', name: 'contact_name' })}
      ${field({ label: '电话', name: 'contact_phone', placeholder: '13800000000' })}
      ${field({ label: '预约时间（可选，本地时间）', name: 'appointment_at', type: 'datetime-local' })}
      <div class="form-error" id="exhibitor-error"></div>
      <button class="btn accent" type="submit">写入名录</button>
    </form>`,
  });
  root.querySelector('#exhibitor-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const payload = {
      name: form.name.value.trim(),
      hall: form.hall.value,
      booth_no: form.booth_no.value.trim().toUpperCase(),
      category: form.category.value,
      target_industry: form.target_industry.value,
      priority: form.priority.value,
      contact_name: form.contact_name.value.trim(),
      contact_phone: form.contact_phone.value.trim(),
      appointment_at: form.appointment_at.value ? `${form.appointment_at.value}:00` : null,
    };
    try {
      await api.post('/api/exhibitors', payload);
      toast('展商已入册');
      close();
      await exhibitorsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#exhibitor-error').textContent =
        err.code === 'CONFLICT' ? '这个展位号已被占用，请核对图纸' : errorMessage(err);
    }
  });
}

export const exhibitorsPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/exhibitors', {
        q: state.q,
        hall: state.hall,
        priority: state.priority,
        category: state.category,
        has_appointment: state.appointment,
        limit: 60,
      });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => exhibitorsPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>展商名录</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${data.total} 家 · P0 ${data.counts.P0} / P1 ${data.counts.P1} / P2 ${data.counts.P2}</span>
            ${can(ctx.user.role, 'exhibitor:write') ? '<button class="btn sm accent" id="new-exhibitor">登记展商</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="exhibitor-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '名称 / 展位号' })}
            ${field({ label: '馆', name: 'hall', value: state.hall, options: options(Object.entries(ENUMS.hall)) })}
            ${field({ label: '优先级', name: 'priority', value: state.priority, options: options(Object.entries(ENUMS.priority)) })}
            ${field({ label: '品类', name: 'category', value: state.category, options: options(Object.entries(ENUMS.category)) })}
            ${field({ label: '预约', name: 'appointment', value: state.appointment, options: [{ value: '', label: '全部' }, { value: 'true', label: '有预约' }] })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '这个筛选下没有展商', hint: '换个优先级或馆号再看。' },
          columns: [
            { key: 'booth_no', label: '展位', className: 'mono' },
            { key: 'name', label: '展商', render: (row) => `<b>${esc(row.name)}</b><div class="muted">${esc(row.category_label)}</div>` },
            { key: 'hall', label: '馆', render: (row) => esc(row.hall) },
            { key: 'priority', label: '优先级', render: (row) => badge(priorityTone(row.priority), `${row.priority} ${row.priority_label}`) },
            { key: 'dwell_min', label: '停留', className: 'num', render: (row) => `${row.dwell_min}′` },
            { key: 'appointment_label', label: '预约', render: (row) => esc(row.appointment_label || '—') },
            { key: 'contact_name', label: '联系人', render: (row) => `${esc(row.contact_name)}<div class="mono muted">${esc(row.contact_phone)}</div>` },
            { key: 'target_industry_label', label: '目标行业' },
          ],
        })}
      </section>`;

    const filters = view.querySelector('#exhibitor-filters');
    filters?.addEventListener('change', () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.hall = filters.querySelector('[name=hall]').value;
      state.priority = filters.querySelector('[name=priority]').value;
      state.category = filters.querySelector('[name=category]').value;
      state.appointment = filters.querySelector('[name=appointment]').value;
      exhibitorsPage.render(view, ctx);
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        exhibitorsPage.render(view, ctx);
      }
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openDetail(view, ctx, item);
      });
    });
    view.querySelector('#new-exhibitor')?.addEventListener('click', () => openCreate(view, ctx));
    if (!data.items.length) {
      view.querySelector('[data-testid="empty-state"]')?.insertAdjacentHTML('beforeend', '<p class="muted">提示：P0 必看展商共 34 家。</p>');
    }
  },
};

export default exhibitorsPage;
