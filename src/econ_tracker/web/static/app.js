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
  displayCurrency: localStorage.getItem('econ_cur') || 'USD',
  fx: { usd_to_uah: 41.5, eur_to_usd: 1.08, plt_to_usd: 0.04999, source: 'fallback' },
  lastDetail: null,
  lastHistoryPoints: [],
  alertsGameFilter: '',
  sugItems: [],
  sugIndex: -1,
};

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

function toDisplayNum(usdVal) {
  if (usdVal === null || usdVal === undefined || usdVal === '') return 0;
  const n = Number(usdVal);
  return state.displayCurrency === 'UAH' ? n * Number(state.fx.usd_to_uah || 41.5) : n;
}

function fmtUsd(val) {
  if (val === null || val === undefined || val === '') return '—';
  return `$${Number(val).toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDisplayMoney(usdVal) {
  if (usdVal === null || usdVal === undefined || usdVal === '') return '—';
  const converted = toDisplayNum(usdVal);
  const symbol = state.displayCurrency === 'UAH' ? '₴' : '$';
  return `${symbol}${converted.toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function isWfHalfBodyPortrait(item) {
  if (!item || item.game_code !== 'warframe') return false;
  const url = String(item.icon_url || '');
  if (!url || url.includes('sub_icons/')) return false;
  return item.item_type === 'warframes' || item.item_type === 'companions';
}

function formatDescHtml(rawText) {
  const escaped = esc(rawText);
  return escaped.replace(/([+-]?\d+(?:[.,]\d+)?\s*%?)/g, '<span class="stat-val">$1</span>');
}

function highlightMatch(text, query) {
  const raw = String(text || '');
  const q = String(query || '').trim();
  if (!q) return esc(raw);
  const idx = raw.toLowerCase().indexOf(q.toLowerCase());
  if (idx < 0) return esc(raw);
  return (
    esc(raw.slice(0, idx)) +
    `<mark class="wf-hl">${esc(raw.slice(idx, idx + q.length))}</mark>` +
    esc(raw.slice(idx + q.length))
  );
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

async function loadFacets() {
  state.facets = await api(`/api/v1/categories?game=${encodeURIComponent(state.game)}`);
  if (state.game === 'rust') {
    renderRustPicker();
  } else {
    renderWarframeCategoryTabs();
  }
}

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
        const imgCls = isWfHalfBodyPortrait({ ...it, game_code: 'warframe' }) ? 'wf-portrait-fade' : '';
        return `
          <article class="wf-item-card" data-item-id="${it.id}">
            <div class="wf-card-left">
              <div class="wf-icon-frame">
                <img class="${imgCls}" src="${esc(it.icon_url || '')}" alt="${esc(it.name)}" loading="lazy" referrerpolicy="no-referrer" />
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
              <div class="wf-usd-sub">${fmtDisplayMoney(it.latest_min_price)} · спред +${Number(it.spread_pct || 0).toFixed(1)}%</div>
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

function renderModalCurrencySection() {
  const detail = state.lastDetail;
  if (!detail) return;

  document.querySelectorAll('#modal-currency-switch .col-cur-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.cur === state.displayCurrency);
  });

  document.getElementById('modal-spread-badge').textContent =
    detail.spread_abs !== null
      ? `Спред: ${fmtDisplayMoney(detail.spread_abs)} (+${Number(detail.spread_pct || 0).toFixed(1)}%)`
      : '';

  document.getElementById('modal-markets-tbody').innerHTML = detail.markets
    .map(
      (m) => `
      <tr>
        <td><strong>${esc(m.market_name)}</strong></td>
        <td class="num">${Number(m.original_price).toFixed(m.original_currency === 'PLT' ? 0 : 2)} ${esc(m.original_currency)}</td>
        <td class="num">${fmtDisplayMoney(m.normalized_price)}</td>
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
    <tr><td>7-денне середнє (MA-7)</td><td class="num">${fmtDisplayMoney(detail.ma7_price)}</td></tr>
  `;

  if (state.lastHistoryPoints.length) {
    renderPriceChart(state.lastHistoryPoints, detail.ma7_price);
    renderHistoryRows(state.lastHistoryPoints);
  }
}

function renderHistoryRows(points) {
  document.getElementById('modal-history-tbody').innerHTML = points
    .slice()
    .reverse()
    .map(
      (p) => `
      <tr>
        <td class="num">${new Date(p.bucket).toLocaleString('uk-UA')}</td>
        <td class="num">${fmtDisplayMoney(p.min_price)}</td>
        <td class="num">${fmtDisplayMoney(p.max_price)}</td>
        <td class="num">${fmtDisplayMoney(p.avg_price)}</td>
        <td class="num">${fmtDisplayMoney(p.median_price)}</td>
        <td class="num">${p.avg_volume}</td>
      </tr>
    `
    )
    .join('');
}

async function openItemModal(itemId) {
  state.activeItemId = itemId;
  state.activeHistoryStep = 'day';
  hideWfSuggestions();
  const modal = document.getElementById('item-modal');
  const modalPanel = modal.querySelector('.modal-panel');
  modal.classList.remove('hidden');
  if (modalPanel) modalPanel.scrollTop = 0;

  const detail = await api(`/api/v1/items/${itemId}`);
  state.lastDetail = detail;
  if (modalPanel) modalPanel.scrollTop = 0;

  document.getElementById('modal-item-title').textContent = detail.name;
  document.getElementById('modal-item-subtitle').textContent =
    detail.name_en && detail.name_en !== detail.name
      ? `${detail.name_en} · ${detail.game_code.toUpperCase()}`
      : detail.game_code.toUpperCase();

  const imgEl = document.getElementById('modal-item-image');
  const stageEl = imgEl.parentElement;
  imgEl.src = detail.icon_url || '';
  imgEl.alt = detail.name;
  imgEl.classList.toggle('wf-portrait-fade', isWfHalfBodyPortrait(detail));
  stageEl.classList.toggle(
    'wf-bp-stage',
    detail.game_code === 'warframe' &&
      detail.subcategory === 'blueprint' &&
      !String(detail.icon_url || '').includes('sub_icons/')
  );

  const descEl = document.getElementById('modal-item-desc');
  if (detail.description) {
    const descHeading = detail.item_type === 'mods' ? 'Ефект модифікатора' : 'Опис предмета';
    descEl.innerHTML = `<div class="item-desc-label">${descHeading}</div><div class="item-desc-text">${formatDescHtml(detail.description)}</div>`;
    descEl.classList.remove('hidden');
  } else {
    descEl.classList.add('hidden');
  }

  renderModalCurrencySection();

  const relWrap = document.getElementById('modal-related-wrap');
  const relList = document.getElementById('modal-related-list');
  if (detail.related_parts && detail.related_parts.length > 0) {
    relWrap.classList.remove('hidden');
    relList.innerHTML = detail.related_parts
      .map((p) => {
        const plt = Math.max(1, Math.round(Number(p.latest_min_price || 0) / PLT_USD_RATE));
        const pImgCls =
          !String(p.icon_url || '').includes('sub_icons/') && p.subcategory === 'blueprint'
            ? 'wf-portrait-fade'
            : '';
        return `
          <button type="button" class="related-part-chip" data-rel-item="${p.id}">
            <div class="related-part-icon">
              <img class="${pImgCls}" src="${esc(p.icon_url || '')}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer" />
            </div>
            <div class="related-part-info">
              <div class="related-part-name">${esc(p.name)}</div>
              <div class="related-part-price">${plt} PLT · ${fmtDisplayMoney(p.latest_min_price)}</div>
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
  state.lastHistoryPoints = hist.points;

  renderHistoryRows(hist.points);
  renderPriceChart(hist.points, ma7Price);
}

function renderPriceChart(points, ma7Price) {
  const canvas = document.getElementById('price-chart');
  if (state.chartInstance) state.chartInstance.destroy();
  if (typeof window.Chart === 'undefined') return;

  const isRust = state.game === 'rust';
  const curCode = state.displayCurrency;
  const curSym = curCode === 'UAH' ? '₴' : '$';
  const lineColor = isRust ? '#d9503a' : '#4ab1c9';
  const barColor = isRust ? 'rgba(217, 150, 74, 0.18)' : 'rgba(201, 169, 97, 0.18)';
  const ctx2d = canvas.getContext('2d');
  const grad = ctx2d.createLinearGradient(0, 0, 0, 260);
  grad.addColorStop(0, isRust ? 'rgba(205, 65, 43, 0.30)' : 'rgba(63, 142, 163, 0.32)');
  grad.addColorStop(1, 'rgba(0, 0, 0, 0)');

  const labels = points.map((p) => {
    const d = new Date(p.bucket);
    return state.activeHistoryStep === 'hour'
      ? d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit' });
  });

  const datasets = [
    {
      type: 'line',
      label: `Середня ціна (${curCode})`,
      data: points.map((p) => Number(toDisplayNum(p.avg_price).toFixed(2))),
      borderColor: lineColor,
      backgroundColor: grad,
      borderWidth: 2.5,
      pointRadius: 2.5,
      pointHoverRadius: 5,
      pointBackgroundColor: lineColor,
      pointStyle: 'circle',
      tension: 0.3,
      fill: true,
      yAxisID: 'y',
    },
    {
      type: 'bar',
      label: 'Обсяг лотів',
      data: points.map((p) => p.avg_volume),
      backgroundColor: barColor,
      borderRadius: 4,
      barPercentage: 0.45,
      categoryPercentage: 0.8,
      pointStyle: 'rectRounded',
      yAxisID: 'y1',
    },
  ];

  if (ma7Price !== null && ma7Price !== undefined && points.length) {
    const ma7Scaled = Number(toDisplayNum(ma7Price).toFixed(2));
    datasets.push({
      type: 'line',
      label: 'Ковзне середнє (MA-7)',
      data: points.map(() => ma7Scaled),
      borderColor: '#d4a94e',
      borderDash: [6, 4],
      borderWidth: 1.6,
      pointRadius: 0,
      pointHoverRadius: 0,
      pointStyle: 'line',
      yAxisID: 'y',
    });
  }

  state.chartInstance = new window.Chart(canvas, {
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#cbd5e1',
            font: { size: 12 },
            usePointStyle: true,
            boxWidth: 10,
            padding: 16,
          },
        },
        tooltip: {
          backgroundColor: isRust ? 'rgba(22, 23, 28, 0.96)' : 'rgba(17, 25, 30, 0.96)',
          titleColor: '#f8fafc',
          titleFont: { size: 13, weight: 'bold' },
          bodyColor: '#d8e3e8',
          bodyFont: { size: 12.5 },
          borderColor: isRust ? '#464854' : '#35505e',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          boxPadding: 5,
          usePointStyle: true,
          callbacks: {
            label(ctx) {
              const v = ctx.parsed.y;
              if (ctx.dataset.yAxisID === 'y1') {
                return ` ${ctx.dataset.label}: ${Math.round(v)} шт.`;
              }
              return ` ${ctx.dataset.label}: ${curSym}${Number(v).toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: '#93a6b0' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: {
          position: 'left',
          ticks: {
            color: '#cbd5e1',
            callback: (val) => `${curSym}${Number(val).toFixed(2)}`,
          },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y1: {
          position: 'right',
          ticks: { color: '#667983' },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

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
  const [allWatches, allAlerts] = await Promise.all([
    api('/api/v1/watch'),
    api(`/api/v1/alerts?unread=${unreadOnly}`),
  ]);

  const gf = state.alertsGameFilter;
  const watches = gf ? allWatches.filter((w) => w.game_code === gf) : allWatches;
  const alerts = gf ? allAlerts.filter((a) => !a.game_code || a.game_code === gf) : allAlerts;

  document.getElementById('watch-tbody').innerHTML = watches.length
    ? watches
        .map(
          (w) => `
          <tr class="clickable" data-open-item="${w.item_id}">
            <td><strong>${esc(w.item_name)}</strong> <span class="muted" style="font-size:11.5px;">${esc((w.game_code || '').toUpperCase())}</span></td>
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
          <tr class="${a.item_id ? 'clickable' : ''}" ${a.item_id ? `data-open-item="${a.item_id}"` : ''}>
            <td style="${a.is_read ? 'opacity:0.6;' : 'font-weight:500;'}">
              ${a.game_code ? `<span class="rarity-pill ${a.game_code === 'rust' ? 'legendary' : 'rare'}" style="margin-right:6px;">${esc(a.game_code.toUpperCase())}</span>` : ''}
              ${esc(a.message)}
            </td>
            <td class="num muted">${new Date(a.created_at).toLocaleString('uk-UA')}</td>
            <td>${a.is_read ? '<span class="muted">Прочитано</span>' : `<button class="btn btn-sm" data-read-alert="${a.id}">Прочитано</button>`}</td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="3" class="muted" style="text-align:center; padding:20px;">Сповіщень немає.</td></tr>`;

  document.querySelectorAll('#tab-alerts tr[data-open-item]').forEach((row) => {
    row.addEventListener('click', () => openItemModal(Number(row.dataset.openItem)));
  });

  document.querySelectorAll('[data-del-watch]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await api(`/api/v1/watch/${btn.dataset.delWatch}`, { method: 'DELETE' });
      showToast('Спостереження видалено');
      await loadAlertsAndWatches();
    });
  });

  document.querySelectorAll('[data-read-alert]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
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

function wireEvents() {
  document.getElementById('btn-back-splash').addEventListener('click', returnToSplash);
  document.querySelectorAll('[data-switch-game]').forEach((b) => {
    b.addEventListener('click', () => selectGame(b.dataset.switchGame));
  });
  document.querySelectorAll('.nav-tab').forEach((b) => {
    b.addEventListener('click', () => switchTab(b.dataset.tab));
  });

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

  let wfTimer = null;
  let wfSugTimer = null;
  const wfInput = document.getElementById('wf-search-input');

  wfInput.addEventListener('focus', () => {
    loadWfSuggestions(wfInput.value);
  });

  wfInput.addEventListener('input', (e) => {
    state.filters.q = e.target.value;
    state.filters.page = 1;
    clearTimeout(wfTimer);
    clearTimeout(wfSugTimer);
    wfTimer = setTimeout(loadWarframeCatalog, 220);
    wfSugTimer = setTimeout(() => loadWfSuggestions(e.target.value), 140);
  });

  wfInput.addEventListener('keydown', (e) => {
    const box = document.getElementById('wf-search-suggestions');
    if (box.classList.contains('hidden')) return;
    const btns = box.querySelectorAll('.wf-sug-item');
    if (e.key === 'ArrowDown' && btns.length) {
      e.preventDefault();
      state.sugIndex = (state.sugIndex + 1) % btns.length;
      btns.forEach((b, i) => b.classList.toggle('active', i === state.sugIndex));
    } else if (e.key === 'ArrowUp' && btns.length) {
      e.preventDefault();
      state.sugIndex = state.sugIndex <= 0 ? btns.length - 1 : state.sugIndex - 1;
      btns.forEach((b, i) => b.classList.toggle('active', i === state.sugIndex));
    } else if (e.key === 'Enter' && state.sugIndex >= 0 && btns[state.sugIndex]) {
      e.preventDefault();
      btns[state.sugIndex].click();
    } else if (e.key === 'Escape') {
      hideWfSuggestions();
    }
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.wf-search-wrap')) hideWfSuggestions();
  });

  document.getElementById('wf-search-btn').addEventListener('click', () => {
    hideWfSuggestions();
    state.filters.q = wfInput.value;
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
      if (state.activeItemId) {
        loadItemHistory(
          state.activeItemId,
          btn.dataset.step,
          state.lastDetail ? state.lastDetail.ma7_price : null
        );
      }
    });
  });

  document.querySelectorAll('#modal-currency-switch .col-cur-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.displayCurrency = btn.dataset.cur;
      localStorage.setItem('econ_cur', state.displayCurrency);
      renderModalCurrencySection();
      if (state.game === 'warframe') loadWarframeCatalog();
    });
  });

  document.querySelectorAll('#alerts-game-filter button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.alertsGameFilter = btn.dataset.alertGame;
      document.querySelectorAll('#alerts-game-filter button').forEach((b) => {
        b.classList.toggle('active', b === btn);
      });
      loadAlertsAndWatches();
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

async function loadFxRates() {
  try {
    const fx = await api('/api/v1/fx-rates');
    state.fx = {
      usd_to_uah: Number(fx.usd_to_uah || 41.5),
      eur_to_usd: Number(fx.eur_to_usd || 1.08),
      plt_to_usd: Number(fx.plt_to_usd || 0.04999),
      source: fx.source || 'fallback',
    };
  } catch {
  }
}

function hideWfSuggestions() {
  const box = document.getElementById('wf-search-suggestions');
  if (box) box.classList.add('hidden');
  state.sugIndex = -1;
}

async function loadWfSuggestions(query) {
  const box = document.getElementById('wf-search-suggestions');
  if (!box || state.game !== 'warframe' || state.tab !== 'catalog') return;

  const q = String(query || '').trim();
  const qs = new URLSearchParams({ game: 'warframe', page_size: '8', sort: 'volume_desc' });
  if (q) qs.set('q', q);

  try {
    const data = await api(`/api/v1/items?${qs.toString()}`);
    state.sugItems = data.items || [];
    state.sugIndex = -1;

    if (!state.sugItems.length) {
      box.innerHTML = `<div class="wf-sug-empty">Нічого не знайдено за запитом «${esc(q)}»</div>`;
      box.classList.remove('hidden');
      return;
    }

    box.innerHTML = state.sugItems
      .map((it) => {
        const plt = Math.max(1, Math.round(Number(it.latest_min_price || 0) / PLT_USD_RATE));
        return `
          <button type="button" class="wf-sug-item" data-sug-id="${it.id}">
            <div class="wf-sug-left">
              <div class="wf-sug-ico">
                <img src="${esc(it.icon_url || '')}" alt="" loading="lazy" referrerpolicy="no-referrer" />
              </div>
              <div style="min-width:0; flex:1;">
                <div class="wf-sug-uk">${highlightMatch(it.name, q)}</div>
                <div class="wf-sug-en">${highlightMatch(it.name_en || '', q)}</div>
              </div>
            </div>
            <div class="wf-sug-price">${plt} PLT</div>
          </button>
        `;
      })
      .join('');

    box.classList.remove('hidden');
    box.querySelectorAll('[data-sug-id]').forEach((btn) => {
      btn.addEventListener('click', () => openItemModal(Number(btn.dataset.sugId)));
    });
  } catch {
    hideWfSuggestions();
  }
}

async function boot() {
  initSplash();
  initCustomSelects();
  initSegmentedToggles();
  wireEvents();
  await Promise.all([loadFxRates(), loadGamesMeta(), syncUser()]);
}

boot();
