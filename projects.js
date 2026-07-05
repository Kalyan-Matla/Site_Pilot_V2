import { api } from '../api.js';
import { animateBars, badge, bar, esc, money, pager, showForm, spinner, table, toast } from '../ui.js';

const STATUSES = ['planned', 'active', 'on_hold', 'completed', 'cancelled'];

const formFields = (p = {}) => [
  { name: 'name', label: 'Project name', required: true, value: p.name },
  { name: 'client_name', label: 'Client', value: p.client_name },
  { name: 'location', label: 'Location', value: p.location },
  { name: 'start_date', label: 'Start date', type: 'date', value: p.start_date },
  { name: 'end_date', label: 'End date', type: 'date', value: p.end_date },
  { name: 'status', label: 'Status', type: 'select', options: STATUSES, value: p.status || 'planned', required: true },
  { name: 'budget', label: 'Budget (cost)', type: 'number', step: '0.01', value: p.budget ?? 0 },
  { name: 'contract_value', label: 'Contract value', type: 'number', step: '0.01', value: p.contract_value ?? 0 },
  { name: 'description', label: 'Description', type: 'textarea', value: p.description },
];

export async function render(view, { user }) {
  let page = 1, status = '', q = '';
  const canEdit = ['owner', 'pm'].includes(user.role);

  async function load() {
    view.innerHTML = spinner();
    const d = await api('GET', `/api/projects?page=${page}&limit=25&status=${status}&q=${encodeURIComponent(q)}`);
    view.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Projects (${d.total})</h3>
        <div class="toolbar">
          <input type="search" id="q" placeholder="Search name / client / location" value="${esc(q)}">
          <select id="status-f"><option value="">All statuses</option>
            ${STATUSES.map(s => `<option ${s === status ? 'selected' : ''}>${s}</option>`).join('')}</select>
          ${canEdit ? '<button class="btn btn-primary" id="new-project">+ New project</button>' : ''}
        </div></div>
      ${table([
        { key: 'name', label: 'Project', render: r => `<a href="#/projects/${r.id}"><b>${esc(r.name)}</b></a><br><small class="muted">${esc(r.location || '')}</small>` },
        { key: 'client_name', label: 'Client' },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'progress', label: 'Progress', render: r => `${bar(r.metrics.progress_pct)}<small class="muted">${r.metrics.progress_pct}% · ${r.metrics.tasks_done}/${r.metrics.tasks_total} tasks</small>` },
        { key: 'delays', label: 'Delays / Issues', render: r => `${r.metrics.tasks_delayed ? `<span class="badge badge-bad">${r.metrics.tasks_delayed} delayed</span>` : ''} ${r.metrics.open_issues ? `<span class="badge badge-warn">${r.metrics.open_issues} issues</span>` : ''}` },
        { key: 'start_date', label: 'Start' }, { key: 'end_date', label: 'End' },
        { key: 'budget', label: 'Budget', align: 'num', render: r => money(r.budget) },
      ], d.data, { empty: 'No projects. Click “New project” to create one.' })}
      ${pager(d.total, d.page, d.limit)}</div>`;
    animateBars(view);

    view.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { page = Number(b.dataset.page); load(); });
    const qEl = view.querySelector('#q');
    qEl.onchange = () => { q = qEl.value; page = 1; load(); };
    view.querySelector('#status-f').onchange = (e) => { status = e.target.value; page = 1; load(); };
    const newBtn = view.querySelector('#new-project');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('New project', formFields());
      if (!v) return;
      try { const p = await api('POST', '/api/projects', v); toast('Project created'); location.hash = `#/projects/${p.id}`; }
      catch (e) { toast(e.message, 'bad'); }
    };
  }
  await load();
}

export { formFields as projectFormFields, STATUSES as PROJECT_STATUSES };
