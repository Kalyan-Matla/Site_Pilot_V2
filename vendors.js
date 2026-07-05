// Vendor master + work orders / service contracts.
import { api } from '../api.js';
import { badge, esc, money, pager, showForm, spinner, table, toast } from '../ui.js';

const vendorFields = (v = {}) => [
  { name: 'name', label: 'Vendor name', required: true, value: v.name },
  { name: 'vendor_type', label: 'Type', type: 'select', required: true,
    options: ['material', 'labour', 'service', 'equipment'], value: v.vendor_type || 'material' },
  { name: 'contact_person', label: 'Contact person', value: v.contact_person },
  { name: 'phone', label: 'Phone', value: v.phone },
  { name: 'email', label: 'Email', value: v.email },
  { name: 'gst_no', label: 'GST number', value: v.gst_no },
  { name: 'address', label: 'Address', type: 'textarea', value: v.address },
  { name: 'payment_terms', label: 'Payment terms', value: v.payment_terms, placeholder: 'e.g. 45 days credit' },
  { name: 'credit_period_days', label: 'Credit period (days)', type: 'number', value: v.credit_period_days ?? 45, required: true },
  { name: 'credit_limit', label: 'Credit limit (0 = none)', type: 'number', step: '0.01', value: v.credit_limit ?? 0 },
  { name: 'active', label: 'Active', type: 'checkbox', value: v.active !== 0 },
];

export async function render(view, { user }) {
  const canEdit = ['owner', 'pm', 'accountant'].includes(user.role);
  const canWO = ['owner', 'pm'].includes(user.role);
  let page = 1;

  async function load() {
    view.innerHTML = spinner();
    const [d, wos] = await Promise.all([
      api('GET', `/api/vendors?page=${page}&limit=50`),
      api('GET', '/api/work-orders?limit=50')]);
    view.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Vendors (${d.total})</h3>
        ${canEdit ? '<button class="btn btn-primary" id="new-v">+ New vendor</button>' : ''}</div>
        ${table([
          { key: 'name', label: 'Vendor', render: r => `<b>${esc(r.name)}</b><br><small class="muted">${esc(r.contact_person || '')} ${esc(r.phone || '')}</small>` },
          { key: 'vendor_type', label: 'Type', render: r => badge(r.vendor_type) },
          { key: 'gst_no', label: 'GST' },
          { key: 'payment_terms', label: 'Terms', render: r => `${esc(r.payment_terms || '')}<br><small class="muted">${r.credit_period_days}d credit</small>` },
          { key: 'outstanding', label: 'Outstanding', align: 'num', render: r =>
            `${money(r.outstanding)} ${r.over_credit_limit ? '<span class="badge badge-bad">over limit</span>' : ''}` },
          { key: 'credit_limit', label: 'Credit limit', align: 'num', render: r => r.credit_limit ? money(r.credit_limit) : '—' },
          { key: 'active', label: '', render: r => badge(r.active ? 'active' : 'retired') },
          ...(canEdit ? [{ key: 'x', label: '', render: r => `<button class="btn btn-sm" data-edit="${r.id}">Edit</button>` }] : []),
        ], d.data)}
        ${pager(d.total, d.page, d.limit)}</div>
      <div class="panel"><div class="panel-head"><h3>Work orders / service contracts (${wos.total})</h3>
        ${canWO ? '<button class="btn btn-primary" id="new-wo">+ New work order</button>' : ''}</div>
        ${table([
          { key: 'wo_number', label: 'WO #', render: r => `<b>${esc(r.wo_number)}</b>` },
          { key: 'title', label: 'Title' },
          { key: 'project_name', label: 'Project' },
          { key: 'vendor_name', label: 'Vendor' },
          { key: 'amount', label: 'Value', align: 'num', render: r => money(r.amount) },
          { key: 'dates', label: 'Period', render: r => `<span class="nw">${r.start_date || '—'}</span> → <span class="nw">${r.end_date || '—'}</span>` },
          { key: 'status', label: 'Status', render: r => badge(r.status) },
          ...(canWO ? [{ key: 'x', label: '', render: r => `<button class="btn btn-sm" data-wo="${r.id}">Edit</button>` }] : []),
        ], wos.data, { empty: 'No work orders.' })}</div>`;

    view.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { page = Number(b.dataset.page); load(); });
    const newBtn = view.querySelector('#new-v');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('New vendor', vendorFields());
      if (!v) return;
      try { await api('POST', '/api/vendors', v); toast('Vendor added'); load(); }
      catch (e) { toast(e.message, 'bad'); }
    };
    view.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
      const rec = d.data.find(x => x.id === Number(b.dataset.edit));
      const v = await showForm(`Edit: ${rec.name}`, vendorFields(rec));
      if (!v) return;
      try { await api('PATCH', `/api/vendors/${rec.id}`, v); toast('Saved'); load(); }
      catch (e) { toast(e.message, 'bad'); }
    });

    const woFields = async (w = {}) => {
      const projects = (await api('GET', '/api/projects?limit=100')).data;
      return [
        { name: 'project_id', label: 'Project', type: 'select', options: projects.map(p => [p.id, p.name]), value: w.project_id, required: true },
        { name: 'vendor_id', label: 'Vendor', type: 'select', options: d.data.map(x => [x.id, x.name]), value: w.vendor_id, required: true },
        { name: 'title', label: 'Title', required: true, value: w.title },
        { name: 'description', label: 'Scope / description', type: 'textarea', value: w.description },
        { name: 'amount', label: 'Contract value', type: 'number', step: '0.01', value: w.amount ?? 0 },
        { name: 'start_date', label: 'Start', type: 'date', value: w.start_date },
        { name: 'end_date', label: 'End', type: 'date', value: w.end_date },
        { name: 'status', label: 'Status', type: 'select', options: ['draft', 'active', 'completed', 'cancelled'], value: w.status || 'active', required: true },
      ];
    };
    const newWo = view.querySelector('#new-wo');
    if (newWo) newWo.onclick = async () => {
      const v = await showForm('New work order', await woFields());
      if (!v) return;
      try {
        await api('POST', '/api/work-orders', { ...v, project_id: Number(v.project_id), vendor_id: Number(v.vendor_id) });
        toast('Work order created'); load();
      } catch (e) { toast(e.message, 'bad'); }
    };
    view.querySelectorAll('[data-wo]').forEach(b => b.onclick = async () => {
      const w = wos.data.find(x => x.id === Number(b.dataset.wo));
      const v = await showForm(`Edit: ${w.wo_number}`, await woFields(w));
      if (!v) return;
      try {
        await api('PATCH', `/api/work-orders/${w.id}`, { ...v, project_id: Number(v.project_id), vendor_id: Number(v.vendor_id) });
        toast('Saved'); load();
      } catch (e) { toast(e.message, 'bad'); }
    });
  }
  await load();
}
