/* ============================================================
   WARDROBE AI — app.js v7
   Today-first: smart daily outfit recommendations + day logging
   ============================================================ */

let allItems = [];
let activeFilter = 'all';
let selectedOutfits = { casual: null, home: null, around_home: null };
let explicitlySelected = { casual: false, home: false, around_home: false };
let currentDayType = 'college';
let todayData = null;          // { date, day_type, slots: { casual:[], home:[], around_home:[] } }
let todayLoggedSlots = {};     // { casual: {...}, home: {...}, around_home: {...} }

// ── Pending states ────────────────────────────────────────────
let pendingWear       = null;  // { type: 'outfit'|'item', id, dest? }
let pendingSlotWear   = null;  // { slot, pairing_id, pairing_name }
let pendingVote       = null;
let selectedDirtLevel = null;
let selectedSlotDirt  = null;
let selectedVoteValue = null;

const SLOT_LABELS = { casual: '🎓 Casual', home: '🏠 Home', around_home: '🚪 Around Home' };
const SLOT_ICONS  = { casual: '🎓', home: '🏠', around_home: '🚪' };
const DIRT_COLORS = { clean: '#10b981', light: '#f59e0b', dirty: '#ef4444' };
const DIRT_LABELS = { clean: '✨ Clean', light: '🟡 Light', dirty: '🔴 Dirty' };

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Set date label
  const d = new Date();
  document.getElementById('today-date-label').textContent =
    d.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' });

  // Load today's log first, then recommendations
  loadTodayState();

  // Outfits + items will load on tab switch
  document.getElementById('dirt-modal').addEventListener('click', e => { if (e.target === e.currentTarget) closeDirtModal(); });
  document.getElementById('vote-modal').addEventListener('click', e => { if (e.target === e.currentTarget) closeVoteModal(); });
  document.getElementById('slot-modal').addEventListener('click', e => { if (e.target === e.currentTarget) closeSlotModal(); });
  
  const customModal = document.getElementById('custom-outfit-modal');
  if (customModal) {
    customModal.addEventListener('click', e => { if (e.target === e.currentTarget) closeCustomOutfitModal(); });
  }
});

// ── Tabs ──────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
  document.getElementById(`tab-${tab}`).classList.add('active');
  const btn = document.getElementById(`tab-${tab}-btn`);
  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
  if (tab === 'outfits') fetchOutfits();
  if (tab === 'wardrobe') fetchItems();
  if (tab === 'history') fetchHistory();
}

// ═══════════════════════════════════════════════════════════════
// ── TODAY TAB ─────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════

async function loadTodayState() {
  const dateStr = today();
  try {
    // Load today's existing log
    const logRes = await fetch(`/api/days?date=${dateStr}`);
    const log = await logRes.json();
    todayLoggedSlots = {};
    (log.slots || []).forEach(s => { todayLoggedSlots[s.slot] = s; });
    if (log.day_type) {
      currentDayType = log.day_type;
      // Update pill UI
      document.querySelectorAll('.day-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.type === currentDayType);
      });
    }
  } catch(e) { /* no log yet */ }

  renderLoggedBar();
  await fetchTodayRecommendations();
}

function setDayType(type, btn) {
  currentDayType = type;
  document.querySelectorAll('.day-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  fetchTodayRecommendations();
}

async function fetchTodayRecommendations() {
  const container = document.getElementById('today-slots');
  container.innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>Finding best outfits for you…</div>`;

  try {
    const res = await fetch(`/api/today?day_type=${encodeURIComponent(currentDayType)}`);
    if (!res.ok) throw new Error('Failed');
    todayData = await res.json();
    
    // Auto-choose or restore selected outfits
    initSelections();
    
    renderTodaySlots();
  } catch(e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load recommendations.</p></div>`;
    console.error(e);
  }
}

// ── Selection & 1-Swap Logic ─────────────────────────────────

function getPairingItemIds(p) {
  if (!p) return new Set();
  if (p.item_ids) {
    return new Set(p.item_ids);
  }
  // Fallback for raw pairing structure
  const ids = new Set();
  const u = p.upper_half || {};
  const tl = u.topest_layer;
  if (tl) ids.add(tl);
  const ul = u.upper_layer;
  if (ul) ids.add(ul.id || ul);
  const ml = u.medium_layer;
  if (ml) ids.add(ml.id || ml);
  const bl = u.bottom_layer;
  if (bl) ids.add(bl);
  const bh = p.bottom_half;
  if (bh) ids.add(bh);
  const fw = p.footwear;
  if (fw) ids.add(fw);
  return ids;
}

function isOneSwapCompatible(pairingA, pairingB) {
  if (!pairingA || !pairingB) return false;
  const setA = getPairingItemIds(pairingA);
  const setB = getPairingItemIds(pairingB);
  
  let diffCount = 0;
  for (const id of setA) {
    if (!setB.has(id)) diffCount++;
  }
  for (const id of setB) {
    if (!setA.has(id)) diffCount++;
  }
  return diffCount <= 2;
}

function initSelections() {
  if (!todayData || !todayData.slots) return;
  
  // 1. Casual
  const casualLogged = !!todayLoggedSlots['casual'];
  const casualList = todayData.slots['casual'] || [];
  if (casualLogged) {
    selectedOutfits.casual = casualList.find(o => o.logged) || casualList[0] || null;
    explicitlySelected.casual = true;
  } else if (!explicitlySelected.casual || !casualList.some(o => o.pairing_id === selectedOutfits.casual?.pairing_id)) {
    selectedOutfits.casual = casualList[0] || null;
  }
  
  // 2. Home & Around Home
  const homeLogged = !!todayLoggedSlots['home'];
  const ahLogged = !!todayLoggedSlots['around_home'];
  const homeList = todayData.slots['home'] || [];
  const ahList = todayData.slots['around_home'] || [];
  
  if (homeLogged && ahLogged) {
    selectedOutfits.home = homeList.find(o => o.logged) || homeList[0] || null;
    explicitlySelected.home = true;
    selectedOutfits.around_home = ahList.find(o => o.logged) || ahList[0] || null;
    explicitlySelected.around_home = true;
  } else if (homeLogged) {
    selectedOutfits.home = homeList.find(o => o.logged) || homeList[0] || null;
    explicitlySelected.home = true;
    
    // Find top compatible around_home
    const currentAhCompatible = isOneSwapCompatible(selectedOutfits.home, selectedOutfits.around_home);
    if (!selectedOutfits.around_home || !currentAhCompatible || explicitlySelected.around_home) {
      const compatibleAh = ahList.filter(o => isOneSwapCompatible(selectedOutfits.home, o));
      selectedOutfits.around_home = compatibleAh[0] || ahList[0] || null;
      explicitlySelected.around_home = false;
    }
  } else if (ahLogged) {
    selectedOutfits.around_home = ahList.find(o => o.logged) || ahList[0] || null;
    explicitlySelected.around_home = true;
    
    // Find top compatible home
    const currentHomeCompatible = isOneSwapCompatible(selectedOutfits.around_home, selectedOutfits.home);
    if (!selectedOutfits.home || !currentHomeCompatible || explicitlySelected.home) {
      const compatibleHome = homeList.filter(o => isOneSwapCompatible(selectedOutfits.around_home, o));
      selectedOutfits.home = compatibleHome[0] || homeList[0] || null;
      explicitlySelected.home = false;
    }
  } else {
    // Neither is logged. Pre-select Home index 0, and filter AH based on it
    if (!explicitlySelected.home || !homeList.some(o => o.pairing_id === selectedOutfits.home?.pairing_id)) {
      selectedOutfits.home = homeList[0] || null;
    }
    
    // AH selection must follow home selection
    const currentAhCompatible = isOneSwapCompatible(selectedOutfits.home, selectedOutfits.around_home);
    if (!selectedOutfits.around_home || !currentAhCompatible || !explicitlySelected.around_home) {
      const compatibleAh = ahList.filter(o => isOneSwapCompatible(selectedOutfits.home, o));
      selectedOutfits.around_home = compatibleAh[0] || ahList[0] || null;
    }
  }
}

function selectOutfitForSlot(slot, pairingId) {
  const outfits = todayData.slots[slot] || [];
  const outfit = outfits.find(o => o.pairing_id === pairingId);
  if (!outfit) return;
  
  selectedOutfits[slot] = outfit;
  explicitlySelected[slot] = true;
  
  // Propagate 1-swap constraints
  if (slot === 'home') {
    const ahLogged = !!todayLoggedSlots['around_home'];
    if (!ahLogged) {
      const ahList = todayData.slots['around_home'] || [];
      const compatibleAh = ahList.filter(o => isOneSwapCompatible(outfit, o));
      // Auto-update selection if not compatible
      if (!selectedOutfits['around_home'] || !isOneSwapCompatible(outfit, selectedOutfits['around_home'])) {
        selectedOutfits['around_home'] = compatibleAh[0] || ahList[0] || null;
        explicitlySelected['around_home'] = false;
      }
    }
  } else if (slot === 'around_home') {
    const homeLogged = !!todayLoggedSlots['home'];
    if (!homeLogged) {
      const homeList = todayData.slots['home'] || [];
      const compatibleHome = homeList.filter(o => isOneSwapCompatible(outfit, o));
      // Auto-update selection if not compatible
      if (!selectedOutfits['home'] || !isOneSwapCompatible(outfit, selectedOutfits['home'])) {
        selectedOutfits['home'] = compatibleHome[0] || homeList[0] || null;
        explicitlySelected['home'] = false;
      }
    }
  }
  
  renderTodaySlots();
}

function renderTodaySlots() {
  const container = document.getElementById('today-slots');
  container.innerHTML = '';

  if (!todayData || !todayData.slots) return;

  const slotOrder = currentDayType === 'holiday'
    ? ['home', 'around_home']
    : ['casual', 'home', 'around_home'];

  slotOrder.forEach(slot => {
    const outfits = todayData.slots[slot] || [];
    const isLogged = !!todayLoggedSlots[slot];
    const selected = selectedOutfits[slot];

    const section = document.createElement('div');
    section.className = `slot-section${isLogged ? ' slot-logged' : ''}`;
    section.id = `slot-section-${slot}`;

    // Header buttons (Custom pair or Logged Badge)
    let headerRightHtml = '';
    if (slot === 'casual' && !isLogged) {
      headerRightHtml = `<button class="btn btn-primary btn-sm" onclick="openCustomOutfitModal()">✨ Custom Pair</button>`;
    } else if (isLogged) {
      headerRightHtml = `
        <div class="slot-logged-badge">
          <span>Logged</span>
          <span class="dirt-dot" style="background:${DIRT_COLORS[todayLoggedSlots[slot].dirt_level]}"></span>
          ${DIRT_LABELS[todayLoggedSlots[slot].dirt_level]}
          <button class="btn-icon-sm" onclick="removeSlotLog('${slot}')" title="Remove">✕</button>
        </div>
      `;
    }

    // Section header
    const header = document.createElement('div');
    header.className = 'slot-header';
    header.innerHTML = `
      <div class="slot-header-left">
        <span class="slot-icon-big">${SLOT_ICONS[slot]}</span>
        <div>
          <div class="slot-title">${SLOT_LABELS[slot]}</div>
          <div class="slot-subtitle">${outfits.length} option${outfits.length !== 1 ? 's' : ''} available</div>
        </div>
      </div>
      <div class="slot-header-right">${headerRightHtml}</div>
    `;
    section.appendChild(header);

    // Render outfits in a single scroll row
    if (selected) {
      const scrollRow = document.createElement('div');
      scrollRow.className = 'outfit-scroll-row';

      // 1. Selected Outfit Card
      const badgeText = isLogged ? 'Logged Outfit' : (explicitlySelected[slot] ? 'Selected' : 'Auto-Selected');
      const badgeClass = isLogged ? 'logged' : (explicitlySelected[slot] ? 'user' : 'auto');
      const selectedCard = buildTodayOutfitCard(selected, slot, false, badgeText, badgeClass);
      scrollRow.appendChild(selectedCard);

      // 2. Compatible Alternative Cards
      if (!isLogged && outfits.length > 1) {
        let alternatives = outfits;
        
        // Filter based on 1-swap rule
        if (slot === 'home' && selectedOutfits.around_home) {
          alternatives = outfits.filter(o => isOneSwapCompatible(selectedOutfits.around_home, o));
        } else if (slot === 'around_home' && selectedOutfits.home) {
          alternatives = outfits.filter(o => isOneSwapCompatible(selectedOutfits.home, o));
        }
        
        // Exclude currently selected
        alternatives = alternatives.filter(o => o.pairing_id !== selected?.pairing_id);

        alternatives.forEach(outfit => {
          const card = buildTodayOutfitCard(outfit, slot, false, '', '', true);
          scrollRow.appendChild(card);
        });
      }

      section.appendChild(scrollRow);
    } else {
      const empty = document.createElement('div');
      empty.className = 'slot-empty';
      empty.innerHTML = `<span>🧺</span> No outfit selected/available`;
      section.appendChild(empty);
    }

    container.appendChild(section);
  });
}

function buildTodayOutfitCard(outfit, slot, isTop, badgeText = '', badgeClass = '', isAlternative = false) {
  const card = document.createElement('div');
  const isLogged = outfit.logged;
  const isAuto = badgeClass === 'auto';
  const isUser = badgeClass === 'user';
  
  let cardClass = 'today-outfit-card';
  if (isTop) cardClass += ' top-pick';
  if (isLogged) cardClass += ' active-selection';
  else if (isUser) cardClass += ' active-selection';
  else if (isAuto) cardClass += ' auto-selection';
  
  card.className = cardClass;
  card.style.position = 'relative';

  const layerDefs = [
    { key: 'topest_layer', label: 'Outer', icon: '🧥' },
    { key: 'upper_layer',  label: 'Upper', icon: '👕' },
    { key: 'medium_layer', label: 'Top',   icon: '👔' },
    { key: 'bottom_layer', label: 'Inner', icon: '👘' },
    { key: 'bottom_half',  label: 'Pants', icon: '👖' },
    { key: 'footwear',     label: 'Shoes', icon: '👟' },
  ];

  const activeItems = layerDefs.filter(d => outfit[d.key]);
  const layersHtml = activeItems.map(def => {
    const item = outfit[def.key];
    const thumb = item.image_name
      ? `<img class="layer-thumb" src="/images/${item.image_name}" alt="${item.name}" loading="lazy">`
      : `<div class="layer-thumb-empty">${def.icon}</div>`;
    const styling = [item.tuck, item.sleeves].filter(Boolean).join(' · ');
    return `
      <div class="layer-row">
        ${thumb}
        <div class="layer-info">
          <div class="layer-role">${def.label}</div>
          <div class="layer-name">${item.name}</div>
          ${styling ? `<div class="layer-detail">${item.category} <span class="layer-styling">· ${styling}</span></div>` : `<div class="layer-detail">${item.category}</div>`}
        </div>
      </div>`;
  }).join('');

  // Dirt bars per item
  const dirtHtml = Object.entries(outfit.dirt_summary || {}).map(([iid, d]) => {
    const pct = Math.min(100, d.dirt_ratio * 100);
    const color = d.dirt_ratio >= 1 ? '#ef4444' : d.dirt_ratio >= 0.6 ? '#f59e0b' : '#10b981';
    const itemLabel = outfit.medium_layer?.id === iid ? outfit.medium_layer?.name :
                      outfit.bottom_half?.id === iid ? outfit.bottom_half?.name :
                      outfit.upper_layer?.id === iid ? outfit.upper_layer?.name :
                      outfit.bottom_layer?.id === iid ? outfit.bottom_layer?.name :
                      iid.replace('item_', '').replace(/_/g, ' ');
    return `<div class="dirt-bar-row" title="${d.wear_count}/${d.laundry_limit} wears">
      <span class="dirt-bar-label">${itemLabel}</span>
      <div class="dirt-bar-track"><div class="dirt-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="dirt-bar-pct" style="color:${color}">${d.wear_count}/${d.laundry_limit}</span>
    </div>`;
  }).join('');

  const scoreColor = outfit.score >= 10 ? '#10b981' : outfit.score >= 7 ? '#8b5cf6' : '#f59e0b';
  const daysAgo = outfit.days_since_worn;
  const recencyTxt = daysAgo === 9999 ? '✨ Never worn'
    : daysAgo === 0 ? '⚠️ Worn today'
    : daysAgo === 1 ? '📅 Yesterday'
    : `📅 ${daysAgo}d ago`;

  const outfitName = activeItems.map(d => outfit[d.key]?.name || '').filter(Boolean).join(' + ');

  let actionBtnHtml = '';
  if (isAlternative) {
    actionBtnHtml = `<button class="btn btn-ghost btn-sm" style="width:100%" onclick="selectOutfitForSlot('${slot}','${outfit.pairing_id}')">👉 Select Outfit</button>`;
  } else if (isLogged) {
    actionBtnHtml = `<button class="btn btn-wear" style="background:#555" onclick="openSlotModal('${slot}','${outfit.pairing_id}',${JSON.stringify(outfitName).replace(/"/g,'&quot;')}, true, '${outfit.dirt_level}')">🔄 Update Dirt</button>`;
  } else {
    actionBtnHtml = `<button class="btn btn-wear" onclick="openSlotModal('${slot}','${outfit.pairing_id}',${JSON.stringify(outfitName).replace(/"/g,'&quot;')})">✅ Wore This</button>`;
  }

  card.innerHTML = `
    ${badgeText ? `<div class="selection-badge ${badgeClass}">${badgeText}</div>` : ''}
    ${isTop ? '<div class="top-pick-badge">⭐ Best Pick</div>' : ''}
    <div class="card-score-row">
      <div class="score-pill" style="background:${scoreColor}20;color:${scoreColor}">
        ${outfit.score.toFixed(1)}
      </div>
      <span class="recency-chip">${recencyTxt}</span>
    </div>
    <div class="outfit-strip">${layersHtml}</div>
    ${dirtHtml ? `<div class="dirt-bars">${dirtHtml}</div>` : ''}
    <div class="card-actions">
      ${actionBtnHtml}
    </div>
  `;
  return card;
}

function renderLoggedBar() {
  const bar = document.getElementById('today-logged-bar');
  const row = document.getElementById('today-logged-slots');
  const count = Object.keys(todayLoggedSlots).length;
  if (count === 0) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = '';
  row.innerHTML = Object.entries(todayLoggedSlots).map(([slot, entry]) => `
    <div class="logged-chip">
      ${SLOT_ICONS[slot]}
      <span>${SLOT_LABELS[slot].replace(/[^\w ]/g,'').trim()}</span>
      <span class="dirt-dot" style="background:${DIRT_COLORS[entry.dirt_level]}"></span>
    </div>
  `).join('');
}

// ── Slot wear modal ───────────────────────────────────────────
let selectedSlotOptionValue = null;

function openSlotModal(slot, pairingId, pairingName, isUpdate = false, currentDirt = '') {
  const label = pairingName || pairingId;
  pendingSlotWear = { slot, pairing_id: pairingId, pairing_name: label, isUpdate };
  selectedSlotDirt = null;
  selectedSlotOptionValue = null;

  document.getElementById('slot-notes').value = '';
  document.querySelectorAll('#slot-dirt-options .dirt-btn').forEach(b => b.classList.remove('selected'));
  document.querySelectorAll('#slot-select-options .slot-select-btn').forEach(b => b.classList.remove('selected'));
  
  document.getElementById('slot-modal-pairing-name').textContent = label;
  
  if (isUpdate) {
    document.getElementById('slot-modal-title').textContent = `Update ${SLOT_LABELS[slot]}`;
    if (todayLoggedSlots[slot]) {
      document.getElementById('slot-notes').value = todayLoggedSlots[slot].notes || '';
    }
    if (currentDirt) {
      selectedSlotDirt = currentDirt;
      const b = document.querySelector(`#slot-dirt-options .dirt-btn[data-level="${currentDirt}"]`);
      if (b) b.classList.add('selected');
    }
    document.getElementById('slot-modal-select-section').style.display = 'none';
    document.getElementById('slot-confirm-btn').disabled = false;
  } else {
    document.getElementById('slot-modal-title').textContent = slot ? `Log ${SLOT_LABELS[slot]}` : 'Log Outfit for Today';
    document.getElementById('slot-confirm-btn').disabled = true;
    
    if (slot) {
      document.getElementById('slot-modal-select-section').style.display = 'none';
      pendingSlotWear.slot = slot;
    } else {
      document.getElementById('slot-modal-select-section').style.display = 'block';
    }
  }

  document.getElementById('slot-modal').classList.add('open');
}

function closeSlotModal() {
  document.getElementById('slot-modal').classList.remove('open');
  pendingSlotWear = null;
  selectedSlotDirt = null;
  selectedSlotOptionValue = null;
}

function selectSlotOption(btn) {
  document.querySelectorAll('#slot-select-options .slot-select-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedSlotOptionValue = btn.dataset.slot;
  if (pendingSlotWear) {
    pendingSlotWear.slot = selectedSlotOptionValue;
  }
  checkSlotConfirmState();
}

function selectSlotDirt(btn) {
  document.querySelectorAll('#slot-dirt-options .dirt-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedSlotDirt = btn.dataset.level;
  checkSlotConfirmState();
}

function checkSlotConfirmState() {
  const hasSlot = pendingSlotWear && pendingSlotWear.slot;
  const hasDirt = selectedSlotDirt;
  document.getElementById('slot-confirm-btn').disabled = !(hasSlot && hasDirt);
}

async function confirmSlotWear() {
  if (!pendingSlotWear || !pendingSlotWear.slot || !selectedSlotDirt) return;
  const btn = document.getElementById('slot-confirm-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  const notes = document.getElementById('slot-notes').value.trim();

  try {
    const res = await fetch('/api/days/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: today(),
        day_type: currentDayType,
        slot: pendingSlotWear.slot,
        pairing_id: pendingSlotWear.pairing_id,
        dirt_level: selectedSlotDirt,
        notes: notes,
      })
    });
    if (!res.ok) throw new Error(await res.text());

    todayLoggedSlots[pendingSlotWear.slot] = {
      slot: pendingSlotWear.slot,
      pairing_id: pendingSlotWear.pairing_id,
      dirt_level: selectedSlotDirt,
      notes: notes,
    };
    
    // reset explicitlySelected for this slot since it is now logged
    selectedOutfits[pendingSlotWear.slot] = null;
    
    renderLoggedBar();
    closeSlotModal();
    // Re-fetch recommendations to reflect new wear counts
    await fetchTodayRecommendations();

  } catch(e) {
    showToast('❌ Failed to log outfit.', true);
    console.error(e);
    btn.disabled = false; btn.textContent = '✅ Log Outfit';
  }
}

async function removeSlotLog(slot) {
  try {
    const res = await fetch(`/api/days/${today()}/slot/${slot}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    delete todayLoggedSlots[slot];
    renderLoggedBar();
    renderTodaySlots();
    showToast('✅ Slot log removed.');
  } catch(e) {
    showToast('❌ Failed to remove log.', true);
  }
}

// ═══════════════════════════════════════════════════════════════
// ── HISTORY TAB ───────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════

async function fetchHistory() {
  const days = document.getElementById('history-days-select').value;
  const list = document.getElementById('history-list');
  list.innerHTML = '<div class="loading-state">Loading history…</div>';

  try {
    const res = await fetch(`/api/days/history?days=${days}`);
    const logs = await res.json();
    renderHistory(logs);
  } catch(e) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load history.</p></div>`;
  }
}

const DAY_TYPE_ICONS = { college: '🎓', outing: '🛍️', trek: '🥾', holiday: '🏠' };

function renderHistory(logs) {
  const list = document.getElementById('history-list');
  if (!logs || logs.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">📅</div><p>No wear history yet. Start logging today!</p></div>`;
    return;
  }
  list.innerHTML = '';

  logs.forEach(log => {
    const item = document.createElement('div');
    item.className = 'history-day-card';
    const dateObj = new Date(log.date + 'T00:00:00');
    const isToday = log.date === today();
    const dayLabel = isToday ? 'Today'
      : dateObj.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

    const slotsHtml = (log.slots || []).map(s => `
      <div class="history-slot">
        <div class="history-slot-label">${SLOT_ICONS[s.slot] || '👕'} ${SLOT_LABELS[s.slot] || s.slot}</div>
        <div class="history-slot-name">${s.pairing_name || s.pairing_id}</div>
        <div class="history-slot-dirt" style="color:${DIRT_COLORS[s.dirt_level] || '#888'}">
          ${DIRT_LABELS[s.dirt_level] || s.dirt_level}
        </div>
      </div>
    `).join('');

    item.innerHTML = `
      <div class="history-day-header">
        <div class="history-date">
          <span class="history-date-big">${isToday ? '📍 Today' : dayLabel}</span>
          <span class="history-date-sub">${log.date}</span>
        </div>
        <div class="history-day-type">
          ${DAY_TYPE_ICONS[log.day_type] || '📅'} ${log.day_type || '—'}
        </div>
      </div>
      ${slotsHtml ? `<div class="history-slots-grid">${slotsHtml}</div>`
        : `<div class="history-empty-day">Nothing logged</div>`}
    `;
    list.appendChild(item);
  });
}

// ═══════════════════════════════════════════════════════════════
// ── OUTFITS TAB (legacy full-wardrobe view) ────────────────────
// ═══════════════════════════════════════════════════════════════

async function fetchOutfits() {
  const dest = document.getElementById('destination-select').value;
  const grid = document.getElementById('outfits-grid');
  grid.innerHTML = '';

  try {
    const res = await fetch(`/api/outfits?destination=${encodeURIComponent(dest)}`);
    if (!res.ok) throw new Error('Failed to fetch');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let count = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        renderSingleOutfit(JSON.parse(line), dest);
        count++;
      }
    }
    if (buffer.trim()) { renderSingleOutfit(JSON.parse(buffer), dest); count++; }
    if (count === 0) {
      grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🧺</div><p>No clean outfits for <strong>${dest}</strong>.</p></div>`;
    }
  } catch(e) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load outfits.</p></div>`;
    console.error(e);
  }
}

function renderSingleOutfit(outfit, dest) {
  const grid = document.getElementById('outfits-grid');
  const layerDefs = [
    { key: 'topest_layer', label: 'Outer', icon: '🧥' },
    { key: 'upper_layer',  label: 'Upper', icon: '👕' },
    { key: 'medium_layer', label: 'Mid',   icon: '👔' },
    { key: 'bottom_layer', label: 'Bottom',icon: '👘' },
    { key: 'bottom_half',  label: 'Pants', icon: '👖' },
    { key: 'footwear',     label: 'Shoes', icon: '👟' },
  ];

  const card = document.createElement('div');
  card.className = 'card';

  const destScore  = outfit.dest_score ?? outfit.score;
  const scorePct   = Math.min(100, (destScore / 10) * 100);
  const scoreColor = destScore >= 8 ? '#10b981' : destScore >= 5 ? '#8b5cf6' : '#f59e0b';
  const lastWornTxt = outfit.last_worn
    ? `<span class="last-worn-chip">📅 ${outfit.last_worn}</span>`
    : `<span class="last-worn-chip" style="color:#10b981;">✨ Never worn</span>`;

  const layersHtml = layerDefs.map(def => {
    const item = outfit[def.key];
    if (!item) return '';
    const styling = [item.tuck, item.sleeves].filter(Boolean).join(' · ');
    const thumb = item.image_name
      ? `<img class="layer-thumb" src="/images/${item.image_name}" alt="${item.name}" loading="lazy">`
      : `<div class="layer-thumb-empty">${def.icon}</div>`;
    return `<div class="layer-row">
      ${thumb}
      <div class="layer-info">
        <div class="layer-role">${def.label}</div>
        <div class="layer-name">${item.name}</div>
        <div class="layer-detail">${item.category}${styling ? ` <span class="layer-styling">· ${styling}</span>` : ''}</div>
      </div>
    </div>`;
  }).join('');

  const votes      = outfit.friend_votes || [];
  const lovedCount = votes.filter(v => v.vote === 'loved').length;
  const likedCount = votes.filter(v => v.vote === 'liked').length;
  const voteSummary = votes.length > 0
    ? `<span class="vote-count">❤️ ${lovedCount} 👍 ${likedCount} · ${votes.length} total</span>` : '';

  const destSlotMap = { 'Casual': 'casual', 'Home': 'home', 'around home': 'around_home' };
  const initialSlot = destSlotMap[dest] || '';
  const outfitName = layerDefs.map(d => outfit[d.key]?.name || '').filter(Boolean).join(' + ');

  card.innerHTML = `
    <div class="outfit-header">
      <div class="score-row" style="flex:1;min-width:0" title="Score for ${dest}">
        <span class="score-label">${dest.split(' ')[0]}</span>
        <div class="score-bar-wrap"><div class="score-bar-fill" style="width:${scorePct}%;background:linear-gradient(90deg,${scoreColor},${scoreColor}99)"></div></div>
        <span class="score-num">${destScore}</span>
      </div>
      ${lastWornTxt}
    </div>
    <div class="outfit-strip">${layersHtml}</div>
    ${voteSummary ? `<div style="padding:0 0.25rem">${voteSummary}</div>` : ''}
    <div class="card-actions">
      <button class="btn btn-wear" onclick="openSlotModal('${initialSlot}','${outfit.pairing_id}',${JSON.stringify(outfitName).replace(/"/g,'&quot;')})">👕 Wore Today</button>
      <button class="btn btn-vote" onclick="openVoteModal('${outfit.pairing_id}',${JSON.stringify(layerDefs.filter(d=>outfit[d.key]).map(d=>({id:outfit[d.key].id??outfit[d.key].layer_id,name:outfit[d.key].name,label:d.label}))).replace(/"/g,'&quot;')})">👥 Vote</button>
    </div>
  `;
  grid.appendChild(card);
}

// ═══════════════════════════════════════════════════════════════
// ── WARDROBE TAB ──────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════

async function fetchItems() {
  try {
    const res = await fetch('/api/items');
    allItems = await res.json();
    renderItems(allItems, activeFilter);
  } catch(e) {
    document.getElementById('items-grid').innerHTML =
      `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load wardrobe.</p></div>`;
  }
}

function filterItems(status, btn) {
  activeFilter = status;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderItems(allItems, status);
}

function renderItems(items, filter) {
  const grid = document.getElementById('items-grid');
  grid.innerHTML = '';
  const filtered = filter === 'all' ? items : items.filter(i => i.status === filter);
  if (filtered.length === 0) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🧺</div><p>No items found.</p></div>`;
    return;
  }

  filtered.forEach(item => {
    const card = document.createElement('div');
    card.className = 'card';
    const statusClass = `status-${(item.status || 'clean').toLowerCase()}`;
    const limit = item.laundry_limit ?? 3;
    const wears = item.wear_count ?? 0;
    const pips  = Array.from({ length: Math.max(limit, wears) }, (_, i) =>
      `<div class="pip${i < wears ? ' used' : ''}"></div>`).join('');

    const votes = item.friend_votes || [];
    const voteSummary = votes.length > 0
      ? `<span class="vote-count">❤️ ${votes.filter(v=>v.vote==='loved').length} 👍 ${votes.filter(v=>v.vote==='liked').length} · ${votes.length}</span>` : '';

    const comfortBadge = item.comfort
      ? `<span class="badge badge-comfort" style="background:${item.comfort==='High'?'#10b98122':'#8b5cf622'};color:${item.comfort==='High'?'#10b981':'#8b5cf6'}">${item.comfort === 'High' ? '😌' : '👔'} ${item.comfort}</span>` : '';

    const agingBadge = item.aging_factor && item.aging_factor > 1.1
      ? `<span class="badge badge-aging" title="Ages faster">⚡ ×${item.aging_factor}</span>` : '';

    card.innerHTML = `
      ${item.image_name
        ? `<img class="item-img" src="/images/${item.image_name}" alt="${item.name}" loading="lazy">`
        : `<div class="no-img">👕</div>`}
      <div class="card-title">${item.name}</div>
      <div class="card-meta">
        <span class="badge">${item.category}</span>
        <span class="badge" style="background:${item.color_hex}25;color:${item.color_hex}">${item.color_name}</span>
        <span class="badge ${statusClass}">${item.status || 'Clean'}</span>
        ${comfortBadge}${agingBadge}${voteSummary}
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap">
        <div class="wear-pips" title="${wears}/${limit} wears before wash">${pips}</div>
        <span style="font-size:0.73rem;color:var(--text-muted)">${wears}/${limit} wears</span>
        ${item.last_worn ? `<span class="last-worn-chip">· Last: ${item.last_worn}</span>` : ''}
      </div>
      <div class="card-actions">
        <button class="btn btn-wear" onclick="openSlotModal('casual','${item.id}', '${item.name.replace(/'/g, "\\'")}')">👕 Wear</button>
        <button class="btn btn-wash" onclick="washItem('${item.id}')">🧺 Washed</button>
      </div>
    `;
    grid.appendChild(card);
  });
}

// ── Dirtiness Modal (legacy Outfits tab) ──────────────────────
function openDirtModal(type, id, dest) {
  pendingWear = { type, id, dest: dest || 'Casual' };
  selectedDirtLevel = null;
  document.querySelectorAll('#dirt-options .dirt-btn').forEach(b => b.classList.remove('selected'));
  document.getElementById('dirt-confirm-btn').disabled = true;
  document.getElementById('dirt-modal').classList.add('open');
}
function closeDirtModal() {
  document.getElementById('dirt-modal').classList.remove('open');
  pendingWear = null; selectedDirtLevel = null;
}
function selectDirt(btn) {
  document.querySelectorAll('#dirt-options .dirt-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedDirtLevel = btn.dataset.level;
  document.getElementById('dirt-confirm-btn').disabled = false;
}
async function confirmWear() {
  if (!pendingWear || !selectedDirtLevel) return;
  const confirmBtn = document.getElementById('dirt-confirm-btn');
  confirmBtn.disabled = true; confirmBtn.textContent = 'Saving…';
  try {
    const endpoint = pendingWear.type === 'outfit'
      ? `/api/pairings/${pendingWear.id}/wear`
      : `/api/items/${pendingWear.id}/wear`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        destination: pendingWear.dest, date: today(),
        force_status: selectedDirtLevel === 'dirty' ? 'Dirty' : null,
        dirt_level: selectedDirtLevel,
      })
    });
    if (!res.ok) throw new Error(await res.text());
    showToast(selectedDirtLevel === 'dirty' ? '✅ Logged! Item(s) marked for wash.'
      : selectedDirtLevel === 'light' ? '✅ Logged! Still wearable.' : '✅ Logged! Still clean.');
    closeDirtModal();
    await Promise.all([fetchOutfits(), fetchItems()]);
  } catch(e) {
    showToast('❌ Failed to log wear.', true);
    console.error(e);
    confirmBtn.disabled = false; confirmBtn.textContent = 'Confirm';
  }
}

// ── Wash ──────────────────────────────────────────────────────
async function washItem(itemId) {
  try {
    const res = await fetch(`/api/items/${itemId}/wash`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'Clean' })
    });
    if (!res.ok) throw new Error(await res.text());
    showToast('✅ Marked clean!');
    await fetchItems();
  } catch(e) { showToast('❌ Failed.', true); }
}

// ── Friend Vote Modal ─────────────────────────────────────────
function openVoteModal(pairingId, layers) {
  pendingVote = { pairingId, layers };
  selectedVoteValue = null;
  document.querySelectorAll('.vote-opt').forEach(b => b.classList.remove('selected'));
  document.getElementById('vote-friend-name').value = '';
  document.getElementById('vote-note').value = '';
  document.getElementById('vote-confirm-btn').disabled = true;
  const sel = document.getElementById('item-vote-select');
  sel.innerHTML = '<option value="">Whole outfit</option>';
  if (layers && Array.isArray(layers)) {
    layers.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l.id || '';
      opt.textContent = `${l.label}: ${l.name}`;
      sel.appendChild(opt);
    });
  }
  document.getElementById('vote-modal').classList.add('open');
}
function closeVoteModal() {
  document.getElementById('vote-modal').classList.remove('open');
  pendingVote = null; selectedVoteValue = null;
}
function selectVote(btn) {
  document.querySelectorAll('.vote-opt').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedVoteValue = btn.dataset.vote;
  document.getElementById('vote-confirm-btn').disabled = false;
}
async function confirmVote() {
  if (!pendingVote || !selectedVoteValue) return;
  const confirmBtn = document.getElementById('vote-confirm-btn');
  confirmBtn.disabled = true; confirmBtn.textContent = 'Saving…';
  const friendName = document.getElementById('vote-friend-name').value.trim();
  const note       = document.getElementById('vote-note').value.trim();
  const itemId     = document.getElementById('item-vote-select').value;
  const votePayload = { friend: friendName || 'Anonymous', vote: selectedVoteValue, note: note||null, date: today(), item_id: itemId||null };
  try {
    const res = await fetch(`/api/pairings/${pendingVote.pairingId}/vote`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(votePayload)
    });
    if (!res.ok) throw new Error(await res.text());
    if (itemId) {
      await fetch(`/api/items/${itemId}/vote`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(votePayload)
      });
    }
    showToast(`✅ ${friendName || 'Vote'} recorded!`);
    closeVoteModal();
    await Promise.all([fetchOutfits(), fetchItems()]);
  } catch(e) {
    showToast('❌ Failed to save vote.', true);
    console.error(e);
    confirmBtn.disabled = false; confirmBtn.textContent = 'Save Vote';
  }
}

// ── Custom Outfit Creator Modal ──────────────────────────────
async function openCustomOutfitModal() {
  try {
    const res = await fetch('/api/items');
    allItems = await res.json();
  } catch(e) {
    showToast('❌ Failed to load wardrobe items.', true);
    return;
  }
  
  populateCustomOutfitDropdowns();
  
  document.getElementById('custom-outer').value = '';
  document.getElementById('custom-upper').value = '';
  document.getElementById('custom-mid').value = '';
  document.getElementById('custom-inner').value = '';
  document.getElementById('custom-bottom').value = '';
  document.getElementById('custom-footwear').value = '';
  
  document.getElementById('custom-upper-style-row').style.display = 'none';
  document.getElementById('custom-mid-style-row').style.display = 'none';
  
  updateCustomPreview();
  document.getElementById('custom-outfit-modal').classList.add('open');
}

function closeCustomOutfitModal() {
  document.getElementById('custom-outfit-modal').classList.remove('open');
}

function populateCustomOutfitDropdowns() {
  const outerSelect = document.getElementById('custom-outer');
  const upperSelect = document.getElementById('custom-upper');
  const midSelect = document.getElementById('custom-mid');
  const innerSelect = document.getElementById('custom-inner');
  const bottomSelect = document.getElementById('custom-bottom');
  const footwearSelect = document.getElementById('custom-footwear');

  // Reset dropdowns
  outerSelect.innerHTML = '<option value="">(None)</option>';
  upperSelect.innerHTML = '<option value="">(None)</option>';
  midSelect.innerHTML = '<option value="">(None)</option>';
  innerSelect.innerHTML = '<option value="">(None)</option>';
  bottomSelect.innerHTML = '<option value="">Select bottom half...</option>';
  footwearSelect.innerHTML = '<option value="">(None / Barefoot)</option>';

  const cleanItems = allItems.filter(i => i.status === 'Clean');

  cleanItems.forEach(item => {
    const cat = item.category;
    const opt = `<option value="${item.id}">${item.name} (${item.color_name})</option>`;

    // Outer Categories
    if (['Jacket', 'Blazer', 'Coat', 'Sweater', 'Hoodie', 'Vest'].includes(cat)) {
      outerSelect.insertAdjacentHTML('beforeend', opt);
    }
    // Upper Categories
    if (['Button-down', 'Polo', 'Sweater', 'Hoodie', 'Shirt', 'Dress Shirt', 'Tank Top'].includes(cat)) {
      upperSelect.insertAdjacentHTML('beforeend', opt);
    }
    // Mid Categories
    if (['T-Shirt', 'Button-down', 'Polo', 'Shirt', 'Tank Top', 'Dress Shirt'].includes(cat)) {
      midSelect.insertAdjacentHTML('beforeend', opt);
    }
    // Inner Categories
    if (['T-Shirt', 'Tank Top', 'Underwear'].includes(cat)) {
      innerSelect.insertAdjacentHTML('beforeend', opt);
    }
    // Bottom Categories
    if (['Jeans', 'Chinos', 'Trousers', 'Shorts', 'Sweatpants', 'Cargo Pants', 'Pants'].includes(cat)) {
      bottomSelect.insertAdjacentHTML('beforeend', opt);
    }
    // Footwear Categories
    if (['Sneakers', 'Formal Shoes', 'Boots', 'Sandals', 'Loafers'].includes(cat)) {
      footwearSelect.insertAdjacentHTML('beforeend', opt);
    }
  });
}

function onCustomUpperChange() {
  const val = document.getElementById('custom-upper').value;
  const row = document.getElementById('custom-upper-style-row');
  if (val) {
    const item = allItems.find(i => i.id === val);
    const cat = item ? item.category : '';
    if (['Button-down', 'Polo', 'Shirt', 'Dress Shirt'].includes(cat)) {
      row.style.display = 'flex';
    } else {
      row.style.display = 'none';
    }
  } else {
    row.style.display = 'none';
  }
  updateCustomPreview();
}

function onCustomMidChange() {
  const val = document.getElementById('custom-mid').value;
  const row = document.getElementById('custom-mid-style-row');
  if (val) {
    const item = allItems.find(i => i.id === val);
    const cat = item ? item.category : '';
    if (['Button-down', 'Polo', 'Shirt', 'Dress Shirt'].includes(cat)) {
      row.style.display = 'flex';
    } else {
      row.style.display = 'none';
    }
  } else {
    row.style.display = 'none';
  }
  updateCustomPreview();
}

function updateCustomPreview() {
  const outer = document.getElementById('custom-outer').value;
  const upper = document.getElementById('custom-upper').value;
  const mid = document.getElementById('custom-mid').value;
  const inner = document.getElementById('custom-inner').value;
  const bottom = document.getElementById('custom-bottom').value;
  const footwear = document.getElementById('custom-footwear').value;

  const previewStrip = document.getElementById('custom-outfit-preview-strip');
  previewStrip.innerHTML = '';

  const layers = [
    { id: outer, label: 'Outer', icon: '🧥' },
    { id: upper, label: 'Upper', icon: '👕', tuck: document.getElementById('custom-upper-tuck').value, sleeves: document.getElementById('custom-upper-sleeves').value, styleRow: 'custom-upper-style-row' },
    { id: mid, label: 'Top', icon: '👔', tuck: document.getElementById('custom-mid-tuck').value, sleeves: document.getElementById('custom-mid-sleeves').value, styleRow: 'custom-mid-style-row' },
    { id: inner, label: 'Inner', icon: '👘' },
    { id: bottom, label: 'Pants', icon: '👖' },
    { id: footwear, label: 'Shoes', icon: '👟' }
  ];

  let selectedCount = 0;
  layers.forEach(lay => {
    if (!lay.id) return;
    selectedCount++;
    const item = allItems.find(i => i.id === lay.id);
    if (!item) return;

    const thumb = item.image_name
      ? `<img class="layer-thumb" src="/images/${item.image_name}" alt="${item.name}">`
      : `<div class="layer-thumb-empty">${lay.icon}</div>`;

    const isStyleVisible = lay.styleRow && document.getElementById(lay.styleRow).style.display !== 'none';
    const styling = isStyleVisible ? [lay.tuck, lay.sleeves].filter(Boolean).join(' · ') : '';

    const rowHtml = `
      <div class="layer-row">
        ${thumb}
        <div class="layer-info">
          <div class="layer-role">${lay.label}</div>
          <div class="layer-name">${item.name}</div>
          <div class="layer-detail">${item.category}${styling ? ` <span class="layer-styling">· ${styling}</span>` : ''}</div>
        </div>
      </div>
    `;
    previewStrip.insertAdjacentHTML('beforeend', rowHtml);
  });

  if (selectedCount === 0) {
    previewStrip.innerHTML = '<div class="empty-state" style="padding:0.5rem 0; font-size:0.85rem; color:var(--text-muted);">No items selected yet.</div>';
  }

  // Validation
  const hasBottom = !!bottom;
  const hasUpper = !!(outer || upper || mid || inner);
  document.getElementById('custom-save-btn').disabled = !(hasBottom && hasUpper);
}

async function saveCustomOutfit() {
  const outer = document.getElementById('custom-outer').value;
  const upper = document.getElementById('custom-upper').value;
  const mid = document.getElementById('custom-mid').value;
  const inner = document.getElementById('custom-inner').value;
  const bottom = document.getElementById('custom-bottom').value;
  const footwear = document.getElementById('custom-footwear').value;

  const upper_layer_style = document.getElementById('custom-upper-style-row').style.display !== 'none';
  const mid_layer_style = document.getElementById('custom-mid-style-row').style.display !== 'none';

  const payload = {
    upper_half: {
      topest_layer: outer || null,
      upper_layer: upper ? {
        id: upper,
        tuck: upper_layer_style ? document.getElementById('custom-upper-tuck').value : 'untucked',
        sleeves: upper_layer_style ? document.getElementById('custom-upper-sleeves').value : 'down'
      } : null,
      medium_layer: mid ? {
        id: mid,
        tuck: mid_layer_style ? document.getElementById('custom-mid-tuck').value : 'untucked',
        sleeves: mid_layer_style ? document.getElementById('custom-mid-sleeves').value : 'down'
      } : null,
      bottom_layer: inner || null
    },
    bottom_half: bottom,
    footwear: footwear || null
  };

  const btn = document.getElementById('custom-save-btn');
  btn.disabled = true; btn.textContent = 'Scoring…';

  try {
    const res = await fetch('/api/pairings/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (!res.ok) {
      throw new Error(await res.text());
    }

    const pairing = await res.json();
    closeCustomOutfitModal();
    showToast('✨ Custom pairing scored and saved!');

    // Add to recommendations on today tab
    if (typeof todayData !== 'undefined' && todayData && todayData.slots && todayData.slots.casual) {
      // Resolve pairing details to look like API candidate
      const itemsMap = {};
      allItems.forEach(i => { itemsMap[i.id] = i; });
      
      const resolveItem = (layData) => {
        if (!layData) return null;
        if (typeof layData === 'string') return itemsMap[layData] ? { ...itemsMap[layData], layer_id: layData } : null;
        if (typeof layData === 'object') return itemsMap[layData.id] ? { ...itemsMap[layData.id], tuck: layData.tuck, sleeves: layData.sleeves } : null;
        return null;
      };

      const dirt_summary = {};
      const activeIds = [];
      const keys = [outer, upper, mid, inner, bottom, footwear];
      keys.forEach(k => {
        if (!k) return;
        const iid = typeof k === 'string' ? k : k.id;
        activeIds.push(iid);
        const item = itemsMap[iid];
        if (item) {
          dirt_summary[iid] = {
            wear_count: item.wear_count || 0,
            laundry_limit: item.laundry_limit || 3,
            dirt_ratio: (item.wear_count || 0) / (item.laundry_limit || 3),
            status: item.status || 'Clean'
          };
        }
      });

      const resolvedPairing = {
        pairing_id: pairing.id,
        score: pairing.scores.Casual || 6,
        dest_score: pairing.scores.Casual || 6,
        scores: pairing.scores,
        last_worn: null,
        days_since_worn: 9999,
        topest_layer: resolveItem(pairing.upper_half.topest_layer),
        upper_layer: resolveItem(pairing.upper_half.upper_layer),
        medium_layer: resolveItem(pairing.upper_half.medium_layer),
        bottom_layer: resolveItem(pairing.upper_half.bottom_layer),
        bottom_half: resolveItem(pairing.bottom_half),
        footwear: resolveItem(pairing.footwear),
        item_ids: activeIds,
        dirt_summary: dirt_summary
      };

      // Add to today's options list
      todayData.slots.casual.unshift(resolvedPairing);
      // Auto-select
      selectOutfitForSlot('casual', pairing.id);
      
      // Auto-open log modal for this custom pairing so they can immediately wear it
      const outfitName = activeIds.map(iid => itemsMap[iid]?.name || '').filter(Boolean).join(' + ');
      openSlotModal('casual', pairing.id, outfitName);
    }
  } catch(e) {
    showToast('❌ Validator Rejected: ' + e.message, true);
    console.error(e);
    btn.disabled = false; btn.textContent = '✨ Score & Wear Outfit';
  }
}

// ── Helpers ───────────────────────────────────────────────────
function today() { return new Date().toISOString().slice(0, 10); }

let toastTimer = null;
function showToast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = isError ? 'rgba(239,68,68,0.5)' : 'rgba(139,92,246,0.45)';
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
}
