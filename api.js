// Thin API client: JWT storage, JSON + multipart requests, file downloads.

export function getToken() { return localStorage.getItem('sp_token'); }
export function setSession(token, user) {
  localStorage.setItem('sp_token', token);
  localStorage.setItem('sp_user', JSON.stringify(user));
}
export function clearSession() {
  localStorage.removeItem('sp_token');
  localStorage.removeItem('sp_user');
}
export function currentUser() {
  try { return JSON.parse(localStorage.getItem('sp_user')); } catch { return null; }
}

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === 'string' ? detail : JSON.stringify(detail)); this.status = status; this.detail = detail; }
}

async function handle(resp) {
  if (resp.status === 401) { clearSession(); location.hash = '#/login'; throw new ApiError(401, 'Session expired'); }
  const text = await resp.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!resp.ok) {
    let msg = data && data.detail ? data.detail : `HTTP ${resp.status}`;
    if (Array.isArray(msg)) msg = msg.map(e => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join('; ');
    throw new ApiError(resp.status, msg);
  }
  return data;
}

export async function api(method, path, body) {
  const opts = { method, headers: { Authorization: `Bearer ${getToken()}` } };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  return handle(await fetch(path, opts));
}

export async function apiForm(method, path, formData) {
  return handle(await fetch(path, { method, headers: { Authorization: `Bearer ${getToken()}` }, body: formData }));
}

export async function download(path, fallbackName) {
  const resp = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!resp.ok) throw new ApiError(resp.status, 'Download failed');
  const blob = await resp.blob();
  const dispo = resp.headers.get('Content-Disposition') || '';
  const m = dispo.match(/filename="?([^";]+)"?/);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = m ? m[1] : (fallbackName || 'download');
  a.click();
  URL.revokeObjectURL(a.href);
}
