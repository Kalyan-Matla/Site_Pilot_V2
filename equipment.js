import { api } from '../api.js';
import { badge, esc, showForm, spinner, table, toast, today } from '../ui.js';

export async function render(view, { user }) {
  const canEdit = ['owner', 'pm', 'store'].includes(user.role);
  const canLog = ['owner', 'pm', 'site', 'store'].includes(user.role);

  const fields = (e = {}, projects = []) => [
    { name: 'name', label: 'Equipment name', required: true, value: e.name },
    { name: 'code', label: 'Asset code', value: e.code },
    { name: 'category', label: 'Category', value: e.category, placeholder: 'Crane / Mixer / Vibrator…' },
    { name: 'project_id', label: 'Current location (project)', type: 'select',
      options: projects.map(p => [p.id, p.name]), value: e.project_id },
    { name: 'status', label: 'Status', type: 'select',
      options: ['available', 'in_use', 'maintenance', 'retired'], value: e.status || 'available', required: true },
    { name: 'maintenance_interval_hours', label: 'Maintenance every (hours, 0 = n/a)', type: 'number',
      value: e.maintenance_interval_hours ?? 0 },
    { name: 'notes', label: 'Notes', type: 'textarea', value: e.notes },
  ];

  async function load() {
    view.innerHTML = spinner();
    const [d, projects] = await Promise.all([
      api('GET', '/api/equipment?limit=100'), api('GET', '/api/projects?limit=100')]);
    view.innerHTML = `<div class="panel"><div class="panel-head"><h3>Equipment & tools (${d.total})</h3>
      ${canEdit ? '<button class="btn btn-primary" id="new-eq">+ Register equipment</button>' : ''}</div>
      ${table([
        { key: 'name', label: 'Equipment', render: r => `<b>${esc(r.name)}</b><br><small class="muted">${esc(r.code || '')} ${esc(r.category || '')}</small>` },
        { key: 'project_name', label: 'Location', render: r => esc(r.project_name || 'Yard / store') },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'usage_hours', label: 'Total hours', align: 'num' },
        { key: 'maint', label: 'Maintenance', render: r => r.maintenance_interval_hours
          ? `${r.hours_since_maintenance}h since last ${r.maintenance_due ? '<span class="badge badge-bad">DUE</span>' : `<small class="muted">(every ${r.maintenance_interval_hours}h)</small>`}`
          : '—' },
        { key: 'x', label: '', render: r => `${canLog ? `<button class="btn btn-sm" data-log="${r.id}">Log hours</button>` : ''}
          <button class="btn btn-sm" data-hist="${r.id}">History</button>
          ${canEdit ? `<button class="btn btn-sm" data-edit="${r.id}">Edit</button>` : ''}` },
      ], d.data, { empty: 'No equipment registered.' })}</div>`;

    const newBtn = view.querySelector('#new-eq');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('Register equipment', fields({}, projects.data));
      if (!v) return;
      try {
        await api('POST', '/api/equipment', { ...v, project_id: v.project_id ? Number(v.project_id) : null,
          maintenance_interval_hours: v.maintenance_interval_hours || 0 });
        toast('Equipment registered'); load();
      } catch (e) { toast(e.message, 'bad'); }
    };
    view.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
      const e = d.data.find(x => x.id === Number(b.dataset.edit));
      const v = await showForm(`Edit: ${e.name}`, fields(e, projects.data));
      if (!v) return;
      try {
        await api('PATCH', `/api/equipment/${e.id}`, { ...v, project_id: v.project_id ? Number(v.project_id) : null,
          maintenance_interval_hours: v.maintenance_interval_hours || 0 });
        toast('Saved'); load();
      } catch (err) { toast(err.message, 'bad'); }
    });
    view.querySelectorAll('[data-log]').forEach(b => b.onclick = async () => {
      const v = await showForm('Log usage / maintenance', [
        { name: 'log_date', label: 'Date', type: 'date', value: today(), required: true },
        { name: 'hours_used', label: 'Hours used', type: 'number', step: '0.5', required: true },
        { name: 'is_maintenance', label: 'This was a maintenance service', type: 'checkbox' },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ]);
      if (!v) return;
      try {
        await api('POST', `/api/equipment/${b.dataset.log}/logs`, { ...v, hours_used: v.hours_used || 0 });
        toast('Logged'); load();
      } catch (e) { toast(e.message, 'bad'); }
    });
    view.querySelectorAll('[data-hist]').forEach(b => b.onclick = async () => {
      const { data } = await api('GET', `/api/equipment/${b.dataset.hist}/logs`);
      await showForm('Usage & maintenance history', [], {
        extraHtml: table([
          { key: 'log_date', label: 'Date' },
          { key: 'hours_used', label: 'Hours', align: 'num' },
          { key: 'is_maintenance', label: 'Type', render: r => r.is_maintenance ? badge('maintenance') : 'usage' },
          { key: 'project_name', label: 'Project' },
          { key: 'logged_by_name', label: 'By' },
          { key: 'notes', label: 'Notes' },
        ], data, { empty: 'No logs.' }), submitLabel: 'Close' });
    });
  }
  await load();
}
