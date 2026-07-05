// Inline SVG icon set — 20px grid, 1.6 stroke, round caps. Hand-authored, no
// third-party assets. Usage: icon('projects'), icon('bell', 16).

const PATHS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  projects: '<path d="M3 21h18"/><path d="M5 21V7l7-4v18"/><path d="M19 21V11l-7-4"/><path d="M9 9v.01M9 12v.01M9 15v.01M9 18v.01"/>',
  procurement: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  materials: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 17.5 9 5 9-5"/>',
  vendors: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  finance: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><circle cx="12" cy="12" r="3"/><path d="M6 9v.01M18 15v.01"/>',
  equipment: '<path d="M14.7 6.3a4.5 4.5 0 0 0-6 5.6L3 17.6a2.1 2.1 0 0 0 3 3l5.6-5.7a4.5 4.5 0 0 0 5.6-6L14 12l-2-2 2.7-3.7Z"/>',
  reports: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 14.5 11 10l3 3 5.5-6.5"/>',
  users: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4S6 13 6 8Z"/><path d="M10.3 20a2 2 0 0 0 3.4 0"/>',
  logout: '<path d="M9 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  logo: '<path d="M2 21h20"/><path d="M4 21V8h7v13"/><path d="M11 8 7.5 3H4v5"/><path d="M14 21V12h6v9"/><path d="M7 12v.01M7 16v.01M17 15v.01M17 18v.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 19h16"/>',
  photo: '<rect x="3" y="5" width="18" height="15" rx="2.5"/><circle cx="9" cy="10.5" r="1.6"/><path d="m4 18 5-5 3.5 3.5L16 13l4 5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>',
  inbox: '<path d="M4 4h16v12l-4 4H8l-4-4Z" /><path d="M4 13h5l1.5 2.5h3L15 13h5"/>',
  doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/>',
  check: '<path d="m4 12.5 5.5 5.5L20 6.5"/>',
  alert: '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 10v4M12 17.5v.01"/>',
  comment: '<path d="M21 12a8 8 0 0 1-8 8H4l2.4-3A8 8 0 1 1 21 12Z"/>',
  coins: '<circle cx="9" cy="8" r="6"/><path d="M15.5 8.5a6 6 0 1 1-7 7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  truck: '<path d="M1 4h14v12H1z"/><path d="M15 9h4l4 4v3h-8"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  flag: '<path d="M5 21V4"/><path d="M5 4h13l-2.5 4L18 12H5"/>',
};

export function icon(name, size = 18, cls = '') {
  const p = PATHS[name] || PATHS.doc;
  return `<svg class="ico ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true">${p}</svg>`;
}
