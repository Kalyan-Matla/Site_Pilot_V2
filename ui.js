// Shared UI toolkit: escaping, animated tables, pagination, dialog forms,
// badges, toasts, skeletons, empty states, comment threads, KPI count-ups.
import { api } from './api.js';
import { icon } from './icons.js';

export const esc = (s) => s == null ? '' : String(s)
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');

export const money = (n) => n == null ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const fmtDate = (s) => s ? s.slice(0, 10) : '—';
export const today = () => new Date().toISOString().slice(0, 10);
export const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

const STATUS_CLASS = {
  active: 'ok', done: 'ok', approved: 'ok', paid: 'ok', received: 'ok', fulfilled: 'ok', resolved: 'ok',
  passed: 'ok', present: 'ok', issued: 'info', in_progress: 'info', under_review: 'info', submitted: 'info',
  partially_received: 'info', ordered: 'info', planned: 'muted', todo: 'muted', draft: 'muted', na: 'muted',
  open: 'warn', pending: 'warn', on_hold: 'warn', half_day: 'warn', blocked: 'bad', overdue: 'bad',
  rejected: 'bad', cancelled: 'bad', failed: 'bad', fail: 'bad', absent: 'bad', critical: 'bad', high: 'bad',
  medium: 'warn', low: 'muted', maintenance: 'warn', in_use: 'info', available: 'ok', retired: 'muted',
  completed: 'ok', closed: 'muted', safety: 'warn', quality: 'info', cash: 'warn', bank: 'info',
  upi: 'info', cheque: 'info', material: 'info', labour: 'warn', service: 'muted',
};
export const badge = (s, label) => s == null ? '' :
  `<span class="badge badge-${STATUS_CLASS[s] || 'muted'}">${esc(String(label ?? s).replaceAll('_', ' '))}</span>`;

export function toast(msg, type = 'ok') {
  const root = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => { el.classList.add('leaving'); setTimeout(() => el.remove(), 220); }, 4000);
}

export function spinner() {
  return `<div class="panel skeleton" aria-busy="true" aria-label="Loading">
    <div class="sk-row"></div><div class="sk-row"></div><div class="sk-row"></div>
    <div class="sk-row"></div><div class="sk-row"></div></div>`;
}

export function emptyState(text, iconName = 'inbox') {
  return `<div class="empty">${icon(iconName, 30)}<div>${esc(text)}</div></div>`;
}

// columns: [{key, label, render?(row), align?}]
export function table(columns, rows, opts = {}) {
  if (!rows || !rows.length) return emptyState(opts.empty || 'No records found.', opts.emptyIcon);
  const head = columns.map(c => `<th class="${c.align || ''}">${esc(c.label)}</th>`).join('');
  const body = rows.map((r, i) => {
    const tds = columns.map(c =>
      `<td class="${c.align || ''}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join('');
    const attrs = opts.rowAttrs ? opts.rowAttrs(r) : '';
    return `<tr style="--i:${i}" ${attrs}>${tds}</tr>`;
  }).join('');
  return `<div class="table-wrap"><table class="table-animate"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function pager(total, page, limit) {
  if (!total || total <= limit) return '';
  const pages = Math.ceil(total / limit);
  return `<div class="pager">
    <button class="btn btn-sm" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>‹ Prev</button>
    <span>Page ${page} of ${pages} · ${total} records</span>
    <button class="btn btn-sm" data-page="${page + 1}" ${page >= pages ? 'disabled' : ''}>Next ›</button>
  </div>`;
}

// Count-up animation for KPI figures. Call after inserting markup:
// <span data-countup="12345" data-prefix="₹ ">…</span>
export function animateCounters(root) {
  if (reducedMotion()) return;
  root.querySelectorAll('[data-countup]').forEach(el => {
    const target = Number(el.dataset.countup);
    if (!isFinite(target) || target === 0) return;
    const prefix = el.dataset.prefix || '';
    const dur = 700, t0 = performance.now();
    const fmt = (v) => prefix + Number(v.toFixed(0)).toLocaleString('en-IN');
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 4); // ease-out-quart
      el.textContent = fmt(target * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

// Progress bars fill from 0 on first paint: width set on next frame.
export function animateBars(root) {
  root.querySelectorAll('.progressbar > div[data-w]').forEach(el => {
    if (reducedMotion()) { el.style.width = el.dataset.w + '%'; return; }
    el.style.width = '0%';
    requestAnimationFrame(() => requestAnimationFrame(() => { el.style.width = el.dataset.w + '%'; }));
  });
}
export const bar = (pct) => `<div class="progressbar"><div data-w="${Math.max(0, Math.min(100, pct || 0))}"></div></div>`;

// Generic dialog form. fields: [{name,label,type(text|number|date|select|textarea|checkbox|file),options,value,required,step,placeholder,help}]
// Resolves to a values object (files under values[name] as File), or null if cancelled.
export function showForm(title, fields, opts = {}) {
  return new Promise((resolve) => {
    const root = document.getElementById('modal-root');
    const controls = fields.map(f => {
      const req = f.required ? 'required' : '';
      const val = f.value != null ? esc(f.value) : '';
      let input;
      if (f.type === 'select') {
        const optHtml = (f.options || []).map(o => {
          const [v, label] = Array.isArray(o) ? o : [o, o];
          return `<option value="${esc(v)}" ${String(f.value) === String(v) ? 'selected' : ''}>${esc(label)}</option>`;
        }).join('');
        input = `<select name="${f.name}" ${req}>${f.required ? '' : '<option value="">—</option>'}${optHtml}</select>`;
      } else if (f.type === 'textarea') {
        input = `<textarea name="${f.name}" ${req} placeholder="${esc(f.placeholder || '')}">${val}</textarea>`;
      } else if (f.type === 'checkbox') {
        input = `<input type="checkbox" name="${f.name}" ${f.value ? 'checked' : ''}>`;
      } else if (f.type === 'file') {
        input = `<input type="file" name="${f.name}" ${req}>`;
      } else {
        input = `<input type="${f.type || 'text'}" name="${f.name}" value="${val}" ${req} ${f.step ? `step="${f.step}"` : ''} placeholder="${esc(f.placeholder || '')}">`;
      }
      return `<label class="field ${f.type === 'checkbox' ? 'field-inline' : ''}"><span>${esc(f.label)}${f.required ? ' *' : ''}</span>${input}${f.help ? `<small>${esc(f.help)}</small>` : ''}</label>`;
    }).join('');
    root.innerHTML = `<div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal">
      <div class="modal-head"><h3>${esc(title)}</h3><button class="modal-x" type="button" aria-label="Close">✕</button></div>
      <form class="modal-body">${controls}${opts.extraHtml || ''}
        <div class="modal-actions">
          <button type="button" class="btn" data-cancel>Cancel</button>
          <button type="submit" class="btn btn-primary">${esc(opts.submitLabel || 'Save')}</button>
        </div>
      </form></div></div>`;
    const backdrop = root.querySelector('.modal-backdrop');
    const close = (result) => {
      if (reducedMotion()) { root.innerHTML = ''; resolve(result); return; }
      backdrop.classList.add('closing');
      setTimeout(() => { root.innerHTML = ''; resolve(result); }, 190);
    };
    const onKey = (e) => { if (e.key === 'Escape') { document.removeEventListener('keydown', onKey); close(null); } };
    document.addEventListener('keydown', onKey);
    root.querySelector('.modal-x').onclick = () => close(null);
    root.querySelector('[data-cancel]').onclick = () => close(null);
    backdrop.onclick = (e) => { if (e.target === backdrop) close(null); };
    const first = root.querySelector('input, select, textarea');
    if (first) setTimeout(() => first.focus(), 60);
    root.querySelector('form').onsubmit = (e) => {
      e.preventDefault();
      const values = {};
      for (const f of fields) {
        const el = root.querySelector(`[name="${f.name}"]`);
        if (!el) continue;
        if (f.type === 'checkbox') values[f.name] = el.checked;
        else if (f.type === 'file') values[f.name] = el.files[0] || null;
        else if (f.type === 'number') values[f.name] = el.value === '' ? null : Number(el.value);
        else values[f.name] = el.value === '' ? null : el.value;
      }
      document.removeEventListener('keydown', onKey);
      close(values);
    };
    // animate bars/tables placed inside the dialog's extraHtml
    animateBars(root);
  });
}

export function confirmBox(message) {
  return showForm('Confirm', [], { extraHtml: `<p>${esc(message)}</p>`, submitLabel: 'Confirm' })
    .then(v => v !== null);
}

// Comment thread widget for any entity.
export async function commentsHtml(entityType, entityId) {
  try {
    const { data } = await api('GET', `/api/comments?entity_type=${entityType}&entity_id=${entityId}`);
    const items = data.map(c => `<div class="comment"><b>${esc(c.user_name)}</b>
      <span class="muted">${esc((c.created_at || '').slice(0, 16).replace('T', ' '))}</span>
      <div>${esc(c.body)}</div></div>`).join('');
    return `<div class="comments" data-etype="${entityType}" data-eid="${entityId}">
      <h4>Comments · ${data.length}</h4>${items || '<div class="muted">No comments yet — start the thread.</div>'}
      <div class="comment-form"><input type="text" placeholder="Write a comment…" class="comment-input" aria-label="Write a comment">
      <button class="btn btn-sm btn-primary comment-send">Send</button></div></div>`;
  } catch { return ''; }
}

export function wireComments(container, refresh) {
  container.querySelectorAll('.comments').forEach(box => {
    const send = box.querySelector('.comment-send');
    const input = box.querySelector('.comment-input');
    if (!send) return;
    const submit = async () => {
      if (!input.value.trim()) return;
      try {
        await api('POST', '/api/comments', {
          entity_type: box.dataset.etype, entity_id: Number(box.dataset.eid), body: input.value.trim() });
        toast('Comment added');
        refresh && refresh();
      } catch (e) { toast(e.message, 'bad'); }
    };
    send.onclick = submit;
    input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } };
  });
}

export function tabs(list, active) {
  return `<div class="tabs" role="tablist">${list.map(t =>
    `<button class="tab ${t.id === active ? 'tab-active' : ''}" role="tab"
      aria-selected="${t.id === active}" data-tab="${t.id}">${esc(t.label)}</button>`
  ).join('')}</div>`;
}

export { icon };
