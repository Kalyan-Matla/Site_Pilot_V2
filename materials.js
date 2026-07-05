import { api } from '../api.js';
import { badge, esc, money, pager, showForm, spinner, table, toast } from '../ui.js';

const fields = (m = {}) => [
  { name: 'name', label: 'Material name', required: true, value: m.name },
  { name: 'category', label: 'Category', value: m.category, placeholder: 'Cement / Steel / Aggregate…' },
  { name: 'unit', label: 'Unit', required: true, value: m.unit, placeholder: 'bag / kg / cft / nos' },
  { name: 'default_rate', label: 'Default rate', type: 'number', step: '0.01', value: m.default_rate ?? 0 },
  { name: 'active', label: 'Active', type: 'checkbox', value: m.active !== 0 },
];

export async function render(view, { user }) {
  let page = 1, q = '';
  const canEdit = ['owner', 'pm', 'store'].includes(user.role);

  async function load() {
    view.innerHTML = spinner();
    const d = await api('GET', `/api/materials?page=${page}&limit=50&q=${encodeURIComponent(q)}`);
    view.innerHTML = `<div class="panel"><div class="panel-head"><h3>Material master (${d.total})</h3>
      <div class="toolbar">
        <input type="search" id="q" placeholder="Search" value="${esc(q)}">
        ${canEdit ? '<button class="btn btn-primary" id="new-mat">+ New material</button>' : ''}
      </div></div>
      ${table([
        { key: 'name', label: 'Material', render: r => `<b>${esc(r.name)}</b>` },
        { key: 'category', label: 'Category' },
        { key: 'unit', label: 'Unit' },
        { key: 'default_rate', label: 'Default rate', align: 'num', render: r => money(r.default_rate) },
        { key: 'active', label: 'Status', render: r => badge(r.active ? 'active' : 'retired') },
        ...(canEdit ? [{ key: 'x', label: '', render: r => `<button class="btn btn-sm" data-edit="${r.id}">Edit</button>` }] : []),
      ], d.data)}
      ${pager(d.total, d.page, d.limit)}</div>`;

    view.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { page = Number(b.dataset.page); load(); });
    view.querySelector('#q').onchange = (e) => { q = e.target.value; page = 1; load(); };
    const newBtn = view.querySelector('#new-mat');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('New material', fields());
      if (!v) return;
      try { await api('POST', '/api/materials', v); toast('Material added'); load(); }
      catch (e) { toast(e.message, 'bad'); }
    };
    view.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
      const m = d.data.find(x => x.id === Number(b.dataset.edit));
      const v = await showForm(`Edit: ${m.name}`, fields(m));
      if (!v) return;
      try { await api('PATCH', `/api/materials/${m.id}`, v); toast('Saved'); load(); }
      catch (e) { toast(e.message, 'bad'); }
    });
  }
  await load();
}
