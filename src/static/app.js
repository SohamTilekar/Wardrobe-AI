/* ============================================================
   WARDROBE AI — app.js v6
   ============================================================ */

let allItems = [];
let activeFilter = "all";

// ── Pending action state ─────────────────────────────────────
let pendingWear = null; // { type: 'outfit'|'item', id, dest? }
let pendingVote = null; // { pairingId, layers }
let selectedDirtLevel = null;
let selectedVoteValue  = null;

// ── Init ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    fetchOutfits();
    fetchItems();
    // Close modals on overlay click
    document.getElementById("dirt-modal").addEventListener("click", e => {
        if (e.target === e.currentTarget) closeDirtModal();
    });
    document.getElementById("vote-modal").addEventListener("click", e => {
        if (e.target === e.currentTarget) closeVoteModal();
    });
});

// ── Tabs ────────────────────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
    });
    document.getElementById(`tab-${tab}`).classList.add("active");
    const btn = document.getElementById(`tab-${tab}-btn`);
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
}

// ── Outfits ──────────────────────────────────────────────────
async function fetchOutfits() {
    const dest = document.getElementById("destination-select").value;
    const grid = document.getElementById("outfits-grid");
    grid.innerHTML = `<div class="loading-state">Loading outfits…</div>`;
    try {
        const res = await fetch(`/api/outfits?destination=${encodeURIComponent(dest)}`);
        const outfits = await res.json();
        renderOutfits(outfits, dest);
    } catch (e) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load outfits.</p></div>`;
        console.error(e);
    }
}

function renderOutfits(outfits, dest) {
    const grid = document.getElementById("outfits-grid");
    grid.innerHTML = "";

    if (outfits.length === 0) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🧺</div><p>No clean outfits for <strong>${dest}</strong>.</p></div>`;
        return;
    }

    const layerDefs = [
        { key: "topest_layer",  label: "Outer",  icon: "🧥" },
        { key: "upper_layer",   label: "Upper",  icon: "👕" },
        { key: "medium_layer",  label: "Mid",    icon: "👔" },
        { key: "bottom_layer",  label: "Bottom", icon: "👘" },
        { key: "bottom_half",   label: "Pants",  icon: "👖" },
        { key: "footwear",      label: "Shoes",  icon: "👟" },
    ];

    outfits.forEach(outfit => {
        const card = document.createElement("div");
        card.className = "card";

        const destScore = outfit.dest_score ?? outfit.score;
        const scoreBarPct = Math.min(100, (destScore / 10) * 100);
        const scoreColor = destScore >= 8 ? "#10b981" : destScore >= 5 ? "#8b5cf6" : "#f59e0b";
        const lastWornTxt = outfit.last_worn
            ? `<span class="last-worn-chip">📅 ${outfit.last_worn}</span>`
            : `<span class="last-worn-chip" style="color:#10b981;">✨ Never worn</span>`;

        // Compact layer strip
        const layersHtml = layerDefs.map(def => {
            const item = outfit[def.key];
            if (!item) return "";
            const styling = [item.tuck, item.sleeves].filter(Boolean).join(" · ");
            const thumb = item.image_name
                ? `<img class="layer-thumb" src="/images/${item.image_name}" alt="${item.name}" loading="lazy">`
                : `<div class="layer-thumb-empty">${def.icon}</div>`;
            return `
            <div class="layer-row">
                ${thumb}
                <div class="layer-info">
                    <div class="layer-role">${def.label}</div>
                    <div class="layer-name">${item.name}</div>
                    <div class="layer-detail">${item.category}${styling ? ` <span class="layer-styling">· ${styling}</span>` : ""}</div>
                </div>
            </div>`;
        }).join("");

        // Friend votes summary
        const votes = outfit.friend_votes || [];
        const lovedCount = votes.filter(v => v.vote === "loved").length;
        const likedCount = votes.filter(v => v.vote === "liked").length;
        const voteSummary = votes.length > 0
            ? `<span class="vote-count">❤️ ${lovedCount} 👍 ${likedCount} · ${votes.length} total</span>`
            : "";

        card.innerHTML = `
            <div class="outfit-header">
                <div class="score-row" style="flex:1; min-width:0;" title="Score for ${dest}">
                    <span class="score-label">${dest.split(" ")[0]}</span>
                    <div class="score-bar-wrap">
                        <div class="score-bar-fill" style="width:${scoreBarPct}%; background:linear-gradient(90deg,${scoreColor},${scoreColor}99);"></div>
                    </div>
                    <span class="score-num">${destScore}</span>
                </div>
                ${lastWornTxt}
            </div>
            <div class="outfit-strip">${layersHtml}</div>
            ${voteSummary ? `<div style="padding:0 0.25rem;">${voteSummary}</div>` : ""}
            <div class="card-actions">
                <button class="btn btn-wear" onclick="openDirtModal('outfit','${outfit.pairing_id}','${dest}')">
                    👕 Wore Today
                </button>
                <button class="btn btn-vote" onclick="openVoteModal('${outfit.pairing_id}', ${JSON.stringify(layerDefs.filter(d => outfit[d.key]).map(d => ({id: outfit[d.key].id ?? outfit[d.key].layer_id, name: outfit[d.key].name, label: d.label}))).replace(/"/g, '&quot;')})">
                    👥 Vote
                </button>
            </div>
        `;
        grid.appendChild(card);
    });
}

// ── Items ────────────────────────────────────────────────────
async function fetchItems() {
    try {
        const res = await fetch("/api/items");
        allItems = await res.json();
        renderItems(allItems, activeFilter);
    } catch (e) {
        document.getElementById("items-grid").innerHTML =
            `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load wardrobe.</p></div>`;
        console.error(e);
    }
}

function filterItems(status, btn) {
    activeFilter = status;
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderItems(allItems, status);
}

function renderItems(items, filter) {
    const grid = document.getElementById("items-grid");
    grid.innerHTML = "";

    const filtered = filter === "all" ? items : items.filter(i => i.status === filter);
    if (filtered.length === 0) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🧺</div><p>No items found.</p></div>`;
        return;
    }

    filtered.forEach(item => {
        const card = document.createElement("div");
        card.className = "card";

        const statusClass = `status-${(item.status || "clean").toLowerCase()}`;
        const limit = item.laundry_limit ?? 3;
        const wears = item.wear_count ?? 0;
        const pips = Array.from({ length: Math.max(limit, wears) }, (_, i) =>
            `<div class="pip${i < wears ? " used" : ""}"></div>`
        ).join("");

        // Friend votes for item
        const votes = item.friend_votes || [];
        const voteSummary = votes.length > 0
            ? `<span class="vote-count">❤️ ${votes.filter(v=>v.vote==="loved").length} 👍 ${votes.filter(v=>v.vote==="liked").length} · ${votes.length}</span>`
            : "";

        card.innerHTML = `
            ${item.image_name
                ? `<img class="item-img" src="/images/${item.image_name}" alt="${item.name}" loading="lazy">`
                : `<div class="no-img">👕</div>`}
            <div class="card-title">${item.name}</div>
            <div class="card-meta">
                <span class="badge">${item.category}</span>
                <span class="badge" style="background:${item.color_hex}25; color:${item.color_hex};">${item.color_name}</span>
                <span class="badge ${statusClass}">${item.status || "Clean"}</span>
                ${voteSummary}
            </div>
            <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                <div class="wear-pips" title="${wears} / ${limit} wears before wash">${pips}</div>
                <span style="font-size:0.73rem; color:var(--text-muted);">${wears}/${limit} wears</span>
                ${item.last_worn ? `<span class="last-worn-chip">· Last: ${item.last_worn}</span>` : ""}
            </div>
            <div class="card-actions">
                <button class="btn btn-wear" onclick="openDirtModal('item','${item.id}')">
                    👕 Wear
                </button>
                <button class="btn btn-wash" onclick="washItem('${item.id}')">
                    🧺 Washed
                </button>
            </div>
        `;
        grid.appendChild(card);
    });
}

// ── Dirtiness Modal ──────────────────────────────────────────
function openDirtModal(type, id, dest) {
    pendingWear = { type, id, dest: dest || "Casual" };
    selectedDirtLevel = null;

    // Reset selections
    document.querySelectorAll(".dirt-btn").forEach(b => b.classList.remove("selected"));
    document.getElementById("dirt-confirm-btn").disabled = true;
    document.getElementById("dirt-modal").classList.add("open");
}

function closeDirtModal() {
    document.getElementById("dirt-modal").classList.remove("open");
    pendingWear = null;
    selectedDirtLevel = null;
}

function selectDirt(btn) {
    document.querySelectorAll(".dirt-btn").forEach(b => b.classList.remove("selected"));
    btn.classList.add("selected");
    selectedDirtLevel = btn.dataset.level;
    document.getElementById("dirt-confirm-btn").disabled = false;
}

async function confirmWear() {
    if (!pendingWear || !selectedDirtLevel) return;

    const confirmBtn = document.getElementById("dirt-confirm-btn");
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Saving…";

    // Map level → status
    const statusMap = { clean: "Clean", light: "Clean", dirty: "Dirty" };
    const newStatus = statusMap[selectedDirtLevel];
    // Extra wear increment regardless (we always log the wear)
    const forceStatus = selectedDirtLevel === "dirty";

    try {
        if (pendingWear.type === "outfit") {
            const res = await fetch(`/api/pairings/${pendingWear.id}/wear`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    destination: pendingWear.dest,
                    date: today(),
                    force_status: forceStatus ? "Dirty" : null,
                    dirt_level: selectedDirtLevel
                })
            });
            if (!res.ok) throw new Error(await res.text());
        } else {
            const res = await fetch(`/api/items/${pendingWear.id}/wear`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    date: today(),
                    destination: pendingWear.dest,
                    force_status: forceStatus ? "Dirty" : null,
                    dirt_level: selectedDirtLevel
                })
            });
            if (!res.ok) throw new Error(await res.text());
        }

        showToast(selectedDirtLevel === "dirty"
            ? "✅ Logged! Item(s) marked for wash."
            : selectedDirtLevel === "light"
            ? "✅ Logged! Still wearable."
            : "✅ Logged! Still clean.");

        closeDirtModal();
        await Promise.all([fetchOutfits(), fetchItems()]);
    } catch (e) {
        showToast("❌ Failed to log wear.", true);
        console.error(e);
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Confirm";
    }
}

// ── Wash item ────────────────────────────────────────────────
async function washItem(itemId) {
    try {
        const res = await fetch(`/api/items/${itemId}/wash`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "Clean" })
        });
        if (!res.ok) throw new Error(await res.text());
        showToast("✅ Marked clean!");
        await fetchItems();
    } catch (e) {
        showToast("❌ Failed.", true);
        console.error(e);
    }
}

// ── Friend Vote Modal ────────────────────────────────────────
function openVoteModal(pairingId, layers) {
    pendingVote = { pairingId, layers };
    selectedVoteValue = null;

    document.querySelectorAll(".vote-opt").forEach(b => b.classList.remove("selected"));
    document.getElementById("vote-friend-name").value = "";
    document.getElementById("vote-note").value = "";
    document.getElementById("vote-confirm-btn").disabled = true;

    // Populate item dropdown
    const sel = document.getElementById("item-vote-select");
    sel.innerHTML = `<option value="">Whole outfit</option>`;
    if (layers && Array.isArray(layers)) {
        layers.forEach(l => {
            const opt = document.createElement("option");
            opt.value = l.id || "";
            opt.textContent = `${l.label}: ${l.name}`;
            sel.appendChild(opt);
        });
    }

    document.getElementById("vote-modal").classList.add("open");
}

function closeVoteModal() {
    document.getElementById("vote-modal").classList.remove("open");
    pendingVote = null;
    selectedVoteValue = null;
}

function selectVote(btn) {
    document.querySelectorAll(".vote-opt").forEach(b => b.classList.remove("selected"));
    btn.classList.add("selected");
    selectedVoteValue = btn.dataset.vote;
    document.getElementById("vote-confirm-btn").disabled = false;
}

async function confirmVote() {
    if (!pendingVote || !selectedVoteValue) return;

    const confirmBtn = document.getElementById("vote-confirm-btn");
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Saving…";

    const friendName = document.getElementById("vote-friend-name").value.trim();
    const note = document.getElementById("vote-note").value.trim();
    const itemId = document.getElementById("item-vote-select").value;

    const votePayload = {
        friend: friendName || "Anonymous",
        vote: selectedVoteValue,
        note: note || null,
        date: today(),
        item_id: itemId || null
    };

    try {
        // Always vote on pairing
        const res = await fetch(`/api/pairings/${pendingVote.pairingId}/vote`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(votePayload)
        });
        if (!res.ok) throw new Error(await res.text());

        // Also vote on specific item if chosen
        if (itemId) {
            await fetch(`/api/items/${itemId}/vote`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(votePayload)
            });
        }

        showToast(`✅ ${friendName || "Vote"} recorded!`);
        closeVoteModal();
        await Promise.all([fetchOutfits(), fetchItems()]);
    } catch (e) {
        showToast("❌ Failed to save vote.", true);
        console.error(e);
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Save Vote";
    }
}

// ── Helpers ──────────────────────────────────────────────────
function today() {
    return new Date().toISOString().slice(0, 10);
}

let toastTimer = null;
function showToast(msg, isError = false) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.style.borderColor = isError ? "rgba(239,68,68,0.5)" : "rgba(139,92,246,0.45)";
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}
