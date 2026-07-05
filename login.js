import { setSession } from '../api.js';
import { esc, icon, toast } from '../ui.js';

const DEMO = [
  ['Owner', 'owner@sitepilot.test'], ['Project Manager', 'pm@sitepilot.test'],
  ['Site Engineer', 'site@sitepilot.test'], ['Storekeeper', 'store@sitepilot.test'],
  ['Accountant', 'accounts@sitepilot.test'], ['Vendor', 'vendor@sitepilot.test'],
];

// Hand-authored geometric night-site scene (no third-party assets).
export const SCENE = `
<svg viewBox="0 0 900 560" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
  <defs>
    <linearGradient id="bA" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#33465e"/><stop offset="1" stop-color="#26374b"/>
    </linearGradient>
    <linearGradient id="bB" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2a3b50"/><stop offset="1" stop-color="#203044"/>
    </linearGradient>
  </defs>

  <!-- moon + drifting specks -->
  <circle class="float-b" cx="700" cy="86" r="26" fill="#dfe9f2" opacity="0.9"/>
  <circle class="float-a" cx="140" cy="120" r="3" fill="#8fb4c9" opacity="0.5"/>
  <circle class="float-b" cx="250" cy="70" r="2" fill="#8fb4c9" opacity="0.4"/>
  <circle class="float-a" cx="560" cy="140" r="2.5" fill="#8fb4c9" opacity="0.45"/>

  <!-- tower crane -->
  <g stroke="#9fc3d4" stroke-width="4" fill="none" opacity="0.95">
    <path d="M175 555 V210 M160 555 V210 M160 240 h15 M160 300 h15 M160 360 h15 M160 420 h15 M160 480 h15
             M160 210 l15 30 M175 240 l-15 30 M160 300 l15 30 M175 360 l-15 30 M160 420 l15 30"/>
    <path d="M60 210 H430 M60 210 l108 -34 M430 210 l-262 -34 M168 176 v34"/>
    <path d="M60 210 v26 M100 210 v20"/>
    <path d="M355 210 v70"/>
  </g>
  <rect x="345" y="280" width="22" height="20" rx="3" fill="#2f6b86"/>
  <rect x="63" y="228" width="30" height="22" rx="3" fill="#3a4f66"/>

  <!-- building under construction (left of crane's reach) -->
  <g>
    <rect x="250" y="330" width="180" height="225" fill="url(#bA)"/>
    <g stroke="#4a5f78" stroke-width="3">
      <path d="M250 385 h180 M250 440 h180 M250 495 h180"/>
      <path d="M295 330 v225 M340 330 v225 M385 330 v225"/>
    </g>
    <!-- lit floors -->
    <g fill="#e8b24a">
      <rect x="258" y="392" width="28" height="12" rx="2" opacity="0.85"/>
      <rect x="348" y="447" width="28" height="12" rx="2" opacity="0.7"/>
      <rect x="303" y="502" width="28" height="12" rx="2" opacity="0.8"/>
    </g>
    <path d="M250 330 h180" stroke="#9fc3d4" stroke-width="4"/>
  </g>

  <!-- finished towers -->
  <g>
    <rect x="490" y="250" width="150" height="305" fill="url(#bB)"/>
    <g fill="#b8d2e0" opacity="0.85">
      ${Array.from({ length: 6 }, (_, r) => Array.from({ length: 4 }, (_, c) =>
        `<rect x="${508 + c * 30}" y="${272 + r * 46}" width="16" height="22" rx="2"
           opacity="${(r * 4 + c) % 3 === 0 ? 0.9 : 0.25}"/>`).join('')).join('')}
    </g>
  </g>
  <g>
    <rect x="668" y="330" width="120" height="225" fill="url(#bA)"/>
    <g fill="#b8d2e0">
      ${Array.from({ length: 4 }, (_, r) => Array.from({ length: 3 }, (_, c) =>
        `<rect x="${684 + c * 32}" y="${352 + r * 50}" width="18" height="24" rx="2"
           opacity="${(r * 3 + c) % 4 === 0 ? 0.85 : 0.2}"/>`).join('')).join('')}
    </g>
  </g>

  <!-- low rise + hoarding -->
  <rect x="810" y="420" width="90" height="135" fill="url(#bB)"/>
  <rect x="0" y="470" width="120" height="85" fill="url(#bB)"/>
  <g fill="#2f6b86">
    <rect x="12" y="486" width="20" height="14" rx="2" opacity="0.8"/>
    <rect x="52" y="486" width="20" height="14" rx="2" opacity="0.4"/>
  </g>

  <!-- ground line -->
  <rect x="0" y="552" width="900" height="8" fill="#17222f"/>
</svg>`;

export function render(root) {
  root.innerHTML = `<div class="login-wrap">
    <div class="login-left">
      <a class="login-brand" href="#/">${icon('logo', 24)} SitePilot</a>
      <h1>Run every site from one place.</h1>
      <p class="login-sub">Projects, materials, labour, and payments — the operational spine of your construction business.</p>
      <form id="login-form">
        <label class="field"><span>Email</span><input type="email" name="email" required autofocus autocomplete="username"></label>
        <label class="field"><span>Password</span><input type="password" name="password" required autocomplete="current-password"></label>
        <button class="btn btn-primary btn-login" type="submit">Sign in</button>
      </form>
      <div class="demo-creds">New here? <a href="#/signup">Create your workspace</a><br><br>
        <b>Demo accounts</b> — password <code id="pw">Password123!</code>, click to fill:<br>
        ${DEMO.map(([r, e]) => `${esc(r)} <code class="demo-email">${e}</code>`).join(' · ')}
      </div>
    </div>
    <div class="login-scene">
      <div class="login-quote">
        <div class="lq-big">Concrete cures overnight. Your numbers shouldn't have to.</div>
        <div class="lq-small">DPRs, stock levels, wages and payables — live, in one system your whole team can use.</div>
      </div>
      ${SCENE}
    </div>
  </div>`;

  root.querySelectorAll('.demo-email').forEach(c => {
    c.onclick = () => {
      root.querySelector('[name=email]').value = c.textContent;
      root.querySelector('[name=password]').value = 'Password123!';
    };
  });
  root.querySelector('#login-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = root.querySelector('.btn-login');
    btn.disabled = true;
    btn.textContent = 'Signing in…';
    const email = root.querySelector('[name=email]').value;
    const password = root.querySelector('[name=password]').value;
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }) });
      const data = await resp.json();
      if (!resp.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Login failed');
      setSession(data.token, data.user);
      location.hash = '#/dashboard';
    } catch (err) {
      toast(err.message, 'bad');
      btn.disabled = false;
      btn.textContent = 'Sign in';
    }
  };
}
