// Finance: invoices, payments & cash/bank book, payables ledger, ageing, alerts.
import { api, download } from '../api.js';
import { badge, commentsHtml, esc, money, pager, showForm, spinner, table, tabs,
         toast, today, wireComments } from '../ui.js';

export async function render(view, ctx) {
  const { user } = ctx;
  const isVendor = user.role === 'vendor';
  const canAcct = ['owner', 'accountant'].includes(user.role);
  const canReview = ['owner', 'accountant', 'pm'].includes(user.role);
  const tab = ctx.params[0] || 'invoices';
  const tabList = isVendor
    ? [{ id: 'invoices', label: 'My Invoices' }, { id: 'payments', label: 'Payments Received' }]
    : [{ id: 'invoices', label: 'Invoices' }, { id: 'payments', label: 'Payments & Book' },
       { id: 'payables', label: 'Payables Ledger' }, { id: 'ageing', label: 'Ageing' },
       { id: 'alerts', label: 'Alerts' }];
  view.innerHTML = `${tabs(tabList, tab)}<div id="tab-body">${spinner()}</div>`;
  view.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { location.hash = `#/finance/${b.dataset.tab}`; });
  const body = view.querySelector('#tab-body');
  await ({ invoices, payments, payables, ageing, alerts }[tab] || invoices)(body);

  async function refData() {
    const [vendors, projects, pos] = await Promise.all([
      api('GET', '/api/vendors?limit=200'), api('GET', '/api/projects?limit=100'),
      api('GET', '/api/purchase-orders?limit=100')]);
    return { vendors: vendors.data, projects: projects.data, pos: pos.data };
  }

  // ---------- invoices ----------
  async function invoices(el, page = 1, status = '') {
    const d = await api('GET', `/api/invoices?page=${page}&limit=25&status=${status}`);
    const canCreate = canAcct || user.role === 'pm' || isVendor;
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Invoices (${d.total})</h3>
      <div class="toolbar"><select id="st-f"><option value="">All</option>
        ${['submitted', 'under_review', 'approved', 'paid', 'overdue', 'rejected'].map(s => `<option ${s === status ? 'selected' : ''}>${s}</option>`).join('')}</select>
        ${canCreate ? '<button class="btn btn-primary" id="new-inv">+ Record invoice</button>' : ''}</div></div>
      ${table([
        { key: 'invoice_number', label: 'Invoice #', render: r => `<b>${esc(r.invoice_number)}</b>${r.po_number ? `<br><small class="muted">PO ${esc(r.po_number)}</small>` : ''}` },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'project_name', label: 'Project' },
        { key: 'invoice_date', label: 'Date', render: r => `${r.invoice_date}<br><small class="muted">${r.age_days}d old</small>` },
        { key: 'due_date', label: 'Due' },
        { key: 'total_amount', label: 'Total', align: 'num', render: r => money(r.total_amount) },
        { key: 'balance', label: 'Balance', align: 'num', render: r => `<b>${money(r.balance)}</b>` },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Open</button>` },
      ], d.data, { empty: 'No invoices.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;

    el.querySelector('#st-f').onchange = (e) => invoices(el, 1, e.target.value);
    el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => invoices(el, Number(b.dataset.page), status));

    const newBtn = el.querySelector('#new-inv');
    if (newBtn) newBtn.onclick = async () => {
      const { vendors, projects, pos } = await refData();
      const v = await showForm('Record vendor invoice', [
        { name: 'invoice_number', label: 'Invoice number', required: true },
        { name: 'vendor_id', label: 'Vendor', type: 'select', required: true,
          options: vendors.map(x => [x.id, x.name]), value: isVendor ? user.vendor_id : undefined },
        { name: 'project_id', label: 'Project', type: 'select', required: true, options: projects.map(p => [p.id, p.name]) },
        { name: 'po_id', label: 'Against PO (optional)', type: 'select', options: pos.map(p => [p.id, `${p.po_number} — ${p.vendor_name}`]) },
        { name: 'invoice_date', label: 'Invoice date', type: 'date', value: today(), required: true },
        { name: 'amount', label: 'Base amount', type: 'number', step: '0.01', required: true },
        { name: 'tax_amount', label: 'Tax (GST)', type: 'number', step: '0.01', value: 0 },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ]);
      if (!v) return;
      try {
        await api('POST', '/api/invoices', { ...v, vendor_id: Number(v.vendor_id),
          project_id: Number(v.project_id), po_id: v.po_id ? Number(v.po_id) : null, tax_amount: v.tax_amount || 0 });
        toast('Invoice recorded — due date set from vendor credit period');
        invoices(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    };

    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const inv = d.data.find(x => x.id === Number(b.dataset.open));
      const info = `<table>
        <tr><th>Vendor</th><td>${esc(inv.vendor_name)}</td><th>Project</th><td>${esc(inv.project_name)}</td></tr>
        <tr><th>Dates</th><td>${inv.invoice_date} → due ${inv.due_date}</td><th>Age</th><td>${inv.age_days} days</td></tr>
        <tr><th>Total</th><td>₹ ${money(inv.total_amount)}</td><th>Paid / balance</th><td>${money(inv.paid_amount)} / <b>${money(inv.balance)}</b></td></tr>
        <tr><th>Notes</th><td colspan="3">${esc(inv.notes || '—')}</td></tr></table>
        ${await commentsHtml('invoice', inv.id)}`;
      const fields = [];
      if (canReview) fields.push({ name: '_status', label: 'Set status', type: 'select',
        options: ['submitted', 'under_review', 'approved', 'rejected'], value: inv.status });
      if (canAcct && inv.balance > 0) fields.push(
        { name: '_pay', label: `Record payment (balance ${money(inv.balance)})`, type: 'number', step: '0.01' },
        { name: '_mode', label: 'Mode', type: 'select', options: ['bank', 'cash', 'upi', 'cheque'] },
        { name: '_ref', label: 'Reference (UTR / cheque #)' });
      const prom = showForm(`Invoice ${inv.invoice_number}`, fields,
        { extraHtml: info, submitLabel: fields.length ? 'Apply' : 'Close' });
      wireComments(document.getElementById('modal-root'), () => {});
      const v = await prom;
      if (!v) return;
      try {
        if (v._pay > 0) {
          await api('POST', '/api/payments', { invoice_id: inv.id, vendor_id: inv.vendor_id,
            pay_date: today(), amount: Number(v._pay), mode: v._mode || 'bank', reference: v._ref });
          toast('Payment recorded');
        } else if (v._status && v._status !== inv.status) {
          await api('PATCH', `/api/invoices/${inv.id}/status`, { status: v._status });
          toast(`Invoice ${v._status}`);
        }
        invoices(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------- payments / cash-bank book ----------
  async function payments(el, page = 1, mode = '') {
    const d = await api('GET', `/api/payments?page=${page}&limit=25&mode=${mode}`);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Payments (${d.total})</h3>
      <div class="toolbar">
        <select id="mode-f"><option value="">All modes</option>
          ${['cash', 'bank', 'upi', 'cheque'].map(m => `<option ${m === mode ? 'selected' : ''}>${m}</option>`).join('')}</select>
        <span class="muted">Cash book: ₹ ${money(d.totals.cash_total)} · Bank/other: ₹ ${money(d.totals.bank_total)}</span>
        ${canAcct ? '<button class="btn btn-primary" id="new-pay">+ Record payment</button>' : ''}
      </div></div>
      ${table([
        { key: 'payment_no', label: 'Payment #', render: r => `<b>${esc(r.payment_no)}</b>` },
        { key: 'pay_date', label: 'Date' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'invoice_number', label: 'Against invoice' },
        { key: 'project_name', label: 'Project' },
        { key: 'amount', label: 'Amount', align: 'num', render: r => money(r.amount) },
        { key: 'mode', label: 'Mode', render: r => badge(r.mode) },
        { key: 'reference', label: 'Reference' },
      ], d.data, { empty: 'No payments recorded.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;

    el.querySelector('#mode-f').onchange = (e) => payments(el, 1, e.target.value);
    el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => payments(el, Number(b.dataset.page), mode));
    const newBtn = el.querySelector('#new-pay');
    if (newBtn) newBtn.onclick = async () => {
      const { vendors } = await refData();
      const invs = (await api('GET', '/api/invoices?limit=200')).data.filter(i => i.balance > 0);
      const v = await showForm('Record payment', [
        { name: 'invoice_id', label: 'Against invoice (optional = advance)', type: 'select',
          options: invs.map(i => [i.id, `${i.invoice_number} — ${i.vendor_name} (bal ${money(i.balance)})`]) },
        { name: 'vendor_id', label: 'Vendor', type: 'select', options: vendors.map(x => [x.id, x.name]), required: true },
        { name: 'pay_date', label: 'Date', type: 'date', value: today(), required: true },
        { name: 'amount', label: 'Amount', type: 'number', step: '0.01', required: true },
        { name: 'mode', label: 'Mode', type: 'select', options: ['bank', 'cash', 'upi', 'cheque'], required: true },
        { name: 'reference', label: 'Reference' },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ]);
      if (!v) return;
      try {
        await api('POST', '/api/payments', { ...v, invoice_id: v.invoice_id ? Number(v.invoice_id) : null,
          vendor_id: Number(v.vendor_id) });
        toast('Payment recorded'); payments(el, 1, mode);
      } catch (e) { toast(e.message, 'bad'); }
    };
  }

  // ---------- payables ledger ----------
  async function payables(el) {
    const d = await api('GET', '/api/finance/payables');
    el.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Vendor-wise outstanding</h3>
        <div class="toolbar"><button class="btn" id="exp-csv">CSV</button><button class="btn" id="exp-pdf">PDF</button></div></div>
        ${table([
          { key: 'name', label: 'Vendor' },
          { key: 'invoiced', label: 'Invoiced', align: 'num', render: r => money(r.invoiced) },
          { key: 'paid', label: 'Paid', align: 'num', render: r => money(r.paid) },
          { key: 'outstanding', label: 'Outstanding', align: 'num', render: r => `<b>${money(r.outstanding)}</b>` },
          { key: 'credit_limit', label: 'Credit limit', align: 'num', render: r => r.credit_limit ? money(r.credit_limit) : '—' },
          { key: 'flag', label: '', render: r => r.over_credit_limit ? '<span class="badge badge-bad">over limit</span>' : '' },
        ], d.by_vendor, { empty: 'Nothing outstanding.' })}</div>
      <div class="panel"><h3>Project-wise outstanding</h3>
        ${table([
          { key: 'name', label: 'Project' },
          { key: 'invoiced', label: 'Invoiced', align: 'num', render: r => money(r.invoiced) },
          { key: 'paid', label: 'Paid', align: 'num', render: r => money(r.paid) },
          { key: 'outstanding', label: 'Outstanding', align: 'num', render: r => `<b>${money(r.outstanding)}</b>` },
        ], d.by_project, { empty: 'Nothing outstanding.' })}</div>`;
    el.querySelector('#exp-csv').onclick = () => download('/api/reports/payables?fmt=csv');
    el.querySelector('#exp-pdf').onclick = () => download('/api/reports/payables?fmt=pdf');
  }

  // ---------- ageing ----------
  async function ageing(el) {
    const d = await api('GET', '/api/finance/ageing');
    el.innerHTML = `<div class="panel"><div class="panel-head">
      <h3>Ageing — total outstanding ₹ ${money(d.total_outstanding)}</h3>
      <div class="toolbar"><button class="btn" id="exp-csv">CSV</button><button class="btn" id="exp-pdf">PDF</button></div></div>
      <div class="cards">${d.buckets.map(b =>
        `<div class="card"><div class="kpi">₹ ${money(b.amount)}</div>
         <div class="kpi-label">${b.label} days · ${b.count} invoice(s)</div></div>`).join('')}</div>
      ${d.buckets.map(b => b.invoices.length ? `<h4 class="section-title">${b.label} days</h4>` + table([
        { key: 'invoice_number', label: 'Invoice #' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'project_name', label: 'Project' },
        { key: 'invoice_date', label: 'Date' }, { key: 'due_date', label: 'Due' },
        { key: 'age_days', label: 'Age', align: 'num' },
        { key: 'balance', label: 'Balance', align: 'num', render: r => money(r.balance) },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
      ], b.invoices) : '').join('')}</div>`;
    el.querySelector('#exp-csv').onclick = () => download('/api/reports/ageing?fmt=csv');
    el.querySelector('#exp-pdf').onclick = () => download('/api/reports/ageing?fmt=pdf');
  }

  // ---------- alerts ----------
  async function alerts(el) {
    const d = await api('GET', '/api/finance/alerts');
    el.innerHTML = `<div class="panel"><h3>Credit control alerts (${d.alerts.length})</h3>
      ${d.alerts.map(a => `<div class="alert alert-${a.severity === 'high' ? 'bad' : 'warn'}">⚠ ${esc(a.message)}</div>`).join('')
        || '<div class="empty">No alerts. All vendors within credit limits and no invoices over 45 days.</div>'}</div>`;
  }
}
