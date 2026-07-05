// Report centre: exports + on-screen labour summary + audit log.
import { api, download } from '../api.js';
import { daysAgo, esc, money, pager, spinner, table, toast, today } from '../ui.js';

export async function render(view, { user }) {
  view.innerHTML = spinner();
  const projects = (await api('GET', '/api/projects?limit=100')).data;
  const opts = projects.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  const canFinance = ['owner', 'accountant', 'pm'].includes(user.role);

  view.innerHTML = `
    <div class="panel"><h3>Project reports</h3>
      <div class="filters">
        <select id="rp-project">${opts}</select>
        <input type="date" id="rp-date" value="${today()}">
        <button class="btn" data-exp="dpr,pdf">DPR PDF</button>
        <button class="btn" data-exp="dpr,csv">DPR CSV</button>
        <button class="btn" data-exp="wpr,pdf">WPR PDF</button>
        <button class="btn" data-exp="wpr,csv">WPR CSV</button>
        <button class="btn" data-exp="stock,csv">Stock CSV</button>
        <button class="btn" data-exp="stock,pdf">Stock PDF</button>
        <button class="btn" data-exp="material-flow,csv">Req vs GRN vs Used CSV</button>
      </div></div>
    <div class="panel"><h3>Labour report</h3>
      <div class="filters">
        <input type="date" id="lb-from" value="${daysAgo(14)}"> →
        <input type="date" id="lb-to" value="${today()}">
        <button class="btn btn-primary" id="lb-view">View</button>
        <button class="btn" id="lb-csv">CSV</button><button class="btn" id="lb-pdf">PDF</button>
      </div><div id="lb-out"></div></div>
    ${canFinance ? `<div class="panel"><h3>Finance reports</h3>
      <div class="filters">
        <button class="btn" data-fexp="payables,csv">Payables CSV</button>
        <button class="btn" data-fexp="payables,pdf">Payables PDF</button>
        <button class="btn" data-fexp="ageing,csv">Ageing CSV</button>
        <button class="btn" data-fexp="ageing,pdf">Ageing PDF</button>
      </div></div>` : ''}
    ${['owner', 'accountant'].includes(user.role) ? '<div class="panel"><h3>Audit log</h3><div id="audit-out"></div></div>' : ''}`;

  view.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => {
    const [rep, fmt] = b.dataset.exp.split(',');
    const pid = view.querySelector('#rp-project').value;
    if (!pid) return toast('Create a project first', 'warn');
    const dt = view.querySelector('#rp-date').value;
    const extra = rep === 'dpr' ? `&report_date=${dt}` : '';
    download(`/api/reports/${rep}/${pid}?fmt=${fmt}${extra}`).catch(e => toast(e.message, 'bad'));
  });
  view.querySelectorAll('[data-fexp]').forEach(b => b.onclick = () => {
    const [rep, fmt] = b.dataset.fexp.split(',');
    download(`/api/reports/${rep}?fmt=${fmt}`).catch(e => toast(e.message, 'bad'));
  });

  const range = () => `date_from=${view.querySelector('#lb-from').value}&date_to=${view.querySelector('#lb-to').value}`;
  view.querySelector('#lb-view').onclick = async () => {
    const d = await api('GET', `/api/labour-summary?${range()}`);
    view.querySelector('#lb-out').innerHTML = table([
      { key: 'project', label: 'Project' }, { key: 'vendor', label: 'Vendor' },
      { key: 'labourers', label: 'Labourers', align: 'num' },
      { key: 'days_worked', label: 'Man-days', align: 'num' },
      { key: 'ot_hours', label: 'OT hours', align: 'num' },
      { key: 'payable', label: 'Payable', align: 'num', render: r => money(r.payable) },
    ], d.data, { empty: 'No attendance in this period.' });
  };
  view.querySelector('#lb-csv').onclick = () => download(`/api/reports/labour?${range()}&fmt=csv`);
  view.querySelector('#lb-pdf').onclick = () => download(`/api/reports/labour?${range()}&fmt=pdf`);
  view.querySelector('#lb-view').click();

  const auditOut = view.querySelector('#audit-out');
  if (auditOut) {
    let apage = 1;
    const loadAudit = async () => {
      const d = await api('GET', `/api/audit-log?page=${apage}&limit=25`);
      auditOut.innerHTML = table([
        { key: 'created_at', label: 'When', render: r => (r.created_at || '').slice(0, 16).replace('T', ' ') },
        { key: 'user_name', label: 'User' },
        { key: 'action', label: 'Action' },
        { key: 'entity_type', label: 'Entity', render: r => `${esc(r.entity_type)} #${r.entity_id ?? ''}` },
        { key: 'after_json', label: 'Detail', render: r => `<small class="muted">${esc((r.after_json || r.before_json || '').slice(0, 120))}</small>` },
      ], d.data) + pager(d.total, d.page, d.limit);
      auditOut.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { apage = Number(b.dataset.page); loadAudit(); });
    };
    await loadAudit();
  }
}
