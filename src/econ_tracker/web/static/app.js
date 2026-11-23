import { getSubcategoryIcon } from '/static/icons.js';

const PLT_USD_RATE = 0.04999;

const state = {
  game: 'warframe',
  tab: 'catalog',
  token: localStorage.getItem('econ_token') || null,
  user: null,
  gamesMeta: {},
  facets: [],
  filters: {
    item_type: '',
    subcategory: '',
    q: '',
    rarity: '',
    price_min: '',
    price_max: '',
    sort: 'volume_desc',
    page: 1,
  },
  activeItemId: null,
  activeHistoryStep: 'day',
  chartInstance: null,
};

// ============================================================================
// HTTP HELPER & TOAST
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
  if (!resp.ok) {
    throw new Error(data.detail || data.title || `HTTP ${resp.status}`);
  }
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
  const n = Number(val);
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtCompactUsd(val) {
  const n = Number(val || 0);
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return fmtUsd(n);
}

function fmtPriceForGame(usdVal, gameCode) {
  if (usdVal === null || usdVal === undefined) return '—';
  const n = Number(usdVal);
  if (gameCode === 'warframe') {
    const plt = Math.max(1, Math.round(n / PLT_USD_RATE));
    return `<strong>${plt} PLT</strong> <span class="muted" style="font-size:11.5px;">(${fmtUsd(n)})</span>`;
  }
  return `<strong>${fmtUsd(n)}</strong>`;
}

function fmtPct(val) {
  if (val === null || val === undefined) return '<span class="muted">—</span>';
  const n = Number(val);
  const cls = n > 0 ? 'pos' : n < 0 ? 'neg' : 'muted';
  const sign = n > 0 ? '+' : '';
  return `<span class="mono ${cls}">${sign}${n.toFixed(2)}%</span>`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============================================================================
// SPLASH SCREEN (3D TILT + MINIMAL MARKET CAP)
// ============================================================================
function initSplash() {
  const splash = document.getElementById('splash-screen');
  const panes = splash.querySelectorAll('.splash-pane');

  panes.forEach((pane) => {
    const game = pane.dataset.game;
    const stage = pane.querySelector('.splash-art-stage');
    const sheen = pane.querySelector('.splash-sheen');

    pane.addEventListener('mouseenter', () => {
      splash.classList.remove('hover-warframe', 'hover-rust');
      splash.classList.add(`hover-${game}`);
    });

    pane.addEventListener('mousemove', (e) => {
      const r = pane.getBoundingClientRect();
      const nx = (e.clientX - r.left) / r.width - 0.5;
      const ny = (e.clientY - r.top) / r.height - 0.5;
      stage.style.transform = `rotateY(${nx * 5}deg) rotateX(${-ny * 4}deg) translate3d(${-nx * 14}px, ${-ny * 10}px, 18px)`;
      const gx = ((e.clientX - r.left) / r.width) * 100;
      const gy = ((e.clientY - r.top) / r.height) * 100;
      const glow = game === 'warframe' ? 'rgba(56,189,248,0.14)' : 'rgba(205,65,43,0.16)';
      sheen.style.background = `radial-gradient(520px circle at ${gx}% ${gy}%, ${glow}, transparent 65%)`;
    });

    pane.addEventListener('mouseleave', () => {
      splash.classList.remove('hover-warframe', 'hover-rust');
      stage.style.transform = 'none';
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
        el.textContent = `Общая стоимость рынка: ${fmtCompactUsd(g.total_market_value_usd)} · ${g.total_offers.toLocaleString('ru-RU')} лотов`;
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
  }, 320);
}

function returnToSplash() {
  const splash = document.getElementById('splash-screen');
  const shell = document.getElementById('app-shell');
  shell.classList.add('hidden');
  splash.classList.remove('hidden');
  requestAnimationFrame(() => splash.classList.remove('exiting'));
}

// ============================================================================
// GAME THEME & BANNER SWITCHING
// ============================================================================
async function selectGame(gameCode) {
  state.game = gameCode;
  document.documentElement.setAttribute('data-theme', gameCode);

  document.querySelectorAll('[data-switch-game]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.switchGame === gameCode);
  });

  // Reset category filters when switching universe
  state.filters.item_type = '';
  state.filters.subcategory = '';
  state.filters.page = 1;

  const banner = document.getElementById('game-banner');
  const meta = state.gamesMeta[gameCode];
  if (gameCode === 'warframe') {
    banner.style.backgroundImage = "url('/static/img/warframe_hero.jpg')";
    document.getElementById('banner-title').textContent = 'WARFRAME';
    document.getElementById('banner-subtitle').textContent =
      'Warframe.market (PC / PS) · Живые ордера игроков в Platinum с приведением к USD';
  } else {
    banner.style.backgroundImage = "url('/static/img/rust_hero.jpg')";
    document.getElementById('banner-title').textContent = 'RUST';
    document.getElementById('banner-subtitle').textContent =
      'Skinport (EUR) × Rust.tm (USD) · Скины, спред между площадками и история цен';
  }
  if (meta) {
    document.getElementById('banner-items').textContent = meta.items_count;
    document.getElementById('banner-offers').textContent = meta.total_offers.toLocaleString('ru-RU');
    document.getElementById('banner-cap').textContent = fmtCompactUsd(meta.total_market_value_usd);
  }

  await loadCurrentTab();
}

// ============================================================================
// TAB NAVIGATION
// ============================================================================
async function switchTab(tabName) {
  state.tab = tabName;
  document.querySelectorAll('.nav-tab').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('hidden', panel.id !== `tab-${tabName}`);
  });
  await loadCurrentTab();
}

async function loadCurrentTab() {
  if (state.tab === 'catalog') {
    await loadFacets();
    await loadCatalogItems();
  } else if (state.tab === 'stats') {
    await loadAnalytics();
  } else if (state.tab === 'portfolio') {
    await loadPortfolio();
  } else if (state.tab === 'alerts') {
    await loadAlertsAndWatches();
  } else if (state.tab === 'anomalies') {
    await loadAnomalies();
  } else if (state.tab === 'admin') {
    await loadAdminStatus();
  }
}

// ============================================================================
// CATALOG: CATEGORIES -> OUTLINE SUBCATEGORIES -> FILTERED LIST
// ============================================================================
async function loadFacets() {
  state.facets = await api(`/api/v1/categories?game=${encodeURIComponent(state.game)}`);
  renderCategories();
  renderSubcategories();
}

function renderCategories() {
  const bar = document.getElementById('category-bar');
  const totalCount = state.facets.reduce((s, f) => s + f.items_count, 0);
  const allBtn = `
    <button class="cat-chip ${state.filters.item_type === '' ? 'active' : ''}" data-cat="">
      Все категории <span class="cnt">${totalCount}</span>
    </button>
  `;
  const catBtns = state.facets
    .map(
      (f) => `
      <button class="cat-chip ${state.filters.item_type === f.code ? 'active' : ''}" data-cat="${esc(f.code)}">
        ${esc(f.label)} <span class="cnt">${f.items_count}</span>
      </button>
    `
    )
    .join('');
  bar.innerHTML = allBtn + catBtns;

  bar.querySelectorAll('.cat-chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.filters.item_type = btn.dataset.cat;
      state.filters.subcategory = '';
      state.filters.page = 1;
      renderCategories();
      renderSubcategories();
      loadCatalogItems();
    });
  });
}

function renderSubcategories() {
  const strip = document.getElementById('subcategory-strip');
  if (!state.filters.item_type) {
    strip.classList.add('hidden');
    return;
  }
  const activeCat = state.facets.find((f) => f.code === state.filters.item_type);
  if (!activeCat || !activeCat.subcategories.length) {
    strip.classList.add('hidden');
    return;
  }

  strip.classList.remove('hidden');
  const allSub = `
    <button class="subcat-card ${state.filters.subcategory === '' ? 'active' : ''}" data-sub="">
      ${getSubcategoryIcon('default')}
      <span class="subcat-name">Все в типе</span>
      <span class="subcat-cnt">${activeCat.items_count}</span>
    </button>
  `;
  const subCards = activeCat.subcategories
    .map(
      (s) => `
      <button class="subcat-card ${state.filters.subcategory === s.code ? 'active' : ''}" data-sub="${esc(s.code)}">
        ${getSubcategoryIcon(s.code)}
        <span class="subcat-name">${esc(s.label)}</span>
        <span class="subcat-cnt">${s.items_count} шт</span>
      </button>
    `
    )
    .join('');
  strip.innerHTML = allSub + subCards;

  strip.querySelectorAll('.subcat-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.filters.subcategory = btn.dataset.sub;
      state.filters.page = 1;
      renderSubcategories();
      loadCatalogItems();
    });
  });
}

async function loadCatalogItems() {
  const p = new URLSearchParams({
    game: state.game,
    sort: state.filters.sort,
    page: String(state.filters.page),
    page_size: '20',
  });
  if (state.filters.item_type) p.set('item_type', state.filters.item_type);
  if (state.filters.subcategory) p.set('subcategory', state.filters.subcategory);
  if (state.filters.q) p.set('q', state.filters.q);
  if (state.filters.rarity) p.set('rarity', state.filters.rarity);
  if (state.filters.price_min) p.set('price_min', state.filters.price_min);
  if (state.filters.price_max) p.set('price_max', state.filters.price_max);

  const data = await api(`/api/v1/items?${p.toString()}`);
  const tbody = document.getElementById('catalog-tbody');

  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center; padding:32px;">Ничего не найдено по заданным фильтрам.</td></tr>`;
  } else {
    tbody.innerHTML = data.items
      .map(
        (it) => `
        <tr class="clickable" data-item-id="${it.id}">
          <td>
            <div class="item-cell">
              <div class="item-outline-thumb">${getSubcategoryIcon(it.subcategory)}</div>
              <div>
                <div style="font-weight:600;">${esc(it.name)}</div>
                <div class="muted" style="font-size:11.5px;">${esc(it.item_type)} · ${esc(it.subcategory)}</div>
              </div>
            </div>
          </td>
          <td><span class="rarity-pill ${esc(it.rarity)}">${esc(it.rarity)}</span></td>
          <td class="mono">${fmtPriceForGame(it.latest_min_price, it.game_code)}</td>
          <td class="mono">${it.latest_total_volume.toLocaleString('ru-RU')}</td>
          <td class="mono">${it.spread_pct !== null ? `+${Number(it.spread_pct).toFixed(1)}%` : '—'}</td>
          <td>${fmtPct(it.price_change_24h_pct)}</td>
          <td class="mono muted">${fmtUsd(it.ma7_price)}</td>
        </tr>
      `
      )
      .join('');

    tbody.querySelectorAll('tr[data-item-id]').forEach((row) => {
      row.addEventListener('click', () => openItemModal(Number(row.dataset.itemId)));
    });
  }

  document.getElementById('pagination-info').textContent = `Найдено: ${data.total} предметов`;
  document.getElementById('pagination-page').textContent = `${data.page} / ${data.pages}`;
  document.getElementById('btn-prev-page').disabled = data.page <= 1;
  document.getElementById('btn-next-page').disabled = data.page >= data.pages;
}

// ============================================================================
// ITEM DETAIL MODAL (INFO, MARKETS, CHART.JS, CSV, WATCH & TRADE)
// ============================================================================
async function openItemModal(itemId) {
  state.activeItemId = itemId;
  state.activeHistoryStep = 'day';
  document.getElementById('item-modal').classList.remove('hidden');

  const detail = await api(`/api/v1/items/${itemId}`);
  document.getElementById('modal-item-icon').innerHTML = getSubcategoryIcon(detail.subcategory);
  document.getElementById('modal-item-title').textContent = detail.name;

  const releasedText = detail.released_at
    ? ` · Появление: ${new Date(detail.released_at).toLocaleDateString('ru-RU')}`
    : '';
  document.getElementById('modal-item-meta').textContent =
    `${detail.game_code.toUpperCase()} · ${detail.item_type} / ${detail.subcategory} · ${detail.rarity}${releasedText} · Лотов: ${detail.latest_total_volume}`;

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
        <td class="mono">${Number(m.original_price).toFixed(2)} ${esc(m.original_currency)}</td>
        <td class="mono">${fmtUsd(m.normalized_price)}</td>
        <td class="mono">${m.volume}</td>
        <td class="muted" style="font-size:12px;">${new Date(m.last_checked_at).toLocaleString('ru-RU')}</td>
      </tr>
    `
    )
    .join('');

  // Populate quick watch & trade forms for authenticated users
  const actionsWrap = document.getElementById('modal-user-actions');
  if (state.user && detail.markets.length) {
    actionsWrap.classList.remove('hidden');
    const marketOptions = detail.markets
      .map((m) => `<option value="${m.market_id}">${esc(m.market_name)}</option>`)
      .join('');
    document.getElementById('watch-market-select').innerHTML = marketOptions;
    document.getElementById('trade-market-select').innerHTML = marketOptions;
    const basePrice = Number(detail.cheapest_price || 1).toFixed(2);
    document.getElementById('watch-threshold-input').value = basePrice;
    document.getElementById('trade-price-input').value = basePrice;
  } else {
    actionsWrap.classList.add('hidden');
  }

  document.querySelectorAll('#history-step-switch button').forEach((b) => {
    b.classList.toggle('active', b.dataset.step === 'day');
  });
  await loadItemHistory(itemId, 'day', detail.ma7_price);
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
        <td class="mono" style="font-size:12px;">${new Date(p.bucket).toLocaleString('ru-RU')}</td>
        <td class="mono">${fmtUsd(p.min_price)}</td>
        <td class="mono">${fmtUsd(p.max_price)}</td>
        <td class="mono">${fmtUsd(p.avg_price)}</td>
        <td class="mono">${fmtUsd(p.median_price)}</td>
        <td class="mono">${p.avg_volume}</td>
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
  const lineColor = isRust ? '#cd412b' : '#38bdf8';
  const barColor = isRust ? 'rgba(217, 119, 6, 0.25)' : 'rgba(201, 169, 97, 0.25)';

  const labels = points.map((p) => {
    const d = new Date(p.bucket);
    return state.activeHistoryStep === 'hour'
      ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  });

  const datasets = [
    {
      type: 'line',
      label: 'Средняя цена (USD)',
      data: points.map((p) => Number(p.avg_price)),
      borderColor: lineColor,
      backgroundColor: isRust ? 'rgba(205, 65, 43, 0.14)' : 'rgba(56, 189, 248, 0.14)',
      borderWidth: 2,
      tension: 0.25,
      fill: true,
      yAxisID: 'y',
    },
    {
      type: 'bar',
      label: 'Объём лотов',
      data: points.map((p) => p.avg_volume),
      backgroundColor: barColor,
      yAxisID: 'y1',
    },
  ];

  if (ma7Price !== null && ma7Price !== undefined && points.length) {
    datasets.push({
      type: 'line',
      label: 'MA-7 (USD)',
      data: points.map(() => Number(ma7Price)),
      borderColor: '#94a3b8',
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
      plugins: { legend: { labels: { color: '#cbd5e1', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.08)' } },
        y: { position: 'left', ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(148,163,184,0.08)' } },
        y1: { position: 'right', ticks: { color: '#64748b' }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

// ============================================================================
// ANALYTICS TAB
// ============================================================================
async function loadAnalytics() {
  const [overview, spreads] = await Promise.all([
    api(`/api/v1/stats/overview?game=${encodeURIComponent(state.game)}`),
    api(`/api/v1/stats/spread?game=${encodeURIComponent(state.game)}&limit=12`),
  ]);

  const idx = overview.game_indices[0];
  document.getElementById('stats-kpis').innerHTML = `
    <div class="kpi-card"><div class="kpi-lbl">Отслеживается предметов</div><div class="kpi-val">${overview.total_items}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Снимков истории в БД</div><div class="kpi-val">${overview.total_snapshots.toLocaleString('ru-RU')}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Индекс игры (24ч)</div><div class="kpi-val">${idx ? fmtPct(idx.avg_change_24h_pct) : '—'}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Индекс игры (7д)</div><div class="kpi-val">${idx ? fmtPct(idx.avg_change_7d_pct) : '—'}</div></div>
  `;

  document.getElementById('stats-spread-tbody').innerHTML = spreads
    .map(
      (s) => `
      <tr class="clickable" data-open-item="${s.item_id}">
        <td><strong>${esc(s.name)}</strong></td>
        <td class="mono">${fmtUsd(s.min_price)} <span class="muted" style="font-size:11px;">(${esc(s.cheapest_market)})</span></td>
        <td class="mono">${fmtUsd(s.max_price)} <span class="muted" style="font-size:11px;">(${esc(s.priciest_market)})</span></td>
        <td class="mono pos">+${fmtUsd(s.spread_abs)}</td>
        <td class="mono pos"><strong>+${Number(s.spread_pct).toFixed(1)}%</strong></td>
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
          <td class="mono">${fmtUsd(m.current_price)}</td>
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
        <td><span class="rarity-pill ${esc(r.rarity)}">${esc(r.rarity)}</span></td>
        <td class="mono">${r.items_count}</td>
        <td class="mono">${fmtUsd(r.avg_price)}</td>
        <td class="mono">${r.total_volume.toLocaleString('ru-RU')}</td>
      </tr>
    `
    )
    .join('');

  document.querySelectorAll('#tab-stats [data-open-item]').forEach((row) => {
    row.addEventListener('click', () => openItemModal(Number(row.dataset.openItem)));
  });
}

// ============================================================================
// PORTFOLIO TAB
// ============================================================================
async function loadPortfolio() {
  const guestBox = document.getElementById('portfolio-guest-notice');
  const content = document.getElementById('portfolio-content');
  if (!state.user) {
    guestBox.classList.remove('hidden');
    content.classList.add('hidden');
    return;
  }
  guestBox.classList.add('hidden');
  content.classList.remove('hidden');

  const [port, trades] = await Promise.all([api('/api/v1/portfolio'), api('/api/v1/trades')]);

  const pnlFmt = (v) => {
    const n = Number(v);
    return `<span class="${n >= 0 ? 'pos' : 'neg'}">${n >= 0 ? '+' : ''}${fmtUsd(n)}</span>`;
  };

  document.getElementById('portfolio-kpis').innerHTML = `
    <div class="kpi-card"><div class="kpi-lbl">Вложено</div><div class="kpi-val">${fmtUsd(port.invested)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Текущая оценка</div><div class="kpi-val">${fmtUsd(port.current_value)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Реализованный PnL</div><div class="kpi-val">${pnlFmt(port.realized_pnl)}</div></div>
    <div class="kpi-card"><div class="kpi-lbl">Нереализованный PnL</div><div class="kpi-val">${pnlFmt(port.unrealized_pnl)}</div></div>
  `;

  document.getElementById('portfolio-positions-tbody').innerHTML = port.positions.length
    ? port.positions
        .map(
          (p) => `
          <tr>
            <td><strong>${esc(p.item_name)}</strong> <span class="muted" style="font-size:11px;">${esc(p.game_code)}</span></td>
            <td class="mono">${p.quantity}</td>
            <td class="mono">${fmtUsd(p.avg_cost)}</td>
            <td class="mono">${fmtUsd(p.current_price)}</td>
            <td class="mono">${fmtUsd(p.invested)}</td>
            <td class="mono">${pnlFmt(p.realized_pnl)}</td>
            <td class="mono">${pnlFmt(p.unrealized_pnl)}</td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="7" class="muted" style="text-align:center; padding:24px;">Позиций пока нет — откройте любой предмет в каталоге и запишите сделку.</td></tr>`;

  document.getElementById('portfolio-trades-tbody').innerHTML = trades
    .map(
      (t) => `
      <tr>
        <td class="mono" style="font-size:12px;">${new Date(t.traded_at).toLocaleString('ru-RU')}</td>
        <td>${esc(t.item_name)}</td>
        <td class="muted">${esc(t.market_name)}</td>
        <td><span class="rarity-pill ${t.side === 'buy' ? 'uncommon' : 'legendary'}">${t.side.toUpperCase()}</span></td>
        <td class="mono">${t.quantity}</td>
        <td class="mono">${fmtUsd(t.price)}</td>
        <td><button class="btn btn-sm btn-danger" data-del-trade="${t.id}">Удалить</button></td>
      </tr>
    `
    )
    .join('');

  document.querySelectorAll('[data-del-trade]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/api/v1/trades/${btn.dataset.delTrade}`, { method: 'DELETE' });
        showToast('Сделка удалена, позиция пересчитана с начала истории');
        await loadPortfolio();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });
}

// ============================================================================
// WATCHLIST & ALERTS TAB
// ============================================================================
async function loadAlertsAndWatches() {
  const guestBox = document.getElementById('alerts-guest-notice');
  const content = document.getElementById('alerts-content');
  if (!state.user) {
    guestBox.classList.remove('hidden');
    content.classList.add('hidden');
    return;
  }
  guestBox.classList.add('hidden');
  content.classList.remove('hidden');

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
            <td class="mono">${w.direction === 'below' ? '≤' : '≥'} ${fmtUsd(w.threshold)}</td>
            <td class="mono muted">${w.cooldown_minutes} мин</td>
            <td><button class="btn btn-sm btn-danger" data-del-watch="${w.id}">×</button></td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="5" class="muted" style="text-align:center; padding:20px;">Подписок нет.</td></tr>`;

  document.getElementById('alerts-tbody').innerHTML = alerts.length
    ? alerts
        .map(
          (a) => `
          <tr>
            <td style="${a.is_read ? 'opacity:0.6;' : 'font-weight:600;'}">${esc(a.message)}</td>
            <td class="mono muted" style="font-size:11.5px;">${new Date(a.created_at).toLocaleString('ru-RU')}</td>
            <td>${a.is_read ? '<span class="muted">Прочитано</span>' : `<button class="btn btn-sm" data-read-alert="${a.id}">Ок</button>`}</td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="3" class="muted" style="text-align:center; padding:20px;">Уведомлений нет.</td></tr>`;

  document.querySelectorAll('[data-del-watch]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await api(`/api/v1/watch/${btn.dataset.delWatch}`, { method: 'DELETE' });
      showToast('Подписка удалена');
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

// ============================================================================
// ANOMALIES TAB
// ============================================================================
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
          <tr>
            <td><strong>${esc(a.item_name)}</strong></td>
            <td class="muted">${esc(a.market_name)}</td>
            <td class="mono">${fmtUsd(a.ma7_price)} → ${fmtUsd(a.trigger_price)}</td>
            <td>${fmtPct(a.max_deviation_pct)}</td>
            <td class="mono muted">${a.duration_minutes} мин</td>
            <td>
              <span class="rarity-pill ${a.status === 'open' ? 'legendary' : 'uncommon'}">${a.status.toUpperCase()}</span>
              ${a.comment ? `<div class="muted" style="font-size:11.5px; margin-top:4px;">${esc(a.comment)}</div>` : ''}
            </td>
            <td>
              ${
                a.status === 'open' && canClose
                  ? `<button class="btn btn-sm btn-primary" data-close-anom="${a.id}">Закрыть</button>`
                  : ''
              }
            </td>
          </tr>
        `
        )
        .join('')
    : `<tr><td colspan="7" class="muted" style="text-align:center; padding:24px;">Событий не найдено.</td></tr>`;

  document.querySelectorAll('[data-close-anom]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const comment = window.prompt('Комментарий аналитика к закрытию аномалии:', 'Проверено: сезонный всплеск спроса');
      if (!comment || comment.trim().length < 3) return;
      try {
        await api(`/api/v1/anomalies/${btn.dataset.closeAnom}/close`, {
          method: 'POST',
          body: { comment: comment.trim() },
        });
        showToast('Аномалия закрыта');
        await loadAnomalies();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });
}

// ============================================================================
// ADMIN TAB
// ============================================================================
async function loadAdminStatus() {
  if (!state.user || (state.user.role !== 'admin' && state.user.role !== 'analyst')) return;
  const rows = await api('/api/v1/admin/collection/status');
  const isAdmin = state.user.role === 'admin';
  document.getElementById('admin-status-tbody').innerHTML = rows
    .map(
      (r) => `
      <tr>
        <td><strong>${esc(r.market_name)}</strong> <span class="mono muted" style="font-size:11px;">(${esc(r.market_code)})</span></td>
        <td>${esc(r.game_code)}</td>
        <td class="mono">${esc(r.currency)}</td>
        <td class="mono">${r.schedule_minutes} мин</td>
        <td class="mono muted" style="font-size:12px;">${r.last_run_at ? new Date(r.last_run_at).toLocaleString('ru-RU') : '—'}</td>
        <td class="mono">${r.accepted_count} / <span class="${r.rejected_count > 0 ? 'neg' : 'muted'}">${r.rejected_count}</span></td>
        <td>
          <span class="rarity-pill ${r.last_status === 'failed' ? 'legendary' : 'uncommon'}">${esc(r.last_status || 'idle')}</span>
          ${r.last_error ? `<div class="neg" style="font-size:11.5px; margin-top:4px;">${esc(r.last_error)}</div>` : ''}
        </td>
        <td>${isAdmin ? `<button class="btn btn-sm" data-run-market="${r.market_id}">Собрать</button>` : ''}</td>
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
        showToast('Сбор завершён');
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
    pill.textContent = `${state.user.username} (${state.user.role})`;
    pill.classList.remove('hidden');
    btnAuth.classList.add('hidden');
    btnLogout.classList.remove('hidden');
    adminTab.classList.toggle(
      'hidden',
      state.user.role !== 'admin' && state.user.role !== 'analyst'
    );
    await refreshUnreadBadge();
  } else {
    pill.classList.add('hidden');
    btnAuth.classList.remove('hidden');
    btnLogout.classList.add('hidden');
    adminTab.classList.add('hidden');
    document.getElementById('unread-badge').classList.add('hidden');
  }
}

async function performAuth(endpoint, username, password) {
  try {
    const res = await api(endpoint, { method: 'POST', body: { username, password } });
    state.token = res.access_token;
    localStorage.setItem('econ_token', res.access_token);
    document.getElementById('auth-modal').classList.add('hidden');
    await syncUser();
    showToast(`Вы вошли как ${res.user.username} (${res.user.role})`);
    await loadCurrentTab();
  } catch (err) {
    showToast(err.message, true);
  }
}

// ============================================================================
// EVENT WIRING
// ============================================================================
function wireEvents() {
  document.getElementById('btn-back-splash').addEventListener('click', returnToSplash);

  document.querySelectorAll('[data-switch-game]').forEach((btn) => {
    btn.addEventListener('click', () => selectGame(btn.dataset.switchGame));
  });

  document.querySelectorAll('.nav-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Catalog filters
  let searchTimer = null;
  document.getElementById('filter-q').addEventListener('input', (e) => {
    state.filters.q = e.target.value;
    state.filters.page = 1;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadCatalogItems, 220);
  });

  for (const [id, key] of [
    ['filter-rarity', 'rarity'],
    ['filter-min', 'price_min'],
    ['filter-max', 'price_max'],
    ['filter-sort', 'sort'],
  ]) {
    document.getElementById(id).addEventListener('change', (e) => {
      state.filters[key] = e.target.value;
      state.filters.page = 1;
      loadCatalogItems();
    });
  }

  document.getElementById('btn-reset-filters').addEventListener('click', () => {
    state.filters = {
      item_type: '',
      subcategory: '',
      q: '',
      rarity: '',
      price_min: '',
      price_max: '',
      sort: 'volume_desc',
      page: 1,
    };
    document.getElementById('filter-q').value = '';
    document.getElementById('filter-rarity').value = '';
    document.getElementById('filter-min').value = '';
    document.getElementById('filter-max').value = '';
    document.getElementById('filter-sort').value = 'volume_desc';
    renderCategories();
    renderSubcategories();
    loadCatalogItems();
  });

  document.getElementById('btn-prev-page').addEventListener('click', () => {
    if (state.filters.page > 1) {
      state.filters.page -= 1;
      loadCatalogItems();
    }
  });
  document.getElementById('btn-next-page').addEventListener('click', () => {
    state.filters.page += 1;
    loadCatalogItems();
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
          direction: document.getElementById('watch-dir-select').value,
          threshold: document.getElementById('watch-threshold-input').value,
          cooldown_minutes: 60,
        },
      });
      showToast('Подписка создана');
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
          side: document.getElementById('trade-side-select').value,
          qty: Number(document.getElementById('trade-qty-input').value),
          price: document.getElementById('trade-price-input').value,
          traded_at: new Date().toISOString(),
        },
      });
      showToast('Сделка записана в портфель');
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // Alerts, Anomalies, Admin
  document.getElementById('alerts-unread-only').addEventListener('change', loadAlertsAndWatches);
  document.getElementById('anomaly-status-filter').addEventListener('change', loadAnomalies);
  document.getElementById('btn-collect-all').addEventListener('click', async () => {
    const btn = document.getElementById('btn-collect-all');
    btn.disabled = true;
    btn.textContent = 'Сбор запущен...';
    try {
      await api('/api/v1/collect/run', { method: 'POST', body: {} });
      showToast('Параллельный сбор по всем площадкам завершён');
      await loadAdminStatus();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Запустить сбор со всех площадок';
    }
  });

  // Auth modal
  window.__openAuthModal = () => document.getElementById('auth-modal').classList.remove('hidden');
  document.getElementById('btn-auth').addEventListener('click', window.__openAuthModal);
  document.getElementById('btn-close-auth-modal').addEventListener('click', () => {
    document.getElementById('auth-modal').classList.add('hidden');
  });
  document.getElementById('btn-logout').addEventListener('click', async () => {
    state.token = null;
    localStorage.removeItem('econ_token');
    await syncUser();
    showToast('Вы вышли из аккаунта');
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

// ============================================================================
// BOOTSTRAP
// ============================================================================
async function boot() {
  initSplash();
  wireEvents();
  await Promise.all([loadGamesMeta(), syncUser()]);
}

boot();
