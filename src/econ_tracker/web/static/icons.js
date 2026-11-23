/* Minimalist monochrome outline SVG silhouettes for Rust & Warframe subcategories */

export const SUBCATEGORY_ICONS = {
  // Rust Clothing & Armor
  hoodie: `<svg viewBox="0 0 24 24"><path d="M8 5a4 4 0 0 1 8 0l4 3-2 4-2-1v9H8v-9l-2 1-2-4 4-3Z"/><path d="M9.5 5.5c.8 1.3 4.2 1.3 5 0"/><path d="M12 10v4"/></svg>`,
  pants: `<svg viewBox="0 0 24 24"><path d="M7 4h10l1.5 16h-4.5l-2-9-2 9H5.5L7 4Z"/><path d="M7 7h10"/></svg>`,
  facemask: `<svg viewBox="0 0 24 24"><path d="M6 5c2-2 10-2 12 0l1 7c0 5-3.5 8-7 9-3.5-1-7-4-7-9l1-7Z"/><path d="M8.5 10.5h2.5M13 10.5h2.5M10 15.5v2M12 15v3M14 15.5v2"/></svg>`,
  chestplate: `<svg viewBox="0 0 24 24"><path d="M7 4h3l2 2 2-2h3l2 4-2 3v9H7v-9L5 8l2-4Z"/><path d="M9 11h6v5H9z"/></svg>`,
  kilt: `<svg viewBox="0 0 24 24"><path d="M6 5h12l2 14H4L6 5Z"/><path d="M6 9h12M10 9v10M14 9v10"/></svg>`,
  jacket: `<svg viewBox="0 0 24 24"><path d="M8 4l4 3 4-3 4 3-2 5-2-1v9H8v-9l-2 1-2-5 4-3Z"/><path d="M12 7v13"/></svg>`,
  gloves: `<svg viewBox="0 0 24 24"><path d="M7 11V6a1 1 0 0 1 2 0v4M9 10V5a1 1 0 0 1 2 0v5M11 10V5a1 1 0 0 1 2 0v5M13 10V6a1 1 0 0 1 2 0v6l1.8-1.8a1.2 1.2 0 0 1 1.7 1.7L15 17v3H8v-3l-1-6Z"/></svg>`,
  boots: `<svg viewBox="0 0 24 24"><path d="M7 4h6v9l5 2a2 2 0 0 1 1 1.8V20H5v-3l2-2V4Z"/><path d="M5 18h14"/></svg>`,
  headgear: `<svg viewBox="0 0 24 24"><path d="M5 14a7 7 0 0 1 14 0v2H5v-2Z"/><path d="M3 16h18v2H3z"/></svg>`,
  shirt: `<svg viewBox="0 0 24 24"><path d="M8 4l4 2 4-2 4 3-2 4-2-1v10H8V10l-2 1-2-4 4-3Z"/></svg>`,
  hazmat: `<svg viewBox="0 0 24 24"><circle cx="12" cy="7" r="4"/><path d="M9.5 6.5h5v2h-5z"/><path d="M7 12h10l1 8H6l1-8Z"/></svg>`,

  // Rust Weapons
  ak47: `<svg viewBox="0 0 24 24"><path d="M2 13l3-2h11l2-2h4v2h-3l-1 2h-4l1 5-2 .5-1.5-5.5H8l-3 3-3-1v-2Z"/><path d="M14 11V8"/></svg>`,
  mp5: `<svg viewBox="0 0 24 24"><path d="M3 11h14l2-1h2v2h-2l-1 2h-4l-1 5h-2l1-5H7l-2 2H3v-5Z"/></svg>`,
  lr300: `<svg viewBox="0 0 24 24"><path d="M2 12h15l2-1h3v2h-3l-1 2h-5v4h-2v-4H7l-3 2H2v-5Z"/><path d="M9 12V9h4v3"/></svg>`,
  thompson: `<svg viewBox="0 0 24 24"><path d="M2 13l4-2h11l1-1h4v2h-4l-1 2h-5v5h-2v-5H7l-3 2H2v-3Z"/></svg>`,
  sar: `<svg viewBox="0 0 24 24"><path d="M2 12h14l2-1h4v2h-4l-2 2h-5l-1 4H8l1-4H5l-3 2v-5Z"/></svg>`,
  sniper: `<svg viewBox="0 0 24 24"><path d="M1 13h17l2-1h3v2h-3l-2 1H8l-4 3H2v-5Z"/><path d="M7 10h6M10 10v3"/></svg>`,
  shotgun: `<svg viewBox="0 0 24 24"><path d="M2 13l4-2h15v2H8l-3 3H2v-3Z"/><path d="M10 13h6"/></svg>`,
  pistol: `<svg viewBox="0 0 24 24"><path d="M4 9h14v3h-5l-2 7H8l1.5-7H4V9Z"/><path d="M11 12v2"/></svg>`,
  custom_smg: `<svg viewBox="0 0 24 24"><path d="M4 10h13v3h-4l-1 6h-2l1-6H6l-2 2v-5Z"/></svg>`,

  // Rust Deployables & Tools
  furnace: `<svg viewBox="0 0 24 24"><path d="M9 3h6l1 6 3 4v7H5v-7l3-4 1-6Z"/><path d="M10 20v-4a2 2 0 0 1 4 0v4"/></svg>`,
  garage_door: `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="1"/><path d="M4 8h16M4 12h16M4 16h16"/></svg>`,
  sheet_metal_door: `<svg viewBox="0 0 24 24"><rect x="6" y="3" width="12" height="18" rx="1"/><path d="M14 12h1.5"/><path d="M6 8h12M6 16h12"/></svg>`,
  armored_door: `<svg viewBox="0 0 24 24"><rect x="6" y="3" width="12" height="18" rx="1"/><rect x="9" y="6" width="6" height="4"/><circle cx="15" cy="14" r="1"/></svg>`,
  storage_box: `<svg viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="12" rx="1.5"/><path d="M3 11h18M10 11v3h4v-3"/></svg>`,
  sleeping_bag: `<svg viewBox="0 0 24 24"><rect x="6" y="3" width="12" height="18" rx="3"/><path d="M6 8h12M9 5.5h6"/></svg>`,
  hatchet: `<svg viewBox="0 0 24 24"><path d="M6 20L15 5"/><path d="M13 6l5-2c1 2.5 1 5.5-1 8l-4-2.5"/></svg>`,
  pickaxe: `<svg viewBox="0 0 24 24"><path d="M6 20L16 6"/><path d="M8 5c4-1.5 9 0 12 4M14 8l2-2"/></svg>`,
  rock: `<svg viewBox="0 0 24 24"><path d="M6 16l-2-5 4-6h7l5 5-2 7-7 2-5-3Z"/></svg>`,
  hammer: `<svg viewBox="0 0 24 24"><path d="M5 19l9-9"/><path d="M12 6l4-3 5 5-3 4-6-6Z"/></svg>`,

  // Warframe Subcategories
  prime_set: `<svg viewBox="0 0 24 24"><path d="M12 2l5 4-2 6 3 8-6-3-6 3 3-8-2-6 5-4Z"/><circle cx="12" cy="9" r="1.5"/></svg>`,
  blueprint: `<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>`,
  primary: `<svg viewBox="0 0 24 24"><path d="M2 13l4-3h10l3-2h3v3h-3l-2 2H8l-4 3-2-1v-2Z"/><path d="M11 13l2 4"/></svg>`,
  secondary: `<svg viewBox="0 0 24 24"><path d="M5 8h13v3.5h-5L11 19H8l1.5-7.5H5V8Z"/></svg>`,
  melee: `<svg viewBox="0 0 24 24"><path d="M4 20l5-5m0 0L19 5l-2-2L7 13m2 2l-2-2m0 0l-2 2"/></svg>`,
  mod: `<svg viewBox="0 0 24 24"><polygon points="12 3 20 8 20 16 12 21 4 16 4 8"/><circle cx="12" cy="12" r="2.5"/></svg>`,
  aura: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/></svg>`,
  stance: `<svg viewBox="0 0 24 24"><path d="M5 19L19 5M14 5h5v5M5 9l4 4m6 2l4 4"/></svg>`,
  augment: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="M12 8v8M8 12h8"/></svg>`,
  arcane: `<svg viewBox="0 0 24 24"><path d="M12 2l6 6-6 14L6 8l6-6Z"/><path d="M6 8h12"/></svg>`,

  default: `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 12h6M12 9v6"/></svg>`,
};

export function getSubcategoryIcon(code) {
  return SUBCATEGORY_ICONS[code] || SUBCATEGORY_ICONS.default;
}
