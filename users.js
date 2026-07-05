import { api } from '../api.js';
import { badge, esc, pager, showForm, spinner, table, toast } from '../ui.js';

const ROLES = [['owner', 'Owner'], ['pm', 'Project Manager'], ['site', 'Site Engineer'],
  ['store', 'Storekeeper'], ['accountant', 'Accountant'], ['vendor', 'Vendor']];

export async function render(view) {
  let page = 1;
  const vendors = (await api('GET', '/api/vendors?limit=200')).data;

  const fields = (u = {}) => [
    { name: 'name', label: 'Full name', required: true, value: u.name },
    { name: 'email', label: 'Email', required: true, value: u.email },
    { name: 'password', label: u.id ? 'New password (leave blank to keep)' : 'Password', type: 'text',
      help: 'Minimum 8 characters', required: !u.id },
    { name: 'role', label: 'Role', type: 'select', options: ROLES, value: u.role || 'site', required: true },
    { name: 'phone', label: 'Phone', value: u.phone },
    { name: 'vendor_id', label: 'Linked vendor (for Vendor role)', type: 'select',
      options: vendors.map(v => [v.id, v.name]), value: u.vendor_id },
    { name: 'active', label: 'Active', type: 'checkbox', value: u.active !== 0 },
  ];

  async function load() {
    view.innerHTML = spinner();
    const d = await api('GET', `/api/users?page=${page}&limit=50`);
    view.innerHTML = `<div class="panel"><div class="panel-head"><h3>Users (${d.total})</h3>
      <button class="btn btn-primary" id="new-u">+ New user</button></div>
      ${table([
        { key: 'name', label: 'Name', render: r => `<b>${esc(r.name)}</b>` },
        { key: 'email', label: 'Email' },
        { key: 'role', label: 'Role', render: r => badge(r.role) },
        { key: 'vendor_name', label: 'Vendor link' },
        { key: 'phone', label: 'Phone' },
        { key: 'active', label: 'Status', render: r => badge(r.active ? 'active' : 'retired') },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-edit="${r.id}">Edit</button>
          ${r.active ? `<button class="btn btn-sm btn-danger" data-deact="${r.id}">Deactivate</button>` : ''}` },
      ], d.data)}
      ${pager(d.total, d.page, d.limit)}
      <p class="muted">Assign users to projects from each project's Overview tab.</p></div>`;

    view.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { page = Number(b.dataset.page); load(); });
    view.querySelector('#new-u').onclick = async () => {
      const v = await showForm('New user', fields());
      if (!v) return;
      try {
        await api('POST', '/api/users', { ...v, vendor_id: v.vendor_id ? Number(v.vendor_id) : null });
        toast('User created'); load();
      } catch (e) { toast(e.message, 'bad'); }
    };
    view.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
      const u = d.data.find(x => x.id === Number(b.dataset.edit));
      const v = await showForm(`Edit: ${u.name}`, fields(u));
      if (!v) return;
      try {
        await api('PATCH', `/api/users/${u.id}`, { ...v, vendor_id: v.vendor_id ? Number(v.vendor_id) : null,
          password: v.password || null });
        toast('Saved'); load();
      } catch (e) { toast(e.message, 'bad'); }
    });
    view.querySelectorAll('[data-deact]').forEach(b => b.onclick = async () => {
      try { await api('DELETE', `/api/users/${b.dataset.deact}`); toast('User deactivated'); load(); }
      catch (e) { toast(e.message, 'bad'); }
    });
  }
  await load();
}
