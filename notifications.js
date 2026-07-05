import { api } from '../api.js';
import { esc, icon, pager, spinner, toast } from '../ui.js';

const ICONS = { task: 'check', issue: 'alert', material_request: 'procurement',
  purchase_order: 'doc', invoice: 'finance', payment: 'coins', payment_due: 'clock',
  invoice_45d: 'clock', credit_alert: 'alert', credit_limit: 'alert', low_stock: 'materials',
  stock: 'materials', comment: 'comment', project: 'projects' };

export async function render(view) {
  let page = 1;
  async function load() {
    view.innerHTML = spinner();
    const d = await api('GET', `/api/notifications?page=${page}&limit=30`);
    view.innerHTML = `<div class="panel"><div class="panel-head">
      <h3>Notifications ${d.unread ? `<span class="badge badge-bad">${d.unread} unread</span>` : ''}</h3>
      <button class="btn" id="read-all" ${d.unread ? '' : 'disabled'}>Mark all read</button></div>
      ${d.data.map((n, i) => `<div class="notif ${n.is_read ? '' : 'unread'}" style="--i:${i}">
        <span class="n-ico">${icon(ICONS[n.ntype] || 'bell', 17)}</span>
        <div><b>${esc(n.title)}</b>${n.body ? `<br><small class="muted">${esc(n.body)}</small>` : ''}</div>
        <span class="when">${esc((n.created_at || '').slice(0, 16).replace('T', ' '))}</span></div>`).join('')
        || '<div class="empty">You’re all caught up.</div>'}
      ${pager(d.total, d.page, d.limit)}</div>`;
    view.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { page = Number(b.dataset.page); load(); });
    view.querySelector('#read-all').onclick = async () => {
      await api('POST', '/api/notifications/read', {});
      toast('All marked read'); load();
    };
  }
  await load();
}
