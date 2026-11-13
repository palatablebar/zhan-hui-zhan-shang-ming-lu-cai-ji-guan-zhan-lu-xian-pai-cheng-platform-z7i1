import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-brief">
          <div class="eyebrow">${esc(BRAND.edition)} · 华南工业博览会</div>
          <h1>把 186 家展商<br />排进<em>两天</em>的路线</h1>
          <p class="tagline">${esc(BRAND.loginLead)}</p>
          <div class="hall-index">
            ${BRAND.halls
              .map(([hall, name]) => `<span class="hall-chip"><b>${esc(hall)}</b> ${esc(name)}</span>`)
              .join('')}
          </div>
          <div class="brief-points">
            ${BRAND.loginPoints
              .map(([no, text]) => `<div class="brief-point"><i>${esc(no)}</i><span>${esc(text)}</span></div>`)
              .join('')}
          </div>
          <div class="login-schematic">
            ${BRAND.schematic.map(([key, value]) => `<span>${esc(key)} <b>${esc(value)}</b></span>`).join('')}
          </div>
        </section>
        <section class="login-form-wrap">
          <form class="login-card" id="login-form" novalidate>
            <div>
              <div class="brand">BOOTHMAP</div>
              <div class="sub">使用内部账号登录。三个演示账号权限不同，路线运行/改期按钮会随角色变化。</div>
            </div>
            <div class="field">
              <label for="email">邮箱</label>
              <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
            </div>
            <div class="field">
              <label for="password">密码</label>
              <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
            </div>
            <div class="form-error" id="login-error" role="alert"></div>
            <button class="btn accent" id="login-submit" type="submit">进入图纸</button>
            <div class="login-hint">
              密码 <code>Demo@2026</code><br />
              <code>admin@${esc(BRAND.short)}.io</code> 管理员 · <code>analyst@${esc(BRAND.short)}.io</code> 观展专员 ·
              <code>viewer@${esc(BRAND.short)}.io</code> 只读（电话脱敏）
            </div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '核对证件…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '进入图纸';
      }
    });
  },
};

export default loginPage;
