// Marketing landing — drenched night-site world, orchestrated hero load,
// scroll-drawn workflow, verified photography, live product miniature.
import { getToken } from '../api.js';
import { icon } from '../ui.js';

const IMG = (id, w = 1600) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=80`;
const PHOTOS = {
  hero: IMG('1541888946425-d81bb19240f5', 2000),      // reinforcement + formwork on an active site
  plans: IMG('1503387762-592deb58ef4e', 1200),        // drawings on the drafting table
  crew: IMG('1504307651254-35680f356dfd', 1200),      // engineers walking the slab
  steel: IMG('1581094794329-c8112a89af12', 1200),     // checks on the steel line
  facade: IMG('1487958449943-2429e8be8625', 1600),    // finished concrete facade
};

// Miniature of the real dashboard — the product is the picture.
const MOCK = `
<div class="mock" aria-hidden="true">
  <div class="mock-bar"><span></span><span></span><span></span><i>sitepilot — dashboard</i></div>
  <div class="mock-body">
    <div class="mock-rail">${['dashboard', 'projects', 'procurement', 'materials', 'finance']
      .map((n, i) => `<div class="mock-navi ${i === 0 ? 'on' : ''}">${icon(n, 13)}</div>`).join('')}</div>
    <div class="mock-main">
      <div class="mock-kpis">
        <div><b data-mock-count="12">12</b><span>Active sites</span></div>
        <div><b>₹ <span data-mock-count="48">48</span>L</b><span>Committed</span></div>
        <div><b data-mock-count="97">97</b><span>Tasks done</span></div>
        <div class="warn"><b data-mock-count="3">3</b><span>Overdue bills</span></div>
      </div>
      <div class="mock-rows">
        ${[['Sunrise Apartments — Block A', 72], ['Metro Warehouse Extension', 41], ['Riverside Villas', 88]]
          .map(([n, p]) => `<div class="mock-row"><span>${n}</span>
            <div class="mock-barline"><div style="--w:${p}%"></div></div><b>${p}%</b></div>`).join('')}
      </div>
      <div class="mock-chip ok">GRN-0113 · stock updated</div>
      <div class="mock-chip">DPR sent · 07:00</div>
    </div>
  </div>
</div>`;

const FLOW = [
  ['Indent', 'Site raises a material request with the required date.'],
  ['Approve', 'The PM approves or rejects it in one tap — with a paper trail.'],
  ['Purchase order', 'Approved indents become vendor POs, priced and numbered.'],
  ['Goods receipt', 'The gate records the delivery; stock updates itself.'],
  ['Invoice & pay', 'Bills land against the PO. Due dates, ageing and alerts follow.'],
];

const ROLES = [
  ['Owner', 'Margins, costs and every project on one screen.'],
  ['Project Manager', 'Tasks, approvals, POs and progress without phone tag.'],
  ['Site Engineer', 'DPRs, attendance and indents from the slab, not the office.'],
  ['Storekeeper', 'Stock levels, GRNs and low-stock flags at the gate.'],
  ['Accountant', 'Ledgers, ageing buckets and payments that reconcile.'],
  ['Vendor', 'A portal for their POs, bills and payment status.'],
];

export function render(root) {
  document.documentElement.classList.add('js');
  const signedIn = !!getToken();
  const navCta = signedIn
    ? '<a class="btn-pill" href="#/dashboard">Open dashboard →</a>'
    : '<a class="btn-ghost" href="#/login">Sign in</a><a class="btn-pill" href="#/signup">Get started</a>';
  const heroCta = signedIn
    ? '<a class="btn-pill big" href="#/dashboard">Open your dashboard →</a>'
    : `<a class="btn-pill big" href="#/signup">Create your workspace</a>
       <a class="btn-ghost big" href="#/login">Try the live demo →</a>`;
  const finalCta = signedIn
    ? '<a class="btn-pill big" href="#/dashboard">Open your dashboard →</a>'
    : `<a class="btn-pill big" href="#/signup">Create your workspace</a>
       <a class="btn-ghost big" href="#/login">Sign in</a>`;
  root.innerHTML = `
<div class="landing">
  <header class="lnav">
    <a class="lnav-brand" href="#/landing">${icon('logo', 22)} SitePilot</a>
    <nav class="lnav-links">
      <a href="#how">How it works</a><a href="#field">In the field</a><a href="#roles">Who it's for</a>
    </nav>
    <div class="lnav-cta">${navCta}</div>
  </header>

  <section class="hero">
    <img class="hero-img" src="${PHOTOS.hero}" alt="Reinforcement and formwork across an active construction site" loading="eager">
    <div class="hero-veil"></div>
    <div class="hero-inner">
      <h1><span class="hl">Every site.</span><span class="hl">Every rupee.</span><span class="hl">One system.</span></h1>
      <p class="hero-sub">SitePilot runs the operational spine of a construction business —
        progress, materials, labour and payments — so the numbers reach you before the excuses do.</p>
      <div class="hero-cta">${heroCta}</div>
      <div class="hero-note">Free to run on your own server · seeded demo included</div>
    </div>
    <div class="hero-frame">${MOCK}</div>
  </section>

  <section class="lsec" id="how">
    <div class="lsec-head reveal">
      <h2>Indent to invoice, without the WhatsApp archaeology</h2>
      <p>One chain of custody for every bag of cement: requested,
         approved, ordered, received, consumed — and the bill that follows it.</p>
    </div>
    <div class="flow">
      <svg class="flow-line" viewBox="0 0 1000 60" preserveAspectRatio="none" aria-hidden="true">
        <path class="flow-path" d="M10 30 H990" pathLength="1"/>
        ${[10, 255, 500, 745, 990].map(x => `<circle class="flow-dot" cx="${x}" cy="30" r="7"/>`).join('')}
      </svg>
      <ol class="flow-steps">
        ${FLOW.map(([t, d], i) => `<li class="reveal" style="--d:${i * 90}ms">
          <span class="flow-n">${i + 1}</span><h3>${t}</h3><p>${d}</p></li>`).join('')}
      </ol>
    </div>
  </section>

  <section class="lsec lsec-field" id="field">
    <div class="lsec-head reveal">
      <h2>Built for boots, not just desks</h2>
      <p>High contrast for daylight, big targets for dusty gloves, and reports the
         head office can open before the morning pour.</p>
    </div>
    <div class="collage">
      <figure class="reveal c-a"><img src="${PHOTOS.crew}" alt="Engineers walking the slab on morning rounds" loading="lazy">
        <figcaption>Morning rounds become the day's DPR — logged where the work is.</figcaption></figure>
      <figure class="reveal c-b" style="--d:80ms"><img src="${PHOTOS.plans}" alt="Working drawings spread on the drafting table" loading="lazy">
        <figcaption>Drawings, BOQs and approvals — versioned, never lost in a boot.</figcaption></figure>
      <figure class="reveal c-c" style="--d:160ms"><img src="${PHOTOS.steel}" alt="Quality checks on the steel line" loading="lazy">
        <figcaption>Safety walks and quality checks, with the failures that matter flagged.</figcaption></figure>
      <div class="c-stat reveal" style="--d:240ms">
        <b><span data-count="45">45</span>-day</b>
        <span>credit alerts fire themselves. Vendors stop calling; you stop apologising.</span>
      </div>
    </div>
  </section>

  <section class="lsec lsec-dark">
    <div class="stats">
      <div class="reveal"><b><span data-count="10">10</span></b><span>modules, one login — projects to payables</span></div>
      <div class="reveal" style="--d:80ms"><b><span data-count="6">6</span></b><span>field roles with exactly the access they need</span></div>
      <div class="reveal" style="--d:160ms"><b><span data-count="4">4</span></b><span>ageing buckets watching every unpaid bill</span></div>
      <div class="reveal" style="--d:240ms"><b><span data-count="30">30</span>s</b><span>from site note to a client-ready DPR (PDF)</span></div>
    </div>
  </section>

  <section class="lsec" id="roles">
    <div class="lsec-head reveal">
      <h2>Six jobs. One source of truth.</h2>
    </div>
    <div class="roles">
      ${ROLES.map(([r, d], i) => `<div class="role reveal" style="--d:${i * 60}ms">
        <h3>${r}</h3><p>${d}</p></div>`).join('')}
    </div>
  </section>

  <section class="lfinal">
    <img class="lfinal-img" src="${PHOTOS.facade}" alt="Finished concrete facade against the sky" loading="lazy">
    <div class="lfinal-veil"></div>
    <div class="lfinal-inner reveal">
      <h2>Concrete cures overnight.<br>Your numbers shouldn't have to.</h2>
      <div class="hero-cta">${finalCta}</div>
    </div>
  </section>

  <footer class="lfoot">
    <span>${icon('logo', 16)} SitePilot</span>
    <span>Self-hosted construction management · <a href="#/login">Sign in</a> · <a href="#/signup">Create account</a></span>
  </footer>
</div>`;

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Section anchors would collide with the hash router — scroll instead.
  root.querySelectorAll('.lnav-links a').forEach(a => {
    a.onclick = (e) => {
      e.preventDefault();
      const target = document.getElementById(a.getAttribute('href').slice(1));
      if (target) target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    };
  });

  // Scroll reveals: enhance-only (elements are visible without JS), one-shot.
  const targets = root.querySelectorAll('.reveal, .flow-line');
  if (reduced || !('IntersectionObserver' in window)) {
    targets.forEach(el => el.classList.add('in'));
  } else {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    }, { threshold: 0.18, rootMargin: '0px 0px -6% 0px' });
    targets.forEach(el => io.observe(el));
    setTimeout(() => targets.forEach(el => el.classList.add('in')), 2600); // safety net
  }

  // Count-ups when stats enter.
  if (!reduced) {
    root.querySelectorAll('[data-count]').forEach(el => {
      const target = Number(el.dataset.count);
      const io = new IntersectionObserver((es) => {
        if (!es[0].isIntersecting) return;
        io.disconnect();
        const t0 = performance.now();
        const step = (t) => {
          const p = Math.min(1, (t - t0) / 900);
          el.textContent = Math.round(target * (1 - Math.pow(1 - p, 4)));
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      }, { threshold: 0.6 });
      io.observe(el);
    });
  }

  // Gentle parallax on the product frame; nav gains depth after scroll.
  const frame = root.querySelector('.hero-frame');
  const nav = root.querySelector('.lnav');
  if (!reduced) {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        if (frame && y < 900) frame.style.transform = `translateY(${y * -0.05}px)`;
        nav.classList.toggle('scrolled', y > 24);
        ticking = false;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }
}
