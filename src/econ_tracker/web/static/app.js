const PLT_USD_RATE = 0.04999;

const RARITY_UK = {
  common: 'Звичайний',
  uncommon: 'Незвичайний',
  rare: 'Рідкісний',
  legendary: 'Легендарний',
  prime: 'Прайм',
};

const ROLE_UK = {
  guest: 'Гість',
  user: 'Користувач',
  analyst: 'Аналітик',
  admin: 'Адміністратор',
};

const CATEGORY_UK = {
  weapons: 'Зброя',
  clothing: 'Одяг та броня',
  deployables: 'Конструкції та двері',
  tools: 'Інструменти',
  warframes: 'Варфрейми',
  mods: 'Моди',
  arcanes: 'Містифікатори',
  relics: 'Реліквії',
  companions: 'Компаньйони',
  other: 'Інше',
};

const SUBCATEGORY_UK = {
  prime_set: 'Прайм-комплект',
  blueprint: 'Кресленик',
  primary: 'Основна зброя',
  secondary: 'Допоміжна зброя',
  melee: 'Ближній бій',
  mod: 'Мод',
  aura: 'Аура',
  stance: 'Стійка',
  augment: 'Аугмент',
  arcane: 'Містифікатор',
  void_relic: 'Реліквія Порожнечі',
  weapon_set: 'Комплект зброї',
  weapon_part: 'Компонент зброї',
  companion: 'Супутник',
  misc: 'Інше',
  general: 'Загальне',
};

function formatCategoryLabel(code) {
  return CATEGORY_UK[code] || code;
}

function formatSubcategoryLabel(code, gameCode) {
  if (SUBCATEGORY_UK[code]) return SUBCATEGORY_UK[code];
  return String(code || '')
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ') || (gameCode === 'warframe' ? 'Предмет' : 'Скін');
}

const state = {
  game: 'warframe',
  tab: 'catalog',
  token: localStorage.getItem('econ_token') || null,
  user: null,
  gamesMeta: {},
  facets: [],
  rustPickerOpen: false,
  rustPickerCat: 'weapons',
  filters: {
    item_type: '',
    subcategory: '',
    q: '',
    rarity: '',
    sort: 'newest',
    page: 1,
  },
  activeItemId: null,
  activeHistoryStep: 'day',
  chartInstance: null,
};

// ============================================================================
// HTTP & HELPERS
// ============================================================================
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && typeof options.body === 'object') {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || data.title || `HTTP ${resp.status}`);
  return data;
}

let toastTimer = null;
function showToast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = isError ? 'toast error' : 'toast';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3400);
}

function fmtUsd(val) {
  if (val === null || val === undefined || val === '') return '—';
  return `$${Number(val).toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtCompactUsd(val) {
  const n = Number(val || 0);
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)} млн`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)} тис.`;
  return fmtUsd(n);
}

function fmtPct(val) {
  if (val === null || val === undefined) return '<span class="muted">—</span>';
  const n = Number(val);
  const cls = n > 0 ? 'pos' : n < 0 ? 'neg' : 'muted';
  return `<span class="num ${cls}">${n > 0 ? '+' : ''}${n.toFixed(2)}%</span>`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function rarityBadge(code) {
  const label = RARITY_UK[code] || code;
  return `<span class="rarity-pill ${esc(code)}">${esc(label)}</span>`;
}

// ============================================================================
// CUSTOM DARK DROPDOWNS & SEGMENTED TOGGLES (ZERO NATIVE BLUE MENUS)
// ============================================================================
function closeAllCustomSelects(exceptWrap = null) {
  document.querySelectorAll('.csel.open').forEach((w) => {
    if (w !== exceptWrap) w.classList.remove('open');
  });
}

function refreshCustomSelect(selectEl) {
  if (!selectEl) return;
  let wrap = selectEl._cselWrap;
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.className = 'csel';
    selectEl.parentNode.insertBefore(wrap, selectEl);
    wrap.appendChild(selectEl);
    selectEl.classList.add('csel-native');

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'csel-trigger';
    trigger.innerHTML = `
      <span class="csel-label"></span>
      <svg class="csel-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 6l4 4 4-4"/>
      </svg>
    `;
    const menu = document.createElement('div');
    menu.className = 'csel-menu';

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const willOpen = !wrap.classList.contains('open');
      closeAllCustomSelects(wrap);
      wrap.classList.toggle('open', willOpen);
    });

    wrap.appendChild(trigger);
    wrap.appendChild(menu);
    selectEl._cselWrap = wrap;
    selectEl._cselTriggerLabel = trigger.querySelector('.csel-label');
    selectEl._cselMenu = menu;
  }

  const opts = Array.from(selectEl.options);
  const activeOpt = opts.find((o) => o.value === selectEl.value) || opts[0];
  selectEl._cselTriggerLabel.textContent = activeOpt ? activeOpt.textContent : '—';

  const menu = selectEl._cselMenu;
  menu.innerHTML = opts
    .map(
      (o) =>
        `<button type="button" class="csel-option ${o.value === selectEl.value ? 'selected' : ''}" data-opt-val="${esc(o.value)}">${esc(o.textContent)}</button>`
    )
    .join('');

  menu.querySelectorAll('.csel-option').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const val = btn.dataset.optVal;
      const changed = selectEl.value !== val;
      selectEl.value = val;
      wrap.classList.remove('open');
      refreshCustomSelect(selectEl);
      if (changed) {
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });
}

function initCustomSelects() {
  document.querySelectorAll('select.select').forEach((sel) => refreshCustomSelect(sel));
  document.addEventListener('click', () => closeAllCustomSelects());
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAllCustomSelects();
  });
}

function initSegmentedToggles() {
  document.querySelectorAll('.seg-toggle').forEach((group) => {
    const hidden = group.querySelector('input[type="hidden"]');
    const btns = group.querySelectorAll('.seg-btn');
    btns.forEach((btn) => {
      btn.addEventListener('click', () => {
        if (hidden) hidden.value = btn.dataset.val;
        btns.forEach((b) => b.classList.toggle('active', b === btn));
      });
    });
  });
}

function setSegmentedValue(groupId, val) {
  const group = document.getElementById(groupId);
  if (!group) return;
  const hidden = group.querySelector('input[type="hidden"]');
  if (hidden) hidden.value = val;
  group.querySelectorAll('.seg-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.val === val);
  });
}

// ============================================================================
// SCREEN 1: 3D LAYERED PARALLAX SPLASH
// ============================================================================
function initSplash() {
  const splash = document.getElementById('splash-screen');
  splash.querySelectorAll('.splash-pane').forEach((pane) => {
    const game = pane.dataset.game;
    const bgLayer = pane.querySelector('.splash-layer-bg');
    const charLayer = pane.querySelector('.splash-layer-char');

    pane.addEventListener('mouseenter', () => {
      splash.classList.remove('hover-warframe', 'hover-rust');
      splash.classList.add(`hover-${game}`);
    });

    pane.addEventListener('mousemove', (e) => {
      const r = pane.getBoundingClientRect();
      const nx = (e.clientX - r.left) / r.width - 0.5;
      const ny = (e.clientY - r.top) / r.height - 0.5;
      // Background & cutout foreground move in opposite directions -> real 3D parallax
      bgLayer.style.transform = `translate3d(${-nx * 14}px, ${-ny * 9}px, 0)`;
      charLayer.style.transform = `translate3d(${nx * 22}px, ${ny * 12}px, 0)`;
    });

    pane.addEventListener('mouseleave', () => {
      splash.classList.remove('hover-warframe', 'hover-rust');
      bgLayer.style.transform = 'none';
      charLayer.style.transform = 'none';
    });

    pane.addEventListener('click', () => enterGame(game));
  });
}

async function loadGamesMeta() {
  try {
    const games = await api('/api/v1/games');
    games.forEach((g) => {
      state.gamesMeta[g.code] = g;
      const el = document.getElementById(`splash-cap-${g.code}`);
      if (el) {
        el.textContent = `Загальна вартість ринку: ${fmtCompactUsd(g.total_market_value_usd)} · ${g.total_offers.toLocaleString('uk-UA')} пропозицій`;
      }
    });
  } catch (err) {
    console.error(err);
  }
}

function enterGame(gameCode) {
  const splash = document.getElementById('splash-screen');
  const shell = document.getElementById('app-shell');
  splash.classList.add('exiting');
  setTimeout(() => {
    splash.classList.add('hidden');
    shell.classList.remove('hidden');
    selectGame(gameCode);
  }, 300);
}

function returnToSplash() {
  const splash = document.getElementById('splash-screen');
  const shell = document.getElementById('app-shell');
  shell.classList.add('hidden');
  splash.classList.remove('hidden');
  requestAnimationFrame(() => splash.classList.remove('exiting'));
}

// ============================================================================
// GAME THEME & CATALOG VIEW SWITCHER
// ============================================================================
async function selectGame(gameCode) {
  state.game = gameCode;
  state.rustPickerOpen = false;
  document.documentElement.setAttribute('data-theme', gameCode);
  document.querySelectorAll('[data-switch-game]').forEach((b) => {
    b.classList.toggle('active', b.dataset.switchGame === gameCode);
  });

  state.filters = {
    item_type: '',
    subcategory: '',
    q: '',
    rarity: '',
    sort: gameCode === 'rust' ? 'newest' : 'volume_desc',
    page: 1,
  };

  document.getElementById('rust-search-input').value = '';
  document.getElementById('wf-search-input').value = '';
  document.getElementById('rust-rarity-select').value = '';
  document.getElementById('rust-sort-select').value = 'newest';
  document.getElementById('wf-rarity-select').value = '';
  document.getElementById('wf-sort-select').value = 'volume_desc';
  ['rust-rarity-select', 'rust-sort-select', 'wf-rarity-select', 'wf-sort-select'].forEach((id) =>
    refreshCustomSelect(document.getElementById(id))
  );
  updateRustSelectedPill('', '');

  // Show Warframe.market photo hero ONLY on Warframe catalog
  const isWf = gameCode === 'warframe';
  document.getElementById('wf-hero-banner').classList.toggle('hidden', !isWf || state.tab !== 'catalog');
  document.getElementById('wf-catalog-view').classList.toggle('hidden', !isWf);
  document.getElementById('rust-catalog-view').classList.toggle('hidden', isWf);

  const meta = state.gamesMeta[gameCode];
  if (meta && isWf) {
    document.getElementById('wf-stat-items').textContent = `${meta.items_count} предметів`;
    document.getElementById('wf-stat-offers').textContent = `${meta.total_offers.toLocaleString('uk-UA')} ордерів`;
    document.getElementById('wf-stat-cap').textContent = `Ринок: ${fmtCompactUsd(meta.total_market_value_usd)}`;
  } else if (meta && !isWf) {
    document.getElementById('rust-cap-meta').textContent =
      `${meta.items_count} скінів · ${meta.total_offers.toLocaleString('uk-UA')} лотів · Ринок: ${fmtCompactUsd(meta.total_market_value_usd)}`;
  }

  await loadCurrentTab();
}

async function switchTab(tabName) {
  state.tab = tabName;
  document.querySelectorAll('.nav-tab').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('hidden', panel.id !== `tab-${tabName}`);
  });
  document
    .getElementById('wf-hero-banner')
    .classList.toggle('hidden', !(state.game === 'warframe' && tabName === 'catalog'));

  await loadCurrentTab();
}

async function loadCurrentTab() {
  if (state.tab === 'catalog') {
    await loadFacets();
    if (state.game === 'rust') await loadRustCatalog();
    else await loadWarframeCatalog();
  } else if (state.tab === 'stats') {
    await loadAnalytics();
  } else if (state.tab === 'anomalies') {
    await loadAnomalies();
  } else if (state.tab === 'portfolio') {
    await loadPortfolio();
  } else if (state.tab === 'alerts') {
    await loadAlertsAndWatches();
  } else if (state.tab === 'admin') {
    await loadAdminStatus();
  }
}

// ============================================================================
// FACETS & DUAL CATALOGS (RUSTCLASH VS WARFRAME.MARKET)
// ============================================================================
async function loadFacets() {
  state.facets = await api(`/api/v1/categories?game=${encodeURIComponent(state.game)}`);
  if (state.game === 'rust') {
    renderRustPicker();
  } else {
    renderWarframeCategoryTabs();
  }
}

// ---------------- RUSTCLASH CATALOG ----------------
function renderRustPicker() {
  const drawer = document.getElementById('rust-picker-drawer');
  drawer.classList.toggle('hidden', !state.rustPickerOpen);

  const tabsEl = document.getElementById('rust-picker-tabs');
  if (!state.facets.some((f) => f.code === state.rustPickerCat) && state.facets.length) {
    state.rustPickerCat = state.facets[0].code;
  }

  tabsEl.innerHTML = state.facets
    .map(
      (f) => `
      <button class="rust-picker-tab ${f.code === state.rustPickerCat ? 'active' : ''}" data-pick-cat="${esc(f.code)}">
        ${esc(f.label)} (${f.subcategories.length})
      </button>
    `
    )
    .join('');

  tabsEl.querySelectorAll('.rust-picker-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.rustPickerCat = btn.dataset.pickCat;
      renderRustPicker();
    });
  });

  const activeCat = state.facets.find((f) => f.code === state.rustPickerCat);
  const gridEl = document.getElementById('rust-picker-grid');
  if (!activeCat) {
    gridEl.innerHTML = '';
    return;
  }

  gridEl.innerHTML = activeCat.subcategories
    .map(
      (s) => `
      <button class="rust-stock-tile ${state.filters.subcategory === s.code ? 'active' : ''}" data-pick-sub="${esc(s.code)}" data-pick-label="${esc(s.label)}" data-pick-icon="${esc(s.icon_url || '')}">
        <img src="${esc(s.icon_url || '')}" alt="${esc(s.label)}" loading="lazy" referrerpolicy="no-referrer" />
        <span class="rust-stock-name">${esc(s.label)}</span>
        <span class="rust-stock-cnt">${s.items_count} скінів</span>
      </button>
    `
    )
    .join('');

  gridEl.querySelectorAll('.rust-stock-tile').forEach((tile) => {
    tile.addEventListener('click', () => {
      state.filters.item_type = state.rustPickerCat;
      state.filters.subcategory = tile.dataset.pickSub;
      state.filters.page = 1;
      state.rustPickerOpen = false;
      updateRustSelectedPill(tile.dataset.pickLabel, tile.dataset.pickIcon);
      renderRustPicker();
      loadRustCatalog();
    });
  });
}

function updateRustSelectedPill(label, iconUrl) {
  const content = document.getElementById('rust-selected-pill-content');
  const clearBtn = document.getElementById('btn-rust-clear-item');
  if (!label) {
    content.innerHTML = 'Обрати предмет';
    clearBtn.classList.add('hidden');
  } else {
    const imgHtml = iconUrl ? `<img src="${esc(iconUrl)}" alt="" referrerpolicy="no-referrer" /> ` : '';
    content.innerHTML = `${imgHtml}<span>${esc(label)}</span>`;
    clearBtn.classList.remove('hidden');
  }
}

async function loadRustCatalog() {
  const p = new URLSearchParams({
    game: 'rust',
    sort: state.filters.sort,
    page: String(state.filters.page),
    page_size: '24',
  });
  if (state.filters.item_type) p.set('item_type', state.filters.item_type);
  if (state.filters.subcategory) p.set('subcategory', state.filters.subcategory);
  if (state.filters.q) p.set('q', state.filters.q);
  if (state.filters.rarity) p.set('rarity', state.filters.rarity);

  const data = await api(`/api/v1/items?${p.toString()}`);
  const grid = document.getElementById('rust-skins-grid');
  const recentCutoff = Date.now() - 180 * 86400 * 1000;

  if (!data.items.length) {
    grid.innerHTML = `<div class="card muted" style="grid-column:1/-1; padding:32px; text-align:center;">Скіни за вибраними фільтрами не знайдено.</div>`;
  } else {
    grid.innerHTML = data.items
      .map((it) => {
        const isNew = it.released_at && new Date(it.released_at).getTime() > recentCutoff;
        return `
          <article class="rust-skin-card" data-item-id="${it.id}">
            <div class="rust-skin-stage">
              ${isNew ? '<span class="rust-new-tag">НОВИЙ</span>' : ''}
              <img src="${esc(it.icon_url || '')}" alt="${esc(it.name)}" loading="lazy" referrerpolicy="no-referrer" />
            </div>
            <div class="rust-skin-body">
              <div class="rust-skin-title">${esc(it.name)}</div>
              <div class="rust-skin-sub">${esc(formatSubcategoryLabel(it.subcategory, 'rust'))} · ${esc(RARITY_UK[it.rarity] || it.rarity)}</div>
              <div class="rust-skin-footer">
                <span class="rust-skin-price num">${fmtUsd(it.latest_min_price)}</span>
                <span class="rust-skin-vol num">${it.latest_total_volume} лотів · ${it.spread_pct !== null ? `+${Number(it.spread_pct).toFixed(0)}%` : ''}</span>
              </div>
            </div>
          </article>
        `;
      })
      .join('');

    grid.querySelectorAll('.rust-skin-card').forEach((card) => {
      card.addEventListener('click', () => openItemModal(Number(card.dataset.itemId)));
    });
  }

  document.getElementById('rust-pagination-info').textContent = `Усього скінів: ${data.total}`;
  document.getElementById('rust-pagination-page').textContent = `${data.page} / ${data.pages}`;
  document.getElementById('rust-prev-page').disabled = data.page <= 1;
  document.getElementById('rust-next-page').disabled = data.page >= data.pages;
}

// ---------------- WARFRAME.MARKET CATALOG ----------------
function renderWarframeCategoryTabs() {
  const tabsEl = document.getElementById('wf-cat-tabs');
  const allBtn = `<button class="wf-cat-tab ${state.filters.item_type === '' ? 'active' : ''}" data-wf-cat="">Усі</button>`;
  const catBtns = state.facets
    .map(
      (f) =>
        `<button class="wf-cat-tab ${state.filters.item_type === f.code ? 'active' : ''}" data-wf-cat="${esc(f.code)}">${esc(f.label)} (${f.items_count})</button>`
    )
    .join('');
  tabsEl.innerHTML = allBtn + catBtns;

  tabsEl.querySelectorAll('.wf-cat-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.filters.item_type = btn.dataset.wfCat;
      state.filters.subcategory = '';
      state.filters.page = 1;
      renderWarframeCategoryTabs();
      loadWarframeCatalog();
    });
  });

  // Update subcategory dropdown for selected category
  const subSel = document.getElementById('wf-subcat-select');
  const activeCat = state.facets.find((f) => f.code === state.filters.item_type);
  const subs = activeCat ? activeCat.subcategories : [];
  subSel.innerHTML =
    `<option value="">Усі підтипи</option>` +
    subs.map((s) => `<option value="${esc(s.code)}">${esc(s.label)} (${s.items_count})</option>`).join('');
  subSel.value = state.filters.subcategory;
  refreshCustomSelect(subSel);
}

async function loadWarframeCatalog() {
  const p = new URLSearchParams({
    game: 'warframe',
    sort: state.filters.sort,
    page: String(state.filters.page),
    page_size: '24',
  });
  if (state.filters.item_type) p.set('item_type', state.filters.item_type);
  if (state.filters.subcategory) p.set('subcategory', state.filters.subcategory);
  if (state.filters.q) p.set('q', state.filters.q);
  if (state.filters.rarity) p.set('rarity', state.filters.rarity);

  const data = await api(`/api/v1/items?${p.toString()}`);
  const grid = document.getElementById('wf-orders-grid');

  if (!data.items.length) {
    grid.innerHTML = `<div class="card muted" style="grid-column:1/-1; padding:32px; text-align:center;">Предметів не знайдено.</div>`;
  } else {
    grid.innerHTML = data.items
      .map((it) => {
        const plt = Math.max(1, Math.round(Number(it.latest_min_price || 0) / PLT_USD_RATE));
        const subLabel = formatSubcategoryLabel(it.subcategory, 'warframe');
        return `
          <article class="wf-item-card" data-item-id="${it.id}">
            <div class="wf-card-left">
              <div class="wf-icon-frame">
                <img src="${esc(it.icon_url || '')}" alt="${esc(it.name)}" loading="lazy" referrerpolicy="no-referrer" />
              </div>
              <div style="min-width:0;">
                <div class="wf-title-uk">${esc(it.name)}</div>
                <div class="wf-title-en">${esc(it.name_en || '')}</div>
                <div class="wf-tags-row">
                  ${rarityBadge(it.rarity)}
                  <span class="wf-subcat-pill">${esc(subLabel)}</span>
                  <span class="muted" style="font-size:11.5px;">${fmtPct(it.price_change_24h_pct)}</span>
                </div>
              </div>
            </div>
            <div class="wf-card-right">
              <div class="wf-plat-price">${plt} Платини</div>
              <div class="wf-usd-sub">${fmtUsd(it.latest_min_price)} · спред +${Number(it.spread_pct || 0).toFixed(1)}%</div>
              <div class="wf-vol-sub">${it.latest_total_volume} активних ордерів</div>
            </div>
          </article>
        `;
      })
      .join('');

    grid.querySelectorAll('.wf-item-card').forEach((card) => {
      card.addEventListener('click', () => openItemModal(Number(card.dataset.itemId)));
    });
  }

  document.getElementById('wf-pagination-info').textContent = `Усього предметів: ${data.total}`;
  document.getElementById('wf-pagination-page').textContent = `${data.page} / ${data.pages}`;
  document.getElementById('wf-prev-page').disabled = data.page <= 1;
  document.getElementById('wf-next-page').disabled = data.page >= data.pages;
}

// ============================================================================
// ITEM DETAIL MODAL
// ============================================================================
async function openItemModal(itemId) {
  state.activeItemId = itemId;
  state.activeHistoryStep = 'day';
  const modal = document.getElementById('item-modal');
  const modalPanel = modal.querySelector('.modal-panel');
  modal.classList.remove('hidden');
  if (modalPanel) modalPanel.scrollTop = 0;

  const detail = await api(`/api/v1/items/${itemId}`);
  if (modalPanel) modalPanel.scrollTop = 0;

  document.getElementById('modal-item-title').textContent = detail.name;
  document.getElementById('modal-item-subtitle').textContent =
    detail.name_en && detail.name_en !== detail.name
      ? `${detail.name_en} · ${detail.game_code.toUpperCase()}`
      : detail.game_code.toUpperCase();

  document.getElementById('modal-item-image').src = detail.icon_url || '';
  document.getElementById('modal-item-image').alt = detail.name;

  const descEl = document.getElementById('modal-item-desc');
  if (detail.description) {
    descEl.textContent = detail.description;
    descEl.classList.remove('hidden');
  } else {
    descEl.classList.add('hidden');
  }

  document.getElementById('modal-spread-badge').textContent =
    detail.spread_abs !== null
      ? `Спред: ${fmtUsd(detail.spread_abs)} (+${Number(detail.spread_pct || 0).toFixed(1)}%)`
      : '';

  document.getElementById('modal-markets-tbody').innerHTML = detail.markets
    .map(
      (m) => `
      <tr>
        <td><strong>${esc(m.market_name)}</strong></td>
        <td class="num">${Number(m.original_price).toFixed(m.original_currency === 'PLT' ? 0 : 2)} ${esc(m.original_currency)}</td>
        <td class="num">${fmtUsd(m.normalized_price)}</td>
        <td class="num">${m.volume}</td>
      </tr>
    `
    )
    .join('');

  const released = detail.released_at
    ? new Date(detail.released_at).toLocaleDateString('uk-UA')
    : 'Невідомо';
  const subLabelTitle = detail.game_code === 'warframe' ? 'Тип предмета' : 'Базовий предмет';
  document.getElementById('modal-meta-tbody').innerHTML = `
    <tr><td>Категорія</td><td>${esc(formatCategoryLabel(detail.item_type))}</td></tr>
    <tr><td>${subLabelTitle}</td><td>${esc(formatSubcategoryLabel(detail.subcategory, detail.game_code))}</td></tr>
    <tr><td>Рідкість</td><td>${rarityBadge(detail.rarity)}</td></tr>
    <tr><td>Дата появи</td><td class="num">${released}</td></tr>
    <tr><td>Пропозицій на ринку</td><td class="num">${detail.latest_total_volume}</td></tr>
    <tr><td>7-денне середнє (MA-7)</td><td class="num">${fmtUsd(detail.ma7_price)}</td></tr>
  `;

  // Related Prime Set Parts quick switcher
  const relWrap = document.getElementById('modal-related-wrap');
  const relList = document.getElementById('modal-related-list');
  if (detail.related_parts && detail.related_parts.length > 0) {
    relWrap.classList.remove('hidden');
    relList.innerHTML = detail.related_parts
      .map((p) => {
        const plt = Math.max(1, Math.round(Number(p.latest_min_price || 0) / PLT_USD_RATE));
        return `
          <button type="button" class="related-part-chip" data-rel-item="${p.id}">
            <div class="related-part-icon">
              <img src="${esc(p.icon_url || '')}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer" />
            </div>
            <div class="related-part-info">
              <div class="related-part-name">${esc(p.name)}</div>
              <div class="related-part-price">${plt} PLT · ${fmtUsd(p.latest_min_price)}</div>
            </div>
          </button>
        `;
      })
      .join('');
    relList.querySelectorAll('[data-rel-item]').forEach((btn) => {
      btn.addEventListener('click', () => openItemModal(Number(btn.dataset.relItem)));
    });
  } else {
    relWrap.classList.add('hidden');
    relList.innerHTML = '';
  }

  const actionsWrap = document.getElementById('modal-user-actions');
  if (state.user && detail.markets.length) {
    actionsWrap.classList.remove('hidden');
    const opts = detail.markets.map((m) => `<option value="${m.market_id}">${esc(m.market_name)}</option>`).join('');
    const watchSel = document.getElementById('watch-market-select');
    const tradeSel = document.getElementById('trade-market-select');
    watchSel.innerHTML = opts;
    tradeSel.innerHTML = opts;
    refreshCustomSelect(watchSel);
    refreshCustomSelect(tradeSel);
    setSegmentedValue('watch-dir-toggle', 'below');
    setSegmentedValue('trade-side-toggle', 'buy');
    const basePrice = Number(detail.cheapest_price || 1).toFixed(2);
    document.getElementById('watch-threshold-input').value = basePrice;
    document.getElementById('watch-cooldown-input').value = '60';
    document.getElementById('trade-price-input').value = basePrice;
  } else {
    actionsWrap.classList.add('hidden');
  }

  document.querySelectorAll('#history-step-switch button').forEach((b) => {
    b.classList.toggle('active', b.dataset.step === 'day');
  });
  await loadItemHistory(itemId, 'day', detail.ma7_price);
  if (modalPanel) modalPanel.scrollTop = 0;
}

async function loadItemHistory(itemId, step, ma7Price) {
  state.activeHistoryStep = step;
  document.getElementById('btn-export-csv').href = `/api/v1/items/${itemId}/prices?step=${step}&format=csv`;
  const hist = await api(`/api/v1/items/${itemId}/prices?step=${step}`);

  document.getElementById('modal-history-tbody').innerHTML = hist.points
    .slice()
    .reverse()
    .map(
      (p) => `
      <tr>
        <td class="num">${new Date(p.bucket).toLocaleString('uk-UA')}</td>
        <td class="num">${fmtUsd(p.min_price)}</td>
        <td class="num">${fmtUsd(p.max_price)}</td>
        <td class="num">${fmtUsd(p.avg_price)}</td>
        <td class="num">${fmtUsd(p.median_price)}</td>
        <td class="num">${p.avg_volume}</td>
      </tr>
    `
    )
    .join('');

  renderPriceChart(hist.points, ma7Price);
}

function renderPriceChart(points, ma7Price) {
  const ctx = document.getElementById('price-chart');
  if (state.chartInstance) state.chartInstance.destroy();
  if (typeof window.Chart === 'undefined') return;

  const isRust = state.game === 'rust';
  const lineColor = isRust ? '#cd412b' : '#3f8ea3';
  const fillColor = isRust ? 'rgba(205, 65, 43, 0.14)' : 'rgba(63, 142, 163, 0.14)';
  const barColor = isRust ? 'rgba(217, 119, 6, 0.25)' : 'rgba(201, 169, 97, 0.25)';

  const labels = points.map((p) => {
    const d = new Date(p.bucket);
    return state.activeHistoryStep === 'hour'
      ? d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit' });
  });

  const datasets = [
    {
      type: 'line',
      label: 'Середня ціна (USD)',
      data: points.map((p) => Number(p.avg_price)),
      borderColor: lineColor,
      backgroundColor: fillColor,
      borderWidth: 2,
      tension: 0.25,
      fill: true,
      yAxisID: 'y',
    },
    {
      type: 'bar',
      label: 'Обсяг лотів',
      data: points.map((p) => p.avg_volume),
      backgroundColor: barColor,
      yAxisID: 'y1',
    },
  ];

  if (ma7Price !== null && ma7Price !== undefined && points.length) {
    datasets.push({
      type: 'line',
      label: 'Ковзне середнє (MA-7)',
      data: points.map(() => Number(ma7Price)),
      borderColor: '#93a6b0',
      borderDash: [5, 5],
      borderWidth: 1.5,
      pointRadius: 0,
      yAxisID: 'y',
    });
  }

  state.chartInstance = new window.Chart(ctx, {
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#cbd5e1', font: { size: 12 } } } },
      scales: {
        x: { ticks: { color: '#93a6b0' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { position: 'left', ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y1: { position: 'right', ticks: { color: '#667983' }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

// ============================================================================
// OTHER TABS (100% UKRAINIAN)
// ============================================================================
async function loadAnalytics() {
  const [overview, spreads] = await Promise.all([
    api(`/api/v1/stats/overview?game=${encodeURIComponent(state.game)}`),
    api(`/api/v1/stats/spread?game=${encodeURIComponent(state.game)}&limit=12`),
  ]);

  const idx = overview.game_indices[0];
  document.getElementById('stats-kpis').innerHTML = `
    <div class="kpi-card"><div class="kpi-lbl">Предметів у каталозі</div><div class="kpi-val">${overview.total_items}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Знімків історії цін</div><div class="kpi-val">${overview.total_snapshots.toLocaleString('uk-UA')}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Індекс гри (24 год)</div><div class="kpi-val">${idx ? fmtPct(idx.avg_change_24h_pct) : '—'}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Індекс гри (7 діб)</div><div class="kpi-val">${idx ? fmtPct(idx.avg_change_7d_pct) : '—'}</div></div>
  `;

  document.getElementById('stats-spread-tbody').innerHTML = spreads
    .map(
      (s) => `
      <tr class="clickable" data-open-item="${s.item_id}">
        <td><strong>${esc(s.name)}</strong></td>
        <td class="num">${fmtUsd(s.min_price)} <span class="muted">(${esc(s.cheapest_market)})</span></td>
        <td class="num">${fmtUsd(s.max_price)} <span class="muted">(${esc(s.priciest_market)})</span></td>
        <td class="num pos">+${fmtUsd(s.spread_abs)}</td>
        <td class="num pos"><strong>+${Number(s.spread_pct).toFixed(1)}%</strong></td>
      </tr>
    `
    )
    .join('');

  const renderMovers = (rows) =>
    rows
      .map(
        (m) => `
        <tr class="clickable" data-open-item="${m.item_id}">
          <td>${esc(m.name)}</td>
          <td class="num">${fmtUsd(m.current_price)}</td>
          <td>${fmtPct(m.change_pct)}</td>
        </tr>
      `
      )
      .join('');

  document.getElementById('stats-gainers-tbody').innerHTML = renderMovers(overview.top_gainers_24h);
  document.getElementById('stats-losers-tbody').innerHTML = renderMovers(overview.top_losers_24h);

  document.getElementById('stats-rarity-tbody').innerHTML = overview.rarity_stats
    .map(
      (r) => `
      <tr>
        <td>${rarityBadge(r.rarity)}</td>
        <td class="num">${r.items_count}</td>
        <td class="num">${fmtUsd(r.avg_price)}</td>
        <td class="num">${r.total_volume.toLocaleString('uk-UA')}</td>
      </tr>
    `
    )
    .join('');

  document.querySelectorAll('#tab-stats [data-open-item]').forEach((row) => {
    row.addEventListener('click', () => openItemModal(Number(row.dataset.openItem)));
  });
}

async function loadPortfolio() {
  if (!state.user) return;
  const [port, trades] = await Promise.all([api('/api/v1/portfolio'), api('/api/v1/trades')]);
  const pnlFmt = (v) => {
    const n = Number(v);
    return `<span class="${n >= 0 ? 'pos' : 'neg'}">${n >= 0 ? '+' : ''}${fmtUsd(n)}</span>`;
  };

  document.getElementById('portfolio-kpis').innerHTML = `
    <div class="kpi-card"><div class="kpi-lbl">Вкладено</div><div class="kpi-val">${fmtUsd(port.invested)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Поточна оцінка</div><div class="kpi-val">${fmtUsd(port.current_value)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Реалізований результат</div><div class="kpi-val">${pnlFmt(port.realized_pnl)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Нереалізований результат</div><div class="kpi-val">${pnlFmt(port.unrealized_pnl)}</div></div>
  `;

  document.getElementById('portfolio-positions-tbody').innerHTML = port.positions.length
    ? port.positions
        .map(
          (p) => `
          <tr>
            <td><strong>${esc(p.item_name)}</strong> <span class="muted">${esc(p.game_code)}</span></td>
            <td class="num">${p.quantity}</td>
            <td class="num">${fmtUsd(p.avg_cost)}</td>
            <td class="num">${fmtUsd(p.current_price)}</td>
            <td class="num">${fmtUsd(p.invested)}</td>
            <td class="num">${pnlFmt(p.realized_pnl)}</td>
            <td class="num">${pnlFmt(p.unrealized_pnl)}</td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="7" class="muted" style="text-align:center; padding:24px;">Позицій поки немає — відкрийте будь-який предмет і зафіксуйте угоду.</td></tr>`;

  document.getElementById('portfolio-trades-tbody').innerHTML = trades
    .map(
      (t) => `
      <tr>
        <td class="num">${new Date(t.traded_at).toLocaleString('uk-UA')}</td>
        <td>${esc(t.item_name)}</td>
        <td class="muted">${esc(t.market_name)}</td>
        <td><span class="rarity-pill ${t.side === 'buy' ? 'uncommon' : 'legendary'}">${t.side === 'buy' ? 'КУПІВЛЯ' : 'ПРОДАЖ'}</span></td>
        <td class="num">${t.quantity}</td>
        <td class="num">${fmtUsd(t.price)}</td>
        <td><button class="btn btn-sm btn-danger" data-del-trade="${t.id}">Видалити</button></td>
      </tr>
    `
    )
    .join('');

  document.querySelectorAll('[data-del-trade]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/api/v1/trades/${btn.dataset.delTrade}`, { method: 'DELETE' });
        showToast('Угоду видалено, позицію перераховано від початку історії');
        await loadPortfolio();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });
}

async function loadAlertsAndWatches() {
  if (!state.user) return;
  const unreadOnly = document.getElementById('alerts-unread-only').checked;
  const [watches, alerts] = await Promise.all([
    api('/api/v1/watch'),
    api(`/api/v1/alerts?unread=${unreadOnly}`),
  ]);

  document.getElementById('watch-tbody').innerHTML = watches.length
    ? watches
        .map(
          (w) => `
          <tr>
            <td><strong>${esc(w.item_name)}</strong></td>
            <td class="muted">${esc(w.market_name)}</td>
            <td class="num">${w.direction === 'below' ? '≤' : '≥'} ${fmtUsd(w.threshold)}</td>
            <td class="num muted">${w.cooldown_minutes} хв</td>
            <td><button class="btn btn-sm btn-danger" data-del-watch="${w.id}">×</button></td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="5" class="muted" style="text-align:center; padding:20px;">Немає активних спостережень.</td></tr>`;

  document.getElementById('alerts-tbody').innerHTML = alerts.length
    ? alerts
        .map(
          (a) => `
          <tr>
            <td style="${a.is_read ? 'opacity:0.6;' : 'font-weight:500;'}">${esc(a.message)}</td>
            <td class="num muted">${new Date(a.created_at).toLocaleString('uk-UA')}</td>
            <td>${a.is_read ? '<span class="muted">Прочитано</span>' : `<button class="btn btn-sm" data-read-alert="${a.id}">Прочитано</button>`}</td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="3" class="muted" style="text-align:center; padding:20px;">Сповіщень немає.</td></tr>`;

  document.querySelectorAll('[data-del-watch]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await api(`/api/v1/watch/${btn.dataset.delWatch}`, { method: 'DELETE' });
      showToast('Спостереження видалено');
      await loadAlertsAndWatches();
    });
  });

  document.querySelectorAll('[data-read-alert]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await api(`/api/v1/alerts/${btn.dataset.readAlert}/read`, { method: 'POST' });
      await refreshUnreadBadge();
      await loadAlertsAndWatches();
    });
  });
}

async function refreshUnreadBadge() {
  const badge = document.getElementById('unread-badge');
  if (!state.user) {
    badge.classList.add('hidden');
    return;
  }
  try {
    const unread = await api('/api/v1/alerts?unread=true');
    if (unread.length > 0) {
      badge.textContent = String(unread.length);
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  } catch {
    badge.classList.add('hidden');
  }
}

async function loadAnomalies() {
  const statusVal = document.getElementById('anomaly-status-filter').value;
  const qs = new URLSearchParams({ game: state.game });
  if (statusVal) qs.set('status', statusVal);
  const rows = await api(`/api/v1/anomalies?${qs.toString()}`);

  const canClose = state.user && (state.user.role === 'analyst' || state.user.role === 'admin');
  document.getElementById('anomalies-tbody').innerHTML = rows.length
    ? rows
        .map(
          (a) => `
          <tr class="clickable" data-open-item="${a.item_id}">
            <td><strong>${esc(a.item_name)}</strong></td>
            <td class="muted">${esc(a.market_name)}</td>
            <td class="num">${fmtUsd(a.ma7_price)} → ${fmtUsd(a.trigger_price)}</td>
            <td>${fmtPct(a.max_deviation_pct)}</td>
            <td class="num muted">${a.duration_minutes} хв</td>
            <td>
              <span class="rarity-pill ${a.status === 'open' ? 'legendary' : 'uncommon'}">${a.status === 'open' ? 'ВІДКРИТА' : 'ЗАКРИТА'}</span>
              ${a.comment ? `<div class="muted" style="font-size:12px; margin-top:4px;">${esc(a.comment)}</div>` : ''}
            </td>
            <td>
              ${
                a.status === 'open' && canClose
                  ? `<button class="btn btn-sm btn-primary" data-close-anom="${a.id}">Закрити</button>`
                  : ''
              }
            </td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="7" class="muted" style="text-align:center; padding:24px;">Подій не знайдено.</td></tr>`;

  document.querySelectorAll('#anomalies-tbody tr[data-open-item]').forEach((row) => {
    row.addEventListener('click', () => openItemModal(Number(row.dataset.openItem)));
  });

  document.querySelectorAll('[data-close-anom]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const comment = window.prompt('Коментар аналітика щодо закриття аномалії:', 'Підтверджено: ринкове коливання стабілізувалось');
      if (!comment || comment.trim().length < 3) return;
      try {
        await api(`/api/v1/anomalies/${btn.dataset.closeAnom}/close`, {
          method: 'POST',
          body: { comment: comment.trim() },
        });
        showToast('Аномалію закрито');
        await loadAnomalies();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });
}

async function loadAdminStatus() {
  if (!state.user || (state.user.role !== 'admin' && state.user.role !== 'analyst')) return;
  const rows = await api('/api/v1/admin/collection/status');
  const isAdmin = state.user.role === 'admin';
  document.getElementById('admin-status-tbody').innerHTML = rows
    .map(
      (r) => `
      <tr>
        <td><strong>${esc(r.market_name)}</strong></td>
        <td>${esc(r.game_code)}</td>
        <td class="num">${esc(r.currency)}</td>
        <td class="num">${r.schedule_minutes} хв</td>
        <td class="num muted">${r.last_run_at ? new Date(r.last_run_at).toLocaleString('uk-UA') : '—'}</td>
        <td class="num">${r.accepted_count} / <span class="${r.rejected_count > 0 ? 'neg' : 'muted'}">${r.rejected_count}</span></td>
        <td>
          <span class="rarity-pill ${r.last_status === 'failed' ? 'legendary' : 'uncommon'}">${esc(r.last_status || 'очікує')}</span>
          ${r.last_error ? `<div class="neg" style="font-size:12px; margin-top:4px;">${esc(r.last_error)}</div>` : ''}
        </td>
        <td>${isAdmin ? `<button class="btn btn-sm" data-run-market="${r.market_id}">Зібрати</button>` : ''}</td>
      </tr>
    `
    )
    .join('');

  document.querySelectorAll('[data-run-market]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await api('/api/v1/collect/run', {
          method: 'POST',
          body: { market_id: Number(btn.dataset.runMarket) },
        });
        showToast('Збір завершено');
        await loadAdminStatus();
      } catch (err) {
        showToast(err.message, true);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

// ============================================================================
// AUTH FLOW
// ============================================================================
async function syncUser() {
  const pill = document.getElementById('user-pill');
  const btnAuth = document.getElementById('btn-auth');
  const btnLogout = document.getElementById('btn-logout');
  const portTab = document.getElementById('nav-tab-portfolio');
  const alertTab = document.getElementById('nav-tab-alerts');
  const adminTab = document.getElementById('nav-tab-admin');

  if (!state.token) {
    state.user = null;
  } else {
    try {
      state.user = await api('/api/v1/auth/me');
    } catch {
      state.token = null;
      state.user = null;
      localStorage.removeItem('econ_token');
    }
  }

  if (state.user) {
    pill.textContent = `${state.user.username} (${ROLE_UK[state.user.role] || state.user.role})`;
    pill.classList.remove('hidden');
    btnAuth.classList.add('hidden');
    btnLogout.classList.remove('hidden');
    portTab.classList.remove('hidden');
    alertTab.classList.remove('hidden');
    adminTab.classList.toggle('hidden', state.user.role !== 'admin' && state.user.role !== 'analyst');
    await refreshUnreadBadge();
  } else {
    pill.classList.add('hidden');
    btnAuth.classList.remove('hidden');
    btnLogout.classList.add('hidden');
    portTab.classList.add('hidden');
    alertTab.classList.add('hidden');
    adminTab.classList.add('hidden');
    if (state.tab === 'portfolio' || state.tab === 'alerts' || state.tab === 'admin') {
      await switchTab('catalog');
    }
  }
}

async function performAuth(endpoint, username, password) {
  try {
    const res = await api(endpoint, { method: 'POST', body: { username, password } });
    state.token = res.access_token;
    localStorage.setItem('econ_token', res.access_token);
    document.getElementById('auth-modal').classList.add('hidden');
    await syncUser();
    showToast(`Вхід виконано: ${res.user.username} (${ROLE_UK[res.user.role] || res.user.role})`);
    await loadCurrentTab();
  } catch (err) {
    showToast(err.message, true);
  }
}

// ============================================================================
// WIRE EVENTS
// ============================================================================
function wireEvents() {
  document.getElementById('btn-back-splash').addEventListener('click', returnToSplash);
  document.querySelectorAll('[data-switch-game]').forEach((b) => {
    b.addEventListener('click', () => selectGame(b.dataset.switchGame));
  });
  document.querySelectorAll('.nav-tab').forEach((b) => {
    b.addEventListener('click', () => switchTab(b.dataset.tab));
  });

  // Rust catalog controls
  document.getElementById('btn-rust-select-item').addEventListener('click', () => {
    state.rustPickerOpen = !state.rustPickerOpen;
    renderRustPicker();
  });
  document.getElementById('btn-rust-clear-item').addEventListener('click', () => {
    state.filters.item_type = '';
    state.filters.subcategory = '';
    state.filters.page = 1;
    state.rustPickerOpen = false;
    updateRustSelectedPill('', '');
    renderRustPicker();
    loadRustCatalog();
  });

  let rustTimer = null;
  document.getElementById('rust-search-input').addEventListener('input', (e) => {
    state.filters.q = e.target.value;
    state.filters.page = 1;
    clearTimeout(rustTimer);
    rustTimer = setTimeout(loadRustCatalog, 220);
  });
  document.getElementById('rust-rarity-select').addEventListener('change', (e) => {
    state.filters.rarity = e.target.value;
    state.filters.page = 1;
    loadRustCatalog();
  });
  document.getElementById('rust-sort-select').addEventListener('change', (e) => {
    state.filters.sort = e.target.value;
    state.filters.page = 1;
    loadRustCatalog();
  });
  document.getElementById('rust-prev-page').addEventListener('click', () => {
    if (state.filters.page > 1) {
      state.filters.page -= 1;
      loadRustCatalog();
    }
  });
  document.getElementById('rust-next-page').addEventListener('click', () => {
    state.filters.page += 1;
    loadRustCatalog();
  });

  // Warframe catalog controls
  let wfTimer = null;
  document.getElementById('wf-search-input').addEventListener('input', (e) => {
    state.filters.q = e.target.value;
    state.filters.page = 1;
    clearTimeout(wfTimer);
    wfTimer = setTimeout(loadWarframeCatalog, 220);
  });
  document.getElementById('wf-search-btn').addEventListener('click', () => {
    state.filters.q = document.getElementById('wf-search-input').value;
    state.filters.page = 1;
    loadWarframeCatalog();
  });
  document.getElementById('wf-subcat-select').addEventListener('change', (e) => {
    state.filters.subcategory = e.target.value;
    state.filters.page = 1;
    loadWarframeCatalog();
  });
  document.getElementById('wf-rarity-select').addEventListener('change', (e) => {
    state.filters.rarity = e.target.value;
    state.filters.page = 1;
    loadWarframeCatalog();
  });
  document.getElementById('wf-sort-select').addEventListener('change', (e) => {
    state.filters.sort = e.target.value;
    state.filters.page = 1;
    loadWarframeCatalog();
  });
  document.getElementById('wf-prev-page').addEventListener('click', () => {
    if (state.filters.page > 1) {
      state.filters.page -= 1;
      loadWarframeCatalog();
    }
  });
  document.getElementById('wf-next-page').addEventListener('click', () => {
    state.filters.page += 1;
    loadWarframeCatalog();
  });

  // Item modal
  document.getElementById('btn-close-item-modal').addEventListener('click', () => {
    document.getElementById('item-modal').classList.add('hidden');
  });
  document.getElementById('item-modal').addEventListener('click', (e) => {
    if (e.target.id === 'item-modal') e.target.classList.add('hidden');
  });
  document.querySelectorAll('#history-step-switch button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#history-step-switch button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      if (state.activeItemId) loadItemHistory(state.activeItemId, btn.dataset.step, null);
    });
  });

  document.getElementById('form-quick-watch').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/v1/watch', {
        method: 'POST',
        body: {
          item_id: state.activeItemId,
          market_id: Number(document.getElementById('watch-market-select').value),
          direction: document.getElementById('watch-dir-value').value,
          threshold: document.getElementById('watch-threshold-input').value,
          cooldown_minutes: Number(document.getElementById('watch-cooldown-input').value || 60),
        },
      });
      showToast('Спостереження створено');
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById('form-quick-trade').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/v1/trades', {
        method: 'POST',
        body: {
          item_id: state.activeItemId,
          market_id: Number(document.getElementById('trade-market-select').value),
          side: document.getElementById('trade-side-value').value,
          qty: Number(document.getElementById('trade-qty-input').value),
          price: document.getElementById('trade-price-input').value,
          traded_at: new Date().toISOString(),
        },
      });
      showToast('Угоду збережено у портфелі');
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById('alerts-unread-only').addEventListener('change', loadAlertsAndWatches);
  document.getElementById('anomaly-status-filter').addEventListener('change', loadAnomalies);
  document.getElementById('btn-collect-all').addEventListener('click', async () => {
    const btn = document.getElementById('btn-collect-all');
    btn.disabled = true;
    btn.textContent = 'Триває збір...';
    try {
      await api('/api/v1/collect/run', { method: 'POST', body: {} });
      showToast('Паралельний збір з усіх майданчиків завершено');
      await loadAdminStatus();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Запустити збір з усіх майданчиків';
    }
  });

  // Auth modal
  document.getElementById('btn-auth').addEventListener('click', () => {
    document.getElementById('auth-modal').classList.remove('hidden');
  });
  document.getElementById('btn-close-auth-modal').addEventListener('click', () => {
    document.getElementById('auth-modal').classList.add('hidden');
  });
  document.getElementById('btn-logout').addEventListener('click', async () => {
    state.token = null;
    localStorage.removeItem('econ_token');
    await syncUser();
    showToast('Ви вийшли з облікового запису');
    await loadCurrentTab();
  });

  document.getElementById('form-auth').addEventListener('submit', (e) => {
    e.preventDefault();
    performAuth(
      '/api/v1/auth/login',
      document.getElementById('auth-username').value.trim(),
      document.getElementById('auth-password').value
    );
  });
  document.getElementById('btn-do-register').addEventListener('click', () => {
    performAuth(
      '/api/v1/auth/register',
      document.getElementById('auth-username').value.trim(),
      document.getElementById('auth-password').value
    );
  });
  document.querySelectorAll('[data-demo-login]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const [u, p] = btn.dataset.demoLogin.split(':');
      performAuth('/api/v1/auth/login', u, p);
    });
  });
}

async function boot() {
  initSplash();
  initCustomSelects();
  initSegmentedToggles();
  wireEvents();
  await Promise.all([loadGamesMeta(), syncUser()]);
}

boot();
