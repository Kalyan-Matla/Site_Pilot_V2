import { api } from '../api.js';
import { animateBars, animateCounters, badge, bar, esc, money, spinner, table } from '../ui.js';

// value: number → count-up; string → static
const kpi = (label, value, { prefix = '', cls = '' } = {}) => {
  const inner = typeof value === 'number'
    ? `<span data-countup="${value}" data-prefix="${esc(prefix)}">${esc(prefix)}${money(value)}</span>`
    : esc(value);
  return `<div class="card"><div class="kpi ${cls}">${inner}</div><div class="kpi-label">${esc(label)}</div></div>`;
};

export async function render(view, { user }) {
  view.innerHTML = spinner();

  if (user.role === 'vendor') {
    const [pos, invs] = await Promise.all([
      api('GET', '/api/purchase-orders?limit=10'), api('GET', '/api/invoices?limit=10')]);
    const outstanding = invs.data.reduce((s, i) => s + (i.balance || 0), 0);
    view.innerHTML = `
      <div class="cards">${kpi('Open POs', pos.total)}${kpi('Invoices', invs.total)}
        ${kpi('Outstanding to you', outstanding, { prefix: '₹ ' })}</div>
      <div class="panel"><div class="panel-head"><h3>Recent purchase orders</h3><a href="#/procurement/pos">View all →</a></div>
        ${table([
          { key: 'po_number', label: 'PO #' }, { key: 'project_name', label: 'Project' },
          { key: 'order_date', label: 'Date' },
          { key: 'total_amount', label: 'Amount', align: 'num', render: r => money(r.total_amount) },
          { key: 'status', label: 'Status', render: r => badge(r.status) }], pos.data)}</div>
      <div class="panel"><div class="panel-head"><h3>Your invoices</h3><a href="#/finance/invoices">View all →</a></div>
        ${table([
          { key: 'invoice_number', label: 'Invoice #' }, { key: 'project_name', label: 'Project' },
          { key: 'invoice_date', label: 'Date' }, { key: 'due_date', label: 'Due' },
          { key: 'total_amount', label: 'Total', align: 'num', render: r => money(r.total_amount) },
          { key: 'balance', label: 'Balance', align: 'num', render: r => money(r.balance) },
          { key: 'status', label: 'Status', render: r => badge(r.status) }], invs.data)}</div>`;
    animateCounters(view);
    return;
  }

  const d = await api('GET', '/api/dashboard');
  const s = d.summary;
  const finance = user.role === 'site' || user.role === 'store' ? '' :
    kpi('Outstanding payables', s.outstanding_payables ?? 0, { prefix: '₹ ' }) +
    kpi('Overdue invoices', s.overdue_invoices ?? 0, { cls: s.overdue_invoices ? 'bad' : '' });

  let alertsHtml = '';
  if (['owner', 'pm', 'accountant'].includes(user.role)) {
    try {
      const { alerts } = await api('GET', '/api/finance/alerts');
      alertsHtml = alerts.slice(0, 6).map((a, i) =>
        `<div class="alert alert-${a.severity === 'high' ? 'bad' : 'warn'}" style="animation-delay:${i * 60}ms">${esc(a.message)}</div>`).join('');
    } catch { /* role blocked */ }
  }

  const cols = [
    { key: 'name', label: 'Project', render: r => `<a href="#/projects/${r.id}"><b>${esc(r.name)}</b></a><br><small class="muted">${esc(r.client_name || '')}</small>` },
    { key: 'status', label: 'Status', render: r => badge(r.status) },
    { key: 'progress_pct', label: 'Progress', render: r => `${bar(r.progress_pct)}<small class="muted">${r.progress_pct}%</small>` },
    { key: 'tasks_delayed', label: 'Delayed', align: 'num', render: r => r.tasks_delayed ? `<span class="badge badge-bad">${r.tasks_delayed}</span>` : '0' },
    { key: 'open_issues', label: 'Issues', align: 'num' },
    { key: 'end_date', label: 'Target end', render: r => `<span class="nw">${r.end_date || '—'}</span>` },
  ];
  if (['owner', 'pm', 'accountant'].includes(user.role)) {
    cols.push(
      { key: 'total_cost', label: 'Cost (PO+labour)', align: 'num', render: r => money(r.total_cost) },
      { key: 'invoiced', label: 'Invoiced', align: 'num', render: r => money(r.invoiced) },
      { key: 'paid', label: 'Paid', align: 'num', render: r => money(r.paid) },
      { key: 'margin', label: 'Margin', align: 'num', render: r => `<b>${money(r.margin)}</b>` });
  }

  view.innerHTML = `
    ${alertsHtml}
    <div class="cards">
      ${kpi('Active projects', `${s.projects_active} / ${s.projects_total}`)}
      ${kpi('Delayed tasks', s.tasks_delayed)}
      ${kpi('Open issues', s.open_issues)}
      ${user.role === 'site' || user.role === 'store' ? '' : kpi('Committed (POs)', s.committed ?? 0, { prefix: '₹ ' })}
      ${finance}
    </div>
    <div class="panel"><div class="panel-head"><h3>Projects overview</h3><a href="#/projects">Manage projects →</a></div>
      ${table(cols, d.projects, { empty: 'No projects yet. Create one from the Projects page.', emptyIcon: 'projects' })}</div>`;
  animateCounters(view);
  animateBars(view);
}
