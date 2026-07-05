// Project detail: tabbed workspace for everything scoped to one project.
import { api, apiForm, download } from '../api.js';
import { animateBars, animateCounters, badge, bar, commentsHtml, confirmBox, esc, fmtDate,
         icon, money, pager, showForm, spinner, table, tabs, toast, today, wireComments } from '../ui.js';
import { projectFormFields } from './projects.js';

const TAB_LIST = (role) => [
  { id: 'overview', label: 'Overview' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'issues', label: 'Issues' },
  { id: 'progress', label: 'Progress & DPR' },
  { id: 'documents', label: 'Documents' },
  { id: 'materials', label: 'Materials' },
  { id: 'labour', label: 'Labour' },
  { id: 'checklists', label: 'Checklists' },
  { id: 'activity', label: 'Activity' },
].filter(t => !(role === 'accountant' && ['labour'].includes('')));  // all tabs for now

let usersCache = null;
async function userOptions() {
  if (!usersCache) usersCache = (await api('GET', '/api/users?minimal=1')).data;
  return usersCache.map(u => [u.id, `${u.name} (${u.role})`]);
}

export async function render(view, ctx) {
  const pid = Number(ctx.params[0]);
  let tab = ctx.params[1] || 'overview';
  const { user } = ctx;
  const canManage = ['owner', 'pm'].includes(user.role);
  const canLog = ['owner', 'pm', 'site'].includes(user.role);
  const canStore = ['owner', 'pm', 'store'].includes(user.role);

  const p = await api('GET', `/api/projects/${pid}`);
  ctx.setTitle(p.name);

  view.innerHTML = `${tabs(TAB_LIST(user.role), tab)}<div id="tab-body">${spinner()}</div>`;
  view.querySelectorAll('[data-tab]').forEach(b => {
    b.onclick = () => { location.hash = `#/projects/${pid}/${b.dataset.tab}`; };
  });
  const body = view.querySelector('#tab-body');
  const T = {
    overview, tasks, issues, progress, documents, materials, labour, checklists, activity,
  };
  await (T[tab] || overview)(body);

  // ---------------- overview ----------------
  async function overview(el) {
    const m = p.metrics;
    el.innerHTML = `
      <div class="cards">
        <div class="card"><div class="kpi">${m.progress_pct}%</div><div class="kpi-label">Overall progress</div></div>
        <div class="card"><div class="kpi">${m.tasks_done}/${m.tasks_total}</div><div class="kpi-label">Tasks done</div></div>
        <div class="card"><div class="kpi">${m.tasks_delayed}</div><div class="kpi-label">Delayed tasks</div></div>
        <div class="card"><div class="kpi">${m.open_issues}</div><div class="kpi-label">Open issues</div></div>
        <div class="card"><div class="kpi">₹ ${money((m.po_committed || 0) + (m.labour_cost || 0))}</div><div class="kpi-label">Cost (PO + labour)</div></div>
        <div class="card"><div class="kpi">₹ ${money(m.paid)}</div><div class="kpi-label">Paid out</div></div>
      </div>
      <div class="grid-2">
        <div class="panel"><div class="panel-head"><h3>Details</h3>
          ${canManage ? '<button class="btn btn-sm" id="edit-p">Edit</button>' : ''}</div>
          <table>
            <tr><th>Client</th><td>${esc(p.client_name || '—')}</td></tr>
            <tr><th>Location</th><td>${esc(p.location || '—')}</td></tr>
            <tr><th>Status</th><td>${badge(p.status)}</td></tr>
            <tr><th>Dates</th><td><span class="nw">${fmtDate(p.start_date)}</span> → <span class="nw">${fmtDate(p.end_date)}</span></td></tr>
            <tr><th>Budget</th><td>₹ ${money(p.budget)}</td></tr>
            <tr><th>Contract value</th><td>₹ ${money(p.contract_value)}</td></tr>
            <tr><th>Description</th><td>${esc(p.description || '—')}</td></tr>
          </table></div>
        <div class="panel"><div class="panel-head"><h3>Team (${p.members.length})</h3>
          ${canManage ? '<button class="btn btn-sm" id="add-member">+ Assign user</button>' : ''}</div>
          ${table([
            { key: 'name', label: 'Name' }, { key: 'role', label: 'Role', render: r => badge(r.role) },
            ...(canManage ? [{ key: 'x', label: '', render: r => `<button class="btn btn-sm btn-danger" data-rm="${r.user_id}">Remove</button>` }] : []),
          ], p.members, { empty: 'No users assigned yet.' })}
        </div></div>
      <div class="panel" id="cmt-box">${await commentsHtml('project', pid)}</div>`;
    animateCounters(el);
    wireComments(el, () => render(view, ctx));

    const edit = el.querySelector('#edit-p');
    if (edit) edit.onclick = async () => {
      const v = await showForm('Edit project', projectFormFields(p));
      if (!v) return;
      try { await api('PATCH', `/api/projects/${pid}`, v); toast('Saved'); render(view, ctx); }
      catch (e) { toast(e.message, 'bad'); }
    };
    const addM = el.querySelector('#add-member');
    if (addM) addM.onclick = async () => {
      const v = await showForm('Assign user to project', [
        { name: 'user_id', label: 'User', type: 'select', options: await userOptions(), required: true }]);
      if (!v) return;
      try { await api('POST', `/api/projects/${pid}/members`, { user_id: Number(v.user_id) }); toast('Assigned'); render(view, ctx); }
      catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => {
      if (!await confirmBox('Remove this member from the project?')) return;
      await api('DELETE', `/api/projects/${pid}/members/${b.dataset.rm}`); render(view, ctx);
    });
  }

  // ---------------- tasks ----------------
  const taskFields = async (t = {}) => [
    { name: 'name', label: 'Task name', required: true, value: t.name },
    { name: 'description', label: 'Description', type: 'textarea', value: t.description },
    { name: 'is_milestone', label: 'Milestone', type: 'checkbox', value: t.is_milestone },
    { name: 'planned_start', label: 'Planned start', type: 'date', value: t.planned_start },
    { name: 'planned_end', label: 'Planned end', type: 'date', value: t.planned_end },
    { name: 'status', label: 'Status', type: 'select', options: ['todo', 'in_progress', 'done', 'blocked'], value: t.status || 'todo', required: true },
    { name: 'assignee_id', label: 'Assignee', type: 'select', options: await userOptions(), value: t.assignee_id },
    { name: 'progress_pct', label: 'Progress %', type: 'number', step: '1', value: t.progress_pct ?? 0 },
    { name: 'weight', label: 'Weight (for project %)', type: 'number', step: '0.1', value: t.weight ?? 1 },
  ];

  async function tasks(el) {
    const d = await api('GET', `/api/projects/${pid}/tasks?limit=200`);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Tasks & milestones (${d.total})</h3>
      ${canLog ? '<button class="btn btn-primary" id="new-task">+ New task</button>' : ''}</div>
      ${table([
        { key: 'name', label: 'Task', render: r => `${r.is_milestone ? icon('flag', 13) + ' ' : ''}<b>${esc(r.name)}</b>${r.description ? `<br><small class="muted">${esc(r.description)}</small>` : ''}` },
        { key: 'planned', label: 'Planned', render: r => `<span class="nw">${fmtDate(r.planned_start)}</span> → <span class="nw">${fmtDate(r.planned_end)}</span>` },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'assignee_name', label: 'Assignee' },
        { key: 'progress_pct', label: 'Progress', render: r => `${bar(r.progress_pct)}<small class="muted">${r.progress_pct}%</small>` },
        ...(canLog ? [{ key: 'x', label: '', render: r => `<button class="btn btn-sm" data-edit="${r.id}">Edit</button> ${canManage ? `<button class="btn btn-sm btn-danger" data-del="${r.id}">✕</button>` : ''}` }] : []),
      ], d.data, { empty: 'No tasks yet. Break the project down into tasks and milestones to track progress.', emptyIcon: 'check' })}</div>`;
    animateBars(el);

    const newBtn = el.querySelector('#new-task');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('New task', await taskFields());
      if (!v) return;
      try { await api('POST', `/api/projects/${pid}/tasks`, fix(v)); toast('Task created'); tasks(el); }
      catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
      const t = d.data.find(x => x.id === Number(b.dataset.edit));
      const v = await showForm(`Edit: ${t.name}`, await taskFields(t));
      if (!v) return;
      try { await api('PATCH', `/api/tasks/${t.id}`, fix(v)); toast('Saved'); tasks(el); }
      catch (e) { toast(e.message, 'bad'); }
    });
    el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
      if (!await confirmBox('Delete this task?')) return;
      await api('DELETE', `/api/tasks/${b.dataset.del}`); tasks(el);
    });
    const fix = (v) => ({ ...v, assignee_id: v.assignee_id ? Number(v.assignee_id) : null,
                          progress_pct: v.progress_pct ?? 0, weight: v.weight || 1 });
  }

  // ---------------- issues ----------------
  async function issues(el) {
    const d = await api('GET', `/api/projects/${pid}/issues?limit=100`);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Issues (${d.total})</h3>
      ${canLog || user.role === 'store' ? '<button class="btn btn-primary" id="new-issue">+ Raise issue</button>' : ''}</div>
      ${table([
        { key: 'title', label: 'Issue', render: r => `<b>${esc(r.title)}</b>${r.description ? `<br><small class="muted">${esc(r.description)}</small>` : ''}` },
        { key: 'severity', label: 'Severity', render: r => badge(r.severity) },
        { key: 'status', label: 'Status', render: r => badge(r.status) },
        { key: 'task_name', label: 'Task' },
        { key: 'raised_by_name', label: 'Raised by' },
        { key: 'assigned_to_name', label: 'Assigned to' },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Open</button>` },
      ], d.data, { empty: 'No issues raised.' })}</div>`;

    const issueFields = async (i = {}) => [
      { name: 'title', label: 'Title', required: true, value: i.title },
      { name: 'description', label: 'Description', type: 'textarea', value: i.description },
      { name: 'severity', label: 'Severity', type: 'select', options: ['low', 'medium', 'high', 'critical'], value: i.severity || 'medium', required: true },
      { name: 'status', label: 'Status', type: 'select', options: ['open', 'in_progress', 'resolved', 'closed'], value: i.status || 'open', required: true },
      { name: 'assigned_to', label: 'Assign to', type: 'select', options: await userOptions(), value: i.assigned_to },
    ];
    const newBtn = el.querySelector('#new-issue');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('Raise issue', await issueFields());
      if (!v) return;
      try {
        await api('POST', `/api/projects/${pid}/issues`, { ...v, assigned_to: v.assigned_to ? Number(v.assigned_to) : null });
        toast('Issue raised'); issues(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const i = d.data.find(x => x.id === Number(b.dataset.open));
      const cHtml = await commentsHtml('issue', i.id);
      const v = await showForm(`Issue #${i.id}: ${i.title}`, await issueFields(i), { extraHtml: cHtml, submitLabel: 'Update issue' });
      wireComments(document.getElementById('modal-root'), () => {});
      if (!v) return;
      try {
        await api('PATCH', `/api/issues/${i.id}`, { ...v, assigned_to: v.assigned_to ? Number(v.assigned_to) : null });
        toast('Issue updated'); issues(el);
      } catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------------- progress + DPR/WPR ----------------
  async function progress(el) {
    const d = await api('GET', `/api/projects/${pid}/progress?limit=50`);
    const tasksList = (await api('GET', `/api/projects/${pid}/tasks?limit=200`)).data;
    el.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Progress reports</h3>
        <div class="toolbar">
          <input type="date" id="dpr-date" value="${today()}">
          <button class="btn" id="dpr-pdf">DPR PDF</button><button class="btn" id="dpr-csv">DPR CSV</button>
          <button class="btn" id="wpr-pdf">WPR PDF (this week)</button>
        </div></div>
        <div class="muted">DPR pulls the selected day's logs, materials used, labour and issues. WPR covers Monday–Sunday of the current week.</div>
      </div>
      <div class="panel"><div class="panel-head"><h3>Daily progress logs (${d.total})</h3>
        ${canLog ? '<button class="btn btn-primary" id="new-log">+ Log progress</button>' : ''}</div>
        ${table([
          { key: 'log_date', label: 'Date' },
          { key: 'task_name', label: 'Task' },
          { key: 'work_description', label: 'Work done', render: r => `${esc(r.work_description || '')}${r.issues_text ? `<br><small class="badge badge-warn">issue: ${esc(r.issues_text)}</small>` : ''}` },
          { key: 'quantity_done', label: 'Qty', align: 'num', render: r => r.quantity_done ? `${r.quantity_done} ${esc(r.unit || '')}` : '—' },
          { key: 'labour_count', label: 'Labour', align: 'num' },
          { key: 'photos', label: 'Photos', render: r => r.photos.map(ph => `<a href="#" data-photo="${ph.id}" title="${esc(ph.original_name || 'photo')}">${icon('photo', 15)}</a>`).join(' ') + (canLog ? ` <button class="btn btn-sm" data-addphoto="${r.id}">+</button>` : '') },
          { key: 'created_by_name', label: 'By' },
        ], d.data, { empty: 'No progress logged yet.' })}</div>`;

    el.querySelector('#dpr-pdf').onclick = () => download(`/api/reports/dpr/${pid}?fmt=pdf&report_date=${el.querySelector('#dpr-date').value}`);
    el.querySelector('#dpr-csv').onclick = () => download(`/api/reports/dpr/${pid}?fmt=csv&report_date=${el.querySelector('#dpr-date').value}`);
    el.querySelector('#wpr-pdf').onclick = () => download(`/api/reports/wpr/${pid}?fmt=pdf`);

    const newBtn = el.querySelector('#new-log');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('Log daily progress', [
        { name: 'log_date', label: 'Date', type: 'date', value: today(), required: true },
        { name: 'task_id', label: 'Task', type: 'select', options: tasksList.map(t => [t.id, t.name]) },
        { name: 'work_description', label: 'Work description', type: 'textarea', required: true },
        { name: 'quantity_done', label: 'Quantity done', type: 'number', step: '0.01' },
        { name: 'unit', label: 'Unit', placeholder: 'sqm / cum / nos' },
        { name: 'labour_count', label: 'Labour on site', type: 'number' },
        { name: 'notes', label: 'Notes', type: 'textarea' },
        { name: 'issues_text', label: 'Issues faced', type: 'textarea' },
        { name: 'photo', label: 'Photo (optional)', type: 'file' },
      ]);
      if (!v) return;
      try {
        const { photo, ...rest } = v;
        const log = await api('POST', `/api/projects/${pid}/progress`,
          { ...rest, task_id: rest.task_id ? Number(rest.task_id) : null });
        if (photo) {
          const fd = new FormData(); fd.append('file', photo);
          await apiForm('POST', `/api/progress/${log.id}/photos`, fd);
        }
        toast('Progress logged'); progress(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-photo]').forEach(a => a.onclick = (e) => {
      e.preventDefault(); download(`/api/progress-photos/${a.dataset.photo}`);
    });
    el.querySelectorAll('[data-addphoto]').forEach(b => b.onclick = async () => {
      const v = await showForm('Attach photo', [{ name: 'file', label: 'Photo', type: 'file', required: true }]);
      if (!v || !v.file) return;
      const fd = new FormData(); fd.append('file', v.file);
      try { await apiForm('POST', `/api/progress/${b.dataset.addphoto}/photos`, fd); toast('Photo added'); progress(el); }
      catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------------- documents ----------------
  async function documents(el) {
    const d = await api('GET', `/api/projects/${pid}/documents?limit=100`);
    const canUpload = user.role !== 'vendor';
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Documents (${d.total})</h3>
      ${canUpload ? '<button class="btn btn-primary" id="new-doc">+ Upload document</button>' : ''}</div>
      ${table([
        { key: 'title', label: 'Title', render: r => `<b>${esc(r.title)}</b>` },
        { key: 'category', label: 'Category', render: r => badge(r.category) },
        { key: 'task_name', label: 'Linked task' },
        { key: 'issue_title', label: 'Linked issue' },
        { key: 'version_count', label: 'Versions', align: 'num' },
        { key: 'last_uploaded', label: 'Last upload', render: r => fmtDate(r.last_uploaded) },
        { key: 'created_by_name', label: 'By' },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Versions</button>` },
      ], d.data, { empty: 'No documents uploaded.' })}</div>`;

    const tasksList = (await api('GET', `/api/projects/${pid}/tasks?limit=200`)).data;
    const issuesList = (await api('GET', `/api/projects/${pid}/issues?limit=100`)).data;
    const newBtn = el.querySelector('#new-doc');
    if (newBtn) newBtn.onclick = async () => {
      const v = await showForm('Upload document', [
        { name: 'title', label: 'Title', required: true },
        { name: 'category', label: 'Category', type: 'select', required: true,
          options: ['drawing', 'boq', 'schedule', 'contract', 'approval', 'other'] },
        { name: 'task_id', label: 'Link to task', type: 'select', options: tasksList.map(t => [t.id, t.name]) },
        { name: 'issue_id', label: 'Link to issue', type: 'select', options: issuesList.map(i => [i.id, i.title]) },
        { name: 'notes', label: 'Version notes', type: 'textarea' },
        { name: 'file', label: 'File', type: 'file', required: true },
      ]);
      if (!v || !v.file) return;
      const fd = new FormData();
      fd.append('title', v.title); fd.append('category', v.category);
      if (v.task_id) fd.append('task_id', v.task_id);
      if (v.issue_id) fd.append('issue_id', v.issue_id);
      if (v.notes) fd.append('notes', v.notes);
      fd.append('file', v.file);
      try { await apiForm('POST', `/api/projects/${pid}/documents`, fd); toast('Uploaded'); documents(el); }
      catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const doc = await api('GET', `/api/documents/${b.dataset.open}`);
      const vHtml = `<div class="table-wrap"><table><thead><tr><th>V</th><th>File</th><th>Notes</th><th>By</th><th>Date</th><th></th></tr></thead><tbody>
        ${doc.versions.map(ver => `<tr><td>v${ver.version_no}</td><td>${esc(ver.original_name)}</td>
          <td>${esc(ver.notes || '')}</td><td>${esc(ver.uploaded_by_name || '')}</td><td>${fmtDate(ver.uploaded_at)}</td>
          <td><button class="btn btn-sm" data-dl="${ver.id}">Download</button></td></tr>`).join('')}
        </tbody></table></div>`;
      const v = await showForm(`${doc.title} — versions`, canUpload ? [
        { name: 'notes', label: 'New version notes', type: 'textarea' },
        { name: 'file', label: 'New version file', type: 'file' },
      ] : [], { extraHtml: vHtml, submitLabel: canUpload ? 'Upload new version' : 'Close' });
      document.querySelectorAll('[data-dl]').forEach(x => x.onclick = () => download(`/api/documents/versions/${x.dataset.dl}/download`));
      if (v && v.file) {
        const fd = new FormData();
        if (v.notes) fd.append('notes', v.notes);
        fd.append('file', v.file);
        try { await apiForm('POST', `/api/documents/${doc.id}/versions`, fd); toast('New version uploaded'); documents(el); }
        catch (e) { toast(e.message, 'bad'); }
      }
    });
  }

  // ---------------- materials (stock / summary / usage) ----------------
  async function materials(el) {
    const [stock, summary, usage, mats] = await Promise.all([
      api('GET', `/api/projects/${pid}/stock?limit=200`),
      api('GET', `/api/projects/${pid}/material-summary`),
      api('GET', `/api/projects/${pid}/usage?limit=30`),
      api('GET', '/api/materials?limit=200'),
    ]);
    el.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Site stock</h3>
        <div class="toolbar">
          <button class="btn" id="exp-stock">Export CSV</button>
          ${canStore ? '<button class="btn btn-primary" id="set-stock">Set stock / min level</button>' : ''}
        </div></div>
        ${table([
          { key: 'name', label: 'Material' }, { key: 'category', label: 'Category' },
          { key: 'qty', label: 'In stock', align: 'num', render: r => `${r.qty} ${esc(r.unit)} ${r.is_low ? '<span class="badge badge-bad">LOW</span>' : ''}` },
          { key: 'min_level', label: 'Min level', align: 'num' },
          { key: 'reserved_qty', label: 'Reserved', align: 'num' },
        ], stock.data, { empty: 'No stock entries for this site.' })}</div>
      <div class="panel"><div class="panel-head"><h3>Requested vs received vs used</h3>
        <button class="btn" id="exp-flow">Export CSV</button></div>
        ${table([
          { key: 'name', label: 'Material' },
          { key: 'requested', label: 'Requested', align: 'num' },
          { key: 'ordered', label: 'Ordered', align: 'num' },
          { key: 'received', label: 'Received', align: 'num' },
          { key: 'used', label: 'Used', align: 'num' },
          { key: 'in_stock', label: 'In stock', align: 'num' },
        ], summary.data, { empty: 'No material movement yet.' })}</div>
      <div class="panel"><div class="panel-head"><h3>Usage log</h3>
        ${canLog || user.role === 'store' ? '<button class="btn btn-primary" id="log-usage">+ Log usage</button>' : ''}</div>
        ${table([
          { key: 'usage_date', label: 'Date' }, { key: 'name', label: 'Material' },
          { key: 'qty', label: 'Qty', align: 'num', render: r => `${r.qty} ${esc(r.unit)}` },
          { key: 'task_name', label: 'Task / activity' }, { key: 'logged_by_name', label: 'By' },
        ], usage.data, { empty: 'No usage logged.' })}</div>`;

    el.querySelector('#exp-stock').onclick = () => download(`/api/reports/stock/${pid}?fmt=csv`);
    el.querySelector('#exp-flow').onclick = () => download(`/api/reports/material-flow/${pid}?fmt=csv`);
    const matOpts = mats.data.map(m => [m.id, `${m.name} (${m.unit})`]);
    const setBtn = el.querySelector('#set-stock');
    if (setBtn) setBtn.onclick = async () => {
      const v = await showForm('Set stock level', [
        { name: 'material_id', label: 'Material', type: 'select', options: matOpts, required: true },
        { name: 'qty', label: 'Current quantity', type: 'number', step: '0.01', required: true },
        { name: 'min_level', label: 'Minimum level', type: 'number', step: '0.01', value: 0 },
        { name: 'reserved_qty', label: 'Reserved qty', type: 'number', step: '0.01', value: 0 },
      ]);
      if (!v) return;
      try {
        await api('PUT', `/api/projects/${pid}/stock`, { ...v, material_id: Number(v.material_id) });
        toast('Stock updated'); materials(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
    const useBtn = el.querySelector('#log-usage');
    if (useBtn) useBtn.onclick = async () => {
      const tasksList = (await api('GET', `/api/projects/${pid}/tasks?limit=200`)).data;
      const v = await showForm('Log material usage', [
        { name: 'material_id', label: 'Material', type: 'select', options: matOpts, required: true },
        { name: 'qty', label: 'Quantity used', type: 'number', step: '0.01', required: true },
        { name: 'usage_date', label: 'Date', type: 'date', value: today(), required: true },
        { name: 'task_id', label: 'Task / activity', type: 'select', options: tasksList.map(t => [t.id, t.name]) },
        { name: 'notes', label: 'Notes', type: 'textarea' },
      ]);
      if (!v) return;
      try {
        await api('POST', '/api/material-usage', { ...v, project_id: pid,
          material_id: Number(v.material_id), task_id: v.task_id ? Number(v.task_id) : null });
        toast('Usage logged'); materials(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
  }

  // ---------------- labour ----------------
  async function labour(el) {
    const from = new Date(Date.now() - 13 * 86400000).toISOString().slice(0, 10);
    const [labs, att, pay, vendorsList] = await Promise.all([
      api('GET', `/api/projects/${pid}/labourers?limit=200`),
      api('GET', `/api/projects/${pid}/attendance?att_date=${today()}`),
      api('GET', `/api/projects/${pid}/labour-payable?date_from=${from}&date_to=${today()}`),
      api('GET', '/api/vendors?limit=200').catch(() => ({ data: [] })),
    ]);
    const attMap = Object.fromEntries(att.data.map(a => [a.labourer_id, a]));
    el.innerHTML = `
      <div class="panel"><div class="panel-head"><h3>Attendance — ${today()}</h3>
        ${canLog ? '<button class="btn btn-primary" id="save-att">Save attendance</button>' : ''}</div>
        <div class="table-wrap"><table><thead><tr><th>Labourer</th><th>Category</th><th>Vendor</th>
          <th>Rate/day</th><th>Status</th><th>OT hours</th></tr></thead><tbody>
          ${labs.data.map(l => {
            const a = attMap[l.id] || {};
            return `<tr data-lab="${l.id}"><td>${esc(l.name)}</td><td>${badge(l.category)}</td>
              <td>${esc(l.vendor_name || 'In-house')}</td><td class="num">${money(l.base_rate)}</td>
              <td><select class="att-status" ${canLog ? '' : 'disabled'}>
                ${['present', 'absent', 'half_day'].map(s => `<option ${a.status === s ? 'selected' : (!a.status && s === 'present' ? 'selected' : '')}>${s}</option>`).join('')}
              </select></td>
              <td><input type="number" class="att-ot" value="${a.ot_hours || 0}" min="0" max="16" style="width:65px" ${canLog ? '' : 'disabled'}></td></tr>`;
          }).join('')}</tbody></table></div>
        ${labs.data.length ? '' : '<div class="empty">No labourers registered.</div>'}
        ${canLog ? '<div style="margin-top:.6rem"><button class="btn" id="new-lab">+ Add labourer</button></div>' : ''}
      </div>
      <div class="panel"><div class="panel-head">
        <h3>Payable — last 14 days<br><small class="muted" style="font-weight:400"><span class="nw">${from}</span> → <span class="nw">${today()}</span></small></h3>
        <b class="nw">Total: ₹ ${money(pay.total_payable)}</b></div>
        <div class="grid-2">
          <div><h4 class="section-title">By vendor</h4>
            ${table([
              { key: 'vendor', label: 'Vendor' }, { key: 'labourers', label: 'Labourers', align: 'num' },
              { key: 'days_worked', label: 'Man-days', align: 'num' },
              { key: 'payable', label: 'Payable', align: 'num', render: r => money(r.payable) },
            ], pay.by_vendor)}</div>
          <div><h4 class="section-title">By labourer</h4>
            ${table([
              { key: 'name', label: 'Name' }, { key: 'days_worked', label: 'Days', align: 'num' },
              { key: 'ot_hours', label: 'OT h', align: 'num' },
              { key: 'payable', label: 'Payable', align: 'num', render: r => money(r.payable) },
            ], pay.by_labourer)}</div>
        </div></div>`;

    const saveBtn = el.querySelector('#save-att');
    if (saveBtn) saveBtn.onclick = async () => {
      const entries = [...el.querySelectorAll('[data-lab]')].map(tr => ({
        labourer_id: Number(tr.dataset.lab),
        status: tr.querySelector('.att-status').value,
        ot_hours: Number(tr.querySelector('.att-ot').value || 0),
      }));
      if (!entries.length) return toast('No labourers to mark', 'warn');
      try {
        await api('POST', `/api/projects/${pid}/attendance`, { att_date: today(), entries });
        toast(`Attendance saved for ${entries.length} labourer(s)`);
      } catch (e) { toast(e.message, 'bad'); }
    };
    const newLab = el.querySelector('#new-lab');
    if (newLab) newLab.onclick = async () => {
      const v = await showForm('Add labourer', [
        { name: 'name', label: 'Name', required: true },
        { name: 'category', label: 'Category', type: 'select', required: true,
          options: ['skilled', 'semi_skilled', 'unskilled', 'staff'] },
        { name: 'vendor_id', label: 'Vendor (blank = in-house)', type: 'select',
          options: vendorsList.data.map(x => [x.id, x.name]) },
        { name: 'base_rate', label: 'Base rate / day', type: 'number', step: '0.01', required: true },
        { name: 'ot_rate', label: 'OT rate / hour', type: 'number', step: '0.01', value: 0 },
      ]);
      if (!v) return;
      try {
        await api('POST', `/api/projects/${pid}/labourers`,
          { ...v, vendor_id: v.vendor_id ? Number(v.vendor_id) : null, ot_rate: v.ot_rate || 0 });
        toast('Labourer added'); labour(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
  }

  // ---------------- checklists ----------------
  async function checklists(el) {
    const d = await api('GET', `/api/projects/${pid}/checklists?limit=100`);
    el.innerHTML = `<div class="panel"><div class="panel-head"><h3>Safety & quality checklists (${d.total})</h3>
      ${canLog ? '<button class="btn btn-primary" id="new-cl">+ New inspection</button>' : ''}</div>
      ${table([
        { key: 'check_date', label: 'Date' },
        { key: 'ctype', label: 'Type', render: r => badge(r.ctype) },
        { key: 'title', label: 'Title', render: r => `<b>${esc(r.title)}</b>` },
        { key: 'status', label: 'Outcome', render: r => badge(r.status) },
        { key: 'items', label: 'Items', render: r => `${r.item_count} items${r.failed_count ? ` · <span class="badge badge-bad">${r.failed_count} failed</span>` : ''}` },
        { key: 'inspector_name', label: 'Inspector' },
        { key: 'x', label: '', render: r => `<button class="btn btn-sm" data-open="${r.id}">Open</button>` },
      ], d.data, { empty: 'No inspections recorded.' })}</div>`;

    const itemsEditor = (items = []) => `
      <div class="section-title">Checklist items</div><div class="item-rows" id="cl-items">
      ${items.map(i => rowHtml(i)).join('')}</div>
      <button type="button" class="btn btn-sm" id="add-item">+ Add item</button>`;
    const rowHtml = (i = {}) => `<div class="item-row">
      <input placeholder="Check item" class="ci-item" value="${esc(i.item || '')}">
      <select class="ci-outcome">${['pass', 'fail', 'na'].map(o => `<option ${i.outcome === o ? 'selected' : ''}>${o}</option>`).join('')}</select>
      <input placeholder="Remarks" class="ci-remarks" value="${esc(i.remarks || '')}">
      <button type="button" class="btn btn-sm btn-danger ci-del">✕</button></div>`;
    const wireItems = () => {
      const root = document.getElementById('modal-root');
      root.querySelector('#add-item').onclick = () => {
        root.querySelector('#cl-items').insertAdjacentHTML('beforeend', rowHtml());
        wireDel();
      };
      const wireDel = () => root.querySelectorAll('.ci-del').forEach(b => b.onclick = () => b.closest('.item-row').remove());
      wireDel();
    };
    const collectItems = () => [...document.querySelectorAll('#cl-items .item-row')]
      .map(r => ({ item: r.querySelector('.ci-item').value, outcome: r.querySelector('.ci-outcome').value,
                   remarks: r.querySelector('.ci-remarks').value || null }))
      .filter(i => i.item.trim());

    const clFields = (c = {}) => [
      { name: 'ctype', label: 'Type', type: 'select', options: ['safety', 'quality'], value: c.ctype || 'safety', required: true },
      { name: 'title', label: 'Title', required: true, value: c.title },
      { name: 'check_date', label: 'Date', type: 'date', value: c.check_date || today(), required: true },
      { name: 'status', label: 'Overall outcome', type: 'select', options: ['open', 'passed', 'failed', 'closed'], value: c.status || 'open', required: true },
      { name: 'notes', label: 'Notes', type: 'textarea', value: c.notes },
    ];
    const newBtn = el.querySelector('#new-cl');
    if (newBtn) newBtn.onclick = async () => {
      const prom = showForm('New inspection', clFields(), { extraHtml: itemsEditor([{}, {}, {}]) });
      wireItems();
      const v = await prom;
      if (!v) return;
      try {
        await api('POST', `/api/projects/${pid}/checklists`, { ...v, items: collectItems() });
        toast('Inspection saved'); checklists(el);
      } catch (e) { toast(e.message, 'bad'); }
    };
    el.querySelectorAll('[data-open]').forEach(b => b.onclick = async () => {
      const c = await api('GET', `/api/checklists/${b.dataset.open}`);
      const prom = showForm(`Inspection: ${c.title}`, clFields(c),
        { extraHtml: itemsEditor(c.items), submitLabel: canLog ? 'Update' : 'Close' });
      wireItems();
      const v = await prom;
      if (!v || !canLog) return;
      try {
        await api('PATCH', `/api/checklists/${c.id}`, { ...v, items: collectItems() });
        toast('Updated'); checklists(el);
      } catch (e) { toast(e.message, 'bad'); }
    });
  }

  // ---------------- activity ----------------
  async function activity(el) {
    let apage = 1;
    const loadA = async () => {
      const d = await api('GET', `/api/projects/${pid}/activity?page=${apage}&limit=50`);
      el.innerHTML = `<div class="panel"><h3>Activity feed (${d.total})</h3>
        ${d.data.map((a, i) => `<div class="notif" style="--i:${i}"><b>${esc(a.user_name || 'System')}</b>
          <span>${esc(a.action)}${a.detail ? ` — ${esc(a.detail)}` : ''}</span>
          <span class="when">${esc((a.created_at || '').slice(0, 16).replace('T', ' '))}</span></div>`).join('')
          || '<div class="empty">No activity yet.</div>'}
        ${pager(d.total, d.page, d.limit)}</div>`;
      el.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { apage = Number(b.dataset.page); loadA(); });
    };
    await loadA();
  }
}
