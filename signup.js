import { setSession } from '../api.js';
import { icon, toast } from '../ui.js';
import { SCENE } from './login.js';

export function render(root) {
  root.innerHTML = `<div class="login-wrap">
    <div class="login-left">
      <a class="login-brand" href="#/">${icon('logo', 24)} SitePilot</a>
      <h1>Set up your workspace.</h1>
      <p class="login-sub">You'll start as the Owner — invite your PMs, engineers,
        storekeepers and accountants from inside the app.</p>
      <form id="signup-form">
        <label class="field"><span>Your name</span>
          <input type="text" name="name" required autofocus autocomplete="name" placeholder="e.g. Arun Mehta"></label>
        <label class="field"><span>Work email</span>
          <input type="email" name="email" required autocomplete="username"></label>
        <label class="field"><span>Password</span>
          <input type="password" name="password" required minlength="8" autocomplete="new-password">
          <small>Minimum 8 characters</small></label>
        <button class="btn btn-primary btn-login" type="submit">Create account</button>
      </form>
      <div class="demo-creds">Already have an account? <a href="#/login">Sign in</a> ·
        Just exploring? <a href="#/login">Use the demo accounts</a></div>
    </div>
    <div class="login-scene">
      <div class="login-quote">
        <div class="lq-big">The first brick is free. So is the software.</div>
        <div class="lq-small">Self-hosted, no per-seat fees — your projects, your server, your data.</div>
      </div>
      ${SCENE}
    </div>
  </div>`;

  root.querySelector('#signup-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = root.querySelector('.btn-login');
    btn.disabled = true;
    btn.textContent = 'Creating workspace…';
    const f = new FormData(e.target);
    try {
      const resp = await fetch('/api/auth/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: f.get('name'), email: f.get('email'), password: f.get('password') }) });
      const data = await resp.json();
      if (!resp.ok) {
        const msg = typeof data.detail === 'string' ? data.detail
          : (Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('; ') : 'Sign-up failed');
        throw new Error(msg);
      }
      setSession(data.token, data.user);
      toast(`Welcome, ${data.user.name} — your workspace is ready`);
      location.hash = '#/dashboard';
    } catch (err) {
      toast(err.message, 'bad');
      btn.disabled = false;
      btn.textContent = 'Create account';
    }
  };
}
