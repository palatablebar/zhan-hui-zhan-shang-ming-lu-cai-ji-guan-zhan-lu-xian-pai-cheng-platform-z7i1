import { api } from '../api.js';
import { ENUMS } from '../config.js';
import { badge, drawer, emptyState, errorBox, errorMessage, esc, fmtTime, toast } from '../ui.js';

const state = { pending: false };

function batchTone(status) {
  return { registered: 'pending', published: 'ok', failed: 'danger' }[status] || 'info';
}

function versionTone(status) {
  return { active: 'ok', retired: 'info', rolled_back: 'warn' }[status] || 'info';
}

function statLine(batch) {
  const r = batch.reconciliation || {};
  return `<div class="stat-strip">
    <div class="stat"><span class="k">来源行数</span><span class="v">${esc(batch.total_rows)}</span></div>
    <div class="stat"><span class="k">好行</span><span class="v">${esc(batch.valid_count)}</span></div>
    <div class="stat"><span class="k">隔离</span><span class="v">${esc(batch.quarantine_count)}</span></div>
    <div class="stat"><span class="k">新增 / 合并</span><span class="v">${esc(batch.inserted_count)} / ${esc(batch.merged_count)}</span></div>
    <div class="stat"><span class="k">人工保留</span><span class="v">${esc(r.manual_edited_existing ?? 0)}</span></div>
  </div>`;
}

function batchRow(batch) {
  const publishable = batch.status === 'registered';
  return `<tr data-batch="${esc(batch.id)}">
    <td><b class="mono">${esc(batch.batch_code)}</b><div class="muted">${esc(batch.source_name || '')}</div></td>
    <td>${badge(batchTone(batch.status), ENUMS.batchStatus[batch.status] || batch.status)}</td>
    <td>${badge('info', ENUMS.importMode[batch.mode] || batch.mode)}</td>
    <td class="mono">${esc(batch.total_rows)}</td>
    <td class="mono">${esc(batch.valid_count)}</td>
    <td class="mono">${esc(batch.quarantine_count)}</td>
    <td class="mono">${esc(batch.inserted_count)} / ${esc(batch.merged_count)}</td>
    <td class="muted">${fmtTime(batch.created_at)}</td>
    <td>
      <div class="day-actions">
        <button class="btn sm ghost" data-action="detail" data-id="${esc(batch.id)}">明细</button>
        ${
          publishable
            ? `<button class="btn sm accent" data-action="publish" data-id="${esc(batch.id)}">发布切换</button>`
            : ''
        }
      </div>
    </td>
  </tr>`;
}

function stagingRow(row) {
  const tone = row.status === 'quarantine' ? 'danger' : 'ok';
  const name = row.raw?.name || row.raw?.['展商名称'] || `第 ${row.row_no} 行`;
  const booth = row.normalized?.booth_no || row.raw?.booth_no || row.raw?.['展位号'] || '—';
  return `<tr>
    <td class="mono">${esc(row.row_no)}</td>
    <td>${badge(tone, row.status === 'quarantine' ? '隔离' : '好行')}</td>
    <td><b>${esc(name)}</b><div class="muted mono">${esc(booth)}</div></td>
    <td>${
      row.status === 'quarantine'
        ? (row.reason_labels || []).map((text) => badge('danger', text)).join(' ')
        : '<span class="muted">可入册</span>'
    }</td>
  </tr>`;
}

async function openBatchDetail(view, ctx, batchId) {
  let detail;
  try {
    detail = await api.get(`/api/imports/batches/${batchId}`);
  } catch (err) {
    toast(errorMessage(err), 'err');
    return;
  }
  const { root, close } = drawer({
    title: `批次 ${detail.batch_code}`,
    subtitle: `${detail.source_name || ''} · ${fmtTime(detail.created_at)}`,
    body: `
      ${statLine(detail)}
      ${detail.error_text ? `<p class="note-line" style="color:var(--danger)">${esc(detail.error_text)}</p>` : ''}
      <div class="table-wrap" style="margin-top:12px"><table class="data">
        <thead><tr><th>行号</th><th>判定</th><th>展商 / 展位</th><th>隔离原因</th></tr></thead>
        <tbody>${(detail.staging || []).map(stagingRow).join('')}</tbody>
      </table></div>`,
  });
  root.querySelector('[data-close]')?.addEventListener('click', close);
}

async function publishBatch(view, ctx, batchId) {
  if (state.pending) return;
  if (!window.confirm('整批校验通过后将一次性切换为新名录；失败会自动回滚到旧版且不丢数据。确认发布？')) return;
  state.pending = true;
  try {
    const result = await api.post(`/api/imports/batches/${batchId}/publish`);
    toast(result.idempotent ? '该批次已发布，重复请求未产生变更' : `已切换到名录版本 v${result.version?.version_no ?? ''}`);
    await importsPage.render(view, ctx);
  } catch (err) {
    toast(errorMessage(err), 'err');
    await importsPage.render(view, ctx);
  } finally {
    state.pending = false;
  }
}

async function rollbackVersion(view, ctx, versionId) {
  if (state.pending) return;
  if (!window.confirm('回滚只切换名录版本指针，不会删除任何展商行。确认回滚到该版本？')) return;
  state.pending = true;
  try {
    await api.post(`/api/imports/directory/versions/${versionId}/rollback`);
    toast('已回滚名录版本');
    await importsPage.render(view, ctx);
  } catch (err) {
    toast(errorMessage(err), 'err');
  } finally {
    state.pending = false;
  }
}

function openRegisterForm(view, ctx) {
  const { root, close } = drawer({
    title: '登记补录批次',
    subtitle: '上传官网名录 CSV/JSON；坏行隔离不入库，发布前不改动现网名录',
    body: `<form id="import-form" style="display:grid;gap:12px">
      <div class="field">
        <label for="batch_code">批次编号（幂等键，重复重跑不新增/覆盖）</label>
        <input name="batch_code" id="batch_code" required placeholder="如 B20261113-01" />
      </div>
      <div class="field">
        <label for="mode">导入模式</label>
        <select name="mode" id="mode">
          <option value="supplement">补录（保留旧名录，默认）</option>
          <option value="snapshot">快照（新版本仅含本批好行）</option>
        </select>
      </div>
      <div class="field">
        <label for="file">来源文件（.csv / .json）</label>
        <input type="file" name="file" id="file" accept=".csv,.txt,.json" required />
      </div>
      <div class="form-error" id="import-error"></div>
      <button class="btn accent" type="submit">上传并登记</button>
    </form>`,
  });
  root.querySelector('#import-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const code = form.batch_code.value.trim();
    const file = form.file.files[0];
    const errorNode = root.querySelector('#import-error');
    if (!code || !file) {
      errorNode.textContent = '批次编号和来源文件都必填';
      return;
    }
    const data = new FormData();
    data.append('batch_code', code);
    data.append('mode', form.mode.value);
    data.append('file', file);
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    button.textContent = '登记中…';
    try {
      const batch = await api.upload('/api/imports/batches/upload', data);
      toast(`登记完成：好行 ${batch.valid_count}，隔离 ${batch.quarantine_count}`);
      close();
      await importsPage.render(view, ctx);
      if (batch.quarantine_count > 0) openBatchDetail(view, ctx, batch.id);
    } catch (err) {
      errorNode.textContent = errorMessage(err);
      button.disabled = false;
      button.textContent = '上传并登记';
    }
  });
}

function versionsPanel(payload) {
  const items = payload.items || [];
  if (!items.length) {
    return `<section class="panel"><div class="panel-head"><h2>名录版本</h2></div>
      <div class="panel-body">${emptyState({ title: '还没有名录版本', hint: '发布第一个批次后会生成版本，支持一键回滚。' })}</div></section>`;
  }
  return `<section class="panel">
    <div class="panel-head"><h2>名录版本</h2><span class="meta">当前 active 供平面图与两日排程使用</span></div>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>版本</th><th>状态</th><th>成员数</th><th>说明</th><th>时间</th><th>操作</th></tr></thead>
      <tbody>${items
        .map(
          (v) => `<tr>
            <td class="mono"><b>v${esc(v.version_no)}</b></td>
            <td>${badge(versionTone(v.status), ENUMS.versionStatus[v.status] || v.status)}</td>
            <td class="mono">${esc(v.exhibitor_count)}</td>
            <td class="muted">${esc(v.label || '')}</td>
            <td class="muted">${fmtTime(v.published_at || v.created_at)}</td>
            <td>${v.is_active ? '<span class="muted">当前使用中</span>' : `<button class="btn sm ghost" data-action="rollback" data-vid="${esc(v.id)}">回滚到此版</button>`}</td>
          </tr>`,
        )
        .join('')}</tbody>
    </table></div>
  </section>`;
}

export const importsPage = {
  async render(view, ctx) {
    let batchesPayload;
    let versionsPayload;
    try {
      [batchesPayload, versionsPayload] = await Promise.all([
        api.get('/api/imports/batches'),
        api.get('/api/imports/directory/versions'),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => importsPage.render(view, ctx));
      return;
    }
    const batches = batchesPayload.items || [];
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>批次补录</h2>
          <button class="btn sm accent" id="new-import">登记新批次</button>
        </div>
        <div class="panel-body">
          <p class="note-line">好行入册、坏行隔离并标注原因；同馆同展位重复会被隔离。发布走整批校验 + 单事务切换，失败自动回滚旧版且不丢数据；重复批次重跑不新增、不覆盖人工修改。</p>
          ${
            batches.length
              ? `<div class="table-wrap"><table class="data">
                  <thead><tr><th>批次 / 来源</th><th>状态</th><th>模式</th><th>来源</th><th>好行</th><th>隔离</th><th>新增/合并</th><th>登记时间</th><th>操作</th></tr></thead>
                  <tbody>${batches.map(batchRow).join('')}</tbody>
                </table></div>`
              : emptyState({ title: '还没有补录批次', hint: '上传官网每天补发的名录文件，系统会先清洗隔离再发布。' })
          }
        </div>
      </section>
      ${versionsPanel(versionsPayload)}`;

    view.querySelector('#new-import')?.addEventListener('click', () => openRegisterForm(view, ctx));
    view.querySelectorAll('[data-action="detail"]').forEach((btn) =>
      btn.addEventListener('click', () => openBatchDetail(view, ctx, btn.dataset.id)),
    );
    view.querySelectorAll('[data-action="publish"]').forEach((btn) =>
      btn.addEventListener('click', () => publishBatch(view, ctx, Number(btn.dataset.id))),
    );
    view.querySelectorAll('[data-action="rollback"]').forEach((btn) =>
      btn.addEventListener('click', () => rollbackVersion(view, ctx, Number(btn.dataset.vid))),
    );
  },
};

export default importsPage;
