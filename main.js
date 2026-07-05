// App shell: hash router, icon rail, translucent topbar, route transitions.
import { api, clearSession, currentUser, getToken } from './api.js';
import { esc, icon, toast } from './ui.js';

import * as landing from './pages/landing.js';
import * as login from './pages/login.js';
import * as signup from './pages/signup.js';
import * as dashboard from './pages/dashboard.js';
import * as projects from './pages/projects.js';
import * as project from './pages/project.js';
import * as materials from './pages/materials.js';
import * as procurement from './pages/procurement.js';
import * as vendors from './pages/vendors.js';
import * as finance from './pages/finance.js';
import * as reports from './pages/reports.js';
import * as users from './pages/users.js';
import * as equipment from './pages/equipment.js';
import * as notifications from './pages/notifications.js';

const ROLE_LABELS = { owner: 'Owner', pm: 'Project Manager', site: 'Site Engineer',
  store: 'Storekeeper', accountant: 'Accountant', vendor: 'Vendor' };

// route: [regex, module, title, nav item id]
const ROUTES = [
  [/^#\/dashboard$/, dashboard, 'Dashboard', 'dashboard'],
  [/^#\/projects$/, projects, 'Projects', 'projects'],
  [/^#\/projects\/(\d+)(?:\/(\w+))?$/, project, 'Project', 'projects'],
  [/^#\/materials$/, materials, 'Material Master', 'materials'],
  [/^#\/procurement(?:\/(\w+))?$/, procurement, 'Procurement', 'procurement'],
  [/^#\/vendors$/, vendors, 'Vendors & Work Orders', 'vendors'],
  [/^#\/finance(?:\/(\w+))?$/, finance, 'Finance', 'finance'],
  [/^#\/reports$/, reports, 'Reports & Exports', 'reports'],
  [/^#\/users$/, users, 'Users', 'users'],
  [/^#\/equipment$/, equipment, 'Equipment', 'equipment'],
  [/^#\/notifications$/, notifications, 'Notifications', 'notifications'],
];

// nav item -> [label, icon, roles allowed]
const NAV = [
  ['dashboard', 'Dashboard', 'dashboard', ['owner', 'pm', 'site', 'store', 'accountant', 'vendor']],
  ['projects', 'Projects', 'projects', ['owner', 'pm', 'site', 'store', 'accountant']],
  ['procurement', 'Procurement', 'procurement', ['owner', 'pm', 'site', 'store', 'vendor']],
  ['materials', 'Materials', 'materials', ['owner', 'pm', 'store']],
  ['vendors', 'Vendors', 'vendors', ['owner', 'pm', 'accountant', 'vendor']],
  ['finance', 'Finance', 'finance', ['owner', 'pm', 'accountant', 'vendor']],
  ['equipment', 'Equipment', 'equipment', ['owner', 'pm', 'site', 'store']],
  ['reports', 'Reports', 'reports', ['owner', 'pm', 'accountant']],
  ['users', 'Users', 'users', ['owner']],
];

let unreadTimer = null;

async function pollUnread() {
  try {
    const d = await api('GET', '/api/notifications?limit=1&unread_only=1');
    const bell = document.querySelector('.bell');
    if (!bell) return;
    const dot = bell.querySelector('.dot');
    if (d.unread > 0) {
      if (dot) dot.textContent = d.unread;
      else bell.insertAdjacentHTML('beforeend', `<span class="dot">${d.unread}</span>`);
    } else if (dot) dot.remove();
  } catch { /* ignore */ }
}

function layout(user, title, activeNav) {
  const items = NAV.filter(([, , , roles]) => roles.includes(user.role))
    .map(([id, label, ico]) =>
      `<a href="#/${id}" class="${id === activeNav ? 'active' : ''}">${icon(ico)}<span>${label}</span></a>`).join('');
  return `<div class="layout">
    <aside class="sidebar">
      <a class="logo" href="#/landing" title="About SitePilot">${icon('logo', 22)}<span>SitePilot</span></a>
      <nav>${items}</nav>
      <div class="whoami"><b>${esc(user.name)}</b>${ROLE_LABELS[user.role] || user.role}
        <div><a href="#" id="logout">Sign out</a></div></div>
    </aside>
    <div class="main">
      <div class="topbar"><h1 id="page-title">${esc(title)}</h1>
        <div class="topbar-right">
          <button class="bell" title="Notifications" aria-label="Notifications">${icon('bell', 17)}</button>
        </div>
      </div>
      <div class="content"><div class="page" id="view"></div></div>
    </div></div>`;
}

async function route() {
  const app = document.getElementById('app');
  const hash = location.hash || '#/';
  if (!getToken()) {
    if (hash === '#/login') { login.render(app); return; }
    if (hash === '#/signup') { signup.render(app); return; }
    if (hash === '#/' || hash === '#/landing') { landing.render(app); return; }
    location.hash = '#/';
    return;
  }
  if (hash === '#/landing') { landing.render(app); return; }  // viewable even when signed in
  if (['#/login', '#/signup', '#/'].includes(hash)) { location.hash = '#/dashboard'; return; }

  let user = currentUser();
  if (!user) {
    try { user = await api('GET', '/api/auth/me'); localStorage.setItem('sp_user', JSON.stringify(user)); }
    catch { return; }
  }
  const match = ROUTES.find(([re]) => re.test(hash));
  if (!match) { location.hash = '#/dashboard'; return; }
  const [re, mod, title, navId] = match;
  const params = hash.match(re).slice(1);

  app.innerHTML = layout(user, title, navId);
  document.getElementById('logout').onclick = (e) => {
    e.preventDefault(); clearSession(); location.hash = '#/login';
  };
  document.querySelector('.bell').onclick = () => { location.hash = '#/notifications'; };
  pollUnread();
  if (unreadTimer) clearInterval(unreadTimer);
  unreadTimer = setInterval(pollUnread, 45000);

  const view = document.getElementById('view');
  try {
    await mod.render(view, { user, params, setTitle: (t) => { document.getElementById('page-title').textContent = t; } });
  } catch (e) {
    console.error(e);
    view.innerHTML = `<div class="panel"><h3>Something went wrong</h3><p class="muted">${esc(e.message)}</p></div>`;
    toast(e.message, 'bad');
  }
}

window.addEventListener('hashchange', route);
route();
