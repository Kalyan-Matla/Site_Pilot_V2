// Procurement: material requests (indents) -> purchase orders -> GRNs.
import { api } from '../api.js';
import { badge, commentsHtml, esc, money, pager, showForm, spinner, table, tabs,
         toast, today, wireComments } from '../ui.js';

let cache = {};
async function ref(path, key) {
  if (!cache[key]) cache[key] = (await api('GET', path)).data;
  return cache[key];
}

// Dynamic multi-line item editor injected into modal forms.
function itemsEditor(matOpts, lines = [{}], withRate = false) {
  const rowHtml = (l = {}) => `<div class="item-row" style="grid-template-columns:2fr 1fr ${withRate ? '1fr ' : ''}auto">
    <select class="it-mat">${matOpts.map(([v, t]) => `<option value="${v}" ${l.material_id === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
    <input type="number" class="it-qty" placeholder="Qty" step="0.01" min="0.01" value="${l.qty || ''}">
    ${withRate ? `<input type="number" class="it-rate" placeholder="Rate" step="0.01" min="0" value="${l.rate ?? ''}">` : ''}
    <button type="button" class="btn btn-sm btn-danger it-del">✕</button></div>`;
  const html = `<div class="section-title">Items</div><div class="item-rows" id="po-items">
    ${lines.map(l => rowHtml(l)).join('')}</div>
    <button type="button" class="btn btn-sm" id="add-line">+ Add item</button>`;
  const wire = () => {
    const root = document.getElementById('modal-root');
    const wireDel = () => root.querySelectorAll('.it-del').forEach(b => b.onclick = () => b.closest('.item-row').remove());
    root.querySelector('#add-line').onclick = () => {
      root.querySelector('#po-items').insertAdjacentHTML('beforeend', rowHtml()); wireDel();
    };
    wireDel();
  };
  const collect = () => [...document.querySelectorAll('#po-items .item-row')].map(r => ({
    material_id: Number(r.querySelector('.it-mat').value),
    qty: Number(r.querySelector('.it-qty').value),
    ...(withRate ? { rate: Number(r.querySelector('.it-rate').value || 0) } : {}),
  })).filter(i => i.qty > 0);
  return { html, wire, collect };
}

export async function render(view, ctx) {
  const { user } = ctx;
  cache = {};
  const tab = ctx.params[0] || (user.role === 'vendor' ? 'pos' : 'requests');
  const tabList = user.role === 'vendor'
    ? [{ id: 'pos', label: 'Purchase Orders' }]
    : [{ id: 'requests', label: 'Material Requests' }, { id: 'pos', label: 'Purchase Orders' }, { id: 'grns', label: 'GRNs' }];
  view.innerHTML = `${tabs(tabList, tab)}<div id="tab-body">${spinner()}</div>`;
  view.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { location.hash = `#/procurement/${b.dataset.tab}`; });
  const body = view.querySelector('#tab-body');
  await ({ requests, pos, grns }[tab] || requests)(body);

  // ---------- requests ----------
  async function requests(el, page = 1, status = '') {
    const d = await api('GET', `/api/material-requests?page=${page}&limit=25&status=${status}`);
    const canRaise = ['owner', 'pm', 'site', 'store'].includes(user.role);
    const canDecide = ['owner', 'pm'].includes(user.role);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Material requests (${d.total})</h3>
      <div class="toolbar"><select id="st-f"><option value="">All</option>
        ${['pending', 'approved', 'rejected', 'ordered', 'fulfilled'].map(s => `<option ${s === status ? 'selected' : ''}>${s}</option>`).join('')}</select>
        ${canRaise ? '<button class="btn btn-primary" id="new-mr">+ Raise indent</button>' : ''}</div></div>
      ${table([
        { key: 'request_no', label: 'Indent #', render: r => `<b>${esc(r.request_no)}</b>` },
        { key: 'project_name', label: 'Project' },
        { key: 'item_count', label: 'Items', align: 'num' },
        { key: 'required_date', label: 'Required by', render: r => `<span class="nw">${r.required_date || '—'}</span>` },
        { key: 'requested_by_name', label: 'Requested by' },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Open</button>` },
      ], d.data, { empty: 'No material requests.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;

    el.querySelector('#st-f').onchange = (e) => requests(el, 1, e.target.value);
    el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => requests(el, Number(b.dataset.page), status));

    const newBtn = el.querySelector('#new-mr');
    if (newBtn) newBtn.onclick = async () => {
      const [projects, mats] = await Promise.all([
        ref('/api/projects?limit=100', 'projects'), ref('/api/materials?limit=200', 'mats')]);
      const ed = itemsEditor(mats.map(m => [m.id, `${m.name} (${m.unit})`]));
      const prom = showForm('Raise material indent', [
        { name: 'project_id', label: 'Project', type: 'select', options: projects.map(p => [p.id, p.name]), required: true },
        { name: 'required_date', label: 'Required by', type: 'date', value: today() },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ], { extraHtml: ed.html, submitLabel: 'Submit request' });
      ed.wire();
      const v = await prom;
      if (!v) return;
      const items = ed.collect();
      if (!items.length) return toast('Add at least one item with quantity', 'bad');
      try {
        await api('POST', '/api/material-requests', { ...v, project_id: Number(v.project_id), items });
        toast('Indent submitted'); requests(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    };

    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const r = await api('GET', `/api/material-requests/${b.dataset.open}`);
      const itemsHtml = `<div class="table-wrap"><table><thead><tr><th>Material</th><th>Qty</th><th>Remarks</th></tr></thead>
        <tbody>${r.items.map(i => `<tr><td>${esc(i.name)}</td><td>${i.qty} ${esc(i.unit)}</td><td>${esc(i.remarks || '')}</td></tr>`).join('')}</tbody></table></div>
        <p>${badge(r.status)} ${r.decision_by_name ? `by ${esc(r.decision_by_name)} on ${esc(r.decision_at || '')} ${r.decision_notes ? `— ${esc(r.decision_notes)}` : ''}` : ''}</p>
        ${await commentsHtml('material_request', r.id)}`;
      const actions = canDecide && r.status === 'pending'
        ? [{ name: 'decision', label: 'Decision', type: 'select', options: [['approve', 'Approve ✓'], ['reject', 'Reject ✕']], required: true },
           { name: 'notes', label: 'Decision notes', type: 'textarea' }]
        : [];
      const prom = showForm(`${r.request_no} — ${r.project_name}`, actions,
        { extraHtml: itemsHtml, submitLabel: actions.length ? 'Apply decision' : 'Close' });
      wireComments(document.getElementById('modal-root'), () => {});
      const v = await prom;
      if (!v || !actions.length) return;
      try {
        await api('POST', `/api/material-requests/${r.id}/${v.decision}`, { notes: v.notes });
        toast(`Request ${v.decision}d`); requests(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------- purchase orders ----------
  async function pos(el, page = 1, status = '') {
    const d = await api('GET', `/api/purchase-orders?page=${page}&limit=25&status=${status}`);
    const canCreate = ['owner', 'pm', 'store'].includes(user.role);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Purchase orders (${d.total})</h3>
      <div class="toolbar"><select id="st-f"><option value="">All</option>
        ${['draft', 'issued', 'partially_received', 'received', 'closed', 'cancelled'].map(s => `<option ${s === status ? 'selected' : ''}>${s}</option>`).join('')}</select>
        ${canCreate ? '<button class="btn btn-primary" id="new-po">+ New PO</button>' : ''}</div></div>
      ${table([
        { key: 'po_number', label: 'PO #', render: r => `<b>${esc(r.po_number)}</b>` },
        { key: 'project_name', label: 'Project' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'order_date', label: 'Order date' },
        { key: 'expected_date', label: 'Expected' },
        { key: 'total_amount', label: 'Amount', align: 'num', render: r => money(r.total_amount) },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Open</button>` },
      ], d.data, { empty: 'No purchase orders.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;

    el.querySelector('#st-f').onchange = (e) => pos(el, 1, e.target.value);
    el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => pos(el, Number(b.dataset.page), status));

    const newBtn = el.querySelector('#new-po');
    if (newBtn) newBtn.onclick = async () => {
      const [projects, mats, vendors, reqs] = await Promise.all([
        ref('/api/projects?limit=100', 'projects'), ref('/api/materials?limit=200', 'mats'),
        ref('/api/vendors?limit=200', 'vendors'),
        api('GET', '/api/material-requests?status=approved&limit=100').then(x => x.data)]);
      const ed = itemsEditor(mats.map(m => [m.id, `${m.name} (${m.unit}) @ ${m.default_rate}`]), [{}], true);
      const prom = showForm('New purchase order', [
        { name: 'project_id', label: 'Project', type: 'select', options: projects.map(p => [p.id, p.name]), required: true },
        { name: 'vendor_id', label: 'Vendor', type: 'select', options: vendors.map(x => [x.id, x.name]), required: true },
        { name: 'request_id', label: 'From approved indent (optional)', type: 'select',
          options: reqs.map(r => [r.id, `${r.request_no} — ${r.project_name}`]) },
        { name: 'expected_date', label: 'Expected delivery', type: 'date' },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ], { extraHtml: ed.html, submitLabel: 'Issue PO' });
      ed.wire();
      const v = await prom;
      if (!v) return;
      const items = ed.collect();
      if (!items.length) return toast('Add at least one item', 'bad');
      try {
        await api('POST', '/api/purchase-orders', { ...v, project_id: Number(v.project_id),
          vendor_id: Number(v.vendor_id), request_id: v.request_id ? Number(v.request_id) : null, items });
        toast('PO issued'); cache = {}; pos(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    };

    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const po = await api('GET', `/api/purchase-orders/${b.dataset.open}`);
      const canReceive = ['owner', 'pm', 'store'].includes(user.role) &&
        ['issued', 'partially_received'].includes(po.status);
      const itemsHtml = `<div class="table-wrap"><table><thead><tr><th>Material</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Received</th></tr></thead>
        <tbody>${po.items.map(i => `<tr><td>${esc(i.name)}</td><td>${i.qty} ${esc(i.unit)}</td>
          <td class="num">${money(i.rate)}</td><td class="num">${money(i.amount)}</td>
          <td>${i.received_qty} / ${i.qty}</td></tr>`).join('')}</tbody></table></div>
        <p><b>Total: ₹ ${money(po.total_amount)}</b> · ${badge(po.status)} · from ${esc(po.request_no || 'direct')}
        ${po.grns.length ? `· GRNs: ${po.grns.map(g => esc(g.grn_number)).join(', ')}` : ''}</p>
        ${await commentsHtml('purchase_order', po.id)}`;
      const fields = canReceive ? po.items.filter(i => i.received_qty < i.qty).map(i => ({
        name: `recv_${i.id}`, label: `Receive: ${i.name} (pending ${i.qty - i.received_qty} ${i.unit})`,
        type: 'number', step: '0.01' })) : [];
      const statusField = ['owner', 'pm', 'store'].includes(user.role)
        ? [{ name: '_status', label: 'Change status (optional)', type: 'select',
             options: ['issued', 'closed', 'cancelled'] }] : [];
      const prom = showForm(`${po.po_number} — ${po.vendor_name}`, [...fields, ...statusField],
        { extraHtml: itemsHtml, submitLabel: fields.length ? 'Record GRN / update' : 'Update' });
      wireComments(document.getElementById('modal-root'), () => {});
      const v = await prom;
      if (!v) return;
      try {
        const grnItems = po.items.filter(i => v[`recv_${i.id}`] > 0)
          .map(i => ({ po_item_id: i.id, qty_received: Number(v[`recv_${i.id}`]) }));
        if (grnItems.length) {
          await api('POST', '/api/grns', { po_id: po.id, received_date: today(), items: grnItems });
          toast('GRN recorded, stock updated');
        }
        if (v._status && v._status !== po.status) {
          await api('PATCH', `/api/purchase-orders/${po.id}/status`, { status: v._status });
          toast(`PO ${v._status}`);
        }
        pos(el, 1, status);
      } catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------- GRNs ----------
  async function grns(el, page = 1) {
    const d = await api('GET', `/api/grns?page=${page}&limit=25`);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Goods receipt notes (${d.total})</h3>
      <span class="muted">GRNs are recorded from the PO screen; stock updates automatically.</span></div>
      ${table([
        { key: 'grn_number', label: 'GRN #', render: r => `<b>${esc(r.grn_number)}</b>` },
        { key: 'po_number', label: 'Against PO' },
        { key: 'project_name', label: 'Project' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'received_date', label: 'Received' },
        { key: 'vehicle_no', label: 'Vehicle' },
        { key: 'received_by_name', label: 'By' },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Items</button>` },
      ], d.data, { empty: 'No GRNs yet.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;
    el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => grns(el, Number(b.dataset.page)));
    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const g = await api('GET', `/api/grns/${b.dataset.open}`);
      await showForm(`${g.grn_number} — ${g.project_name}`, [], {
        extraHtml: `<div class="table-wrap"><table><thead><tr><th>Material</th><th>Qty received</th><th>Remarks</th></tr></thead>
          <tbody>${g.items.map(i => `<tr><td>${esc(i.name)}</td><td>${i.qty_received} ${esc(i.unit)}</td><td>${esc(i.remarks || '')}</td></tr>`).join('')}</tbody></table></div>`,
        submitLabel: 'Close' });
    });
  }
}
