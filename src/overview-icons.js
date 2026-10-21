// Fixed SVG paths shared by the preview shell and its calculated cards.
const paths = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  charts: '<path d="M4 20V10m6 10V4m6 16v-7m5 7H2"/>',
  insights: '<path d="m3 17 6-6 4 4 8-10m-6 0h6v6"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="white"/><circle cx="15" cy="17" r="3" fill="white"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  back: '<path d="m10 6-6 6 6 6M4 12h16"/>',
  filter: '<path d="M4 5h16l-6 7v6l-4 2v-8Z"/>',
  account: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  dataset: '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M4 9h16M10 9v12M4 15h16"/>',
  sparkles: '<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6ZM20 2v4m-2-2h4"/>',
  money: '<circle cx="12" cy="12" r="9"/><path d="M15 8.5h-4.5a2 2 0 0 0 0 4h3a2 2 0 0 1 0 4H9M12 6v12"/>',
  percent: '<path d="m6 18 12-12"/><circle cx="7" cy="7" r="3"/><circle cx="17" cy="17" r="3"/>',
  orders: '<path d="M3 4h2l3 12h11l2-8H6"/><circle cx="10" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
  units: '<path d="m12 3 9 5v9l-9 5-9-5V8Zm0 10 9-5M12 13 3 8m9 5v9M7 5.8l9 5"/>',
};

export function overviewIcon(name) {
  return `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.charts}</svg>`;
}
