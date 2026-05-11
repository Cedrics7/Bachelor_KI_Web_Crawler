const API_BASE = "http://localhost:8000/api";
const pageSize = 50;
let monitoringInterval = null;

const globalDataCache = {
  bestandsdaten: [],
  bewegungsdaten: []
};

const stateKeys = ["search", "id", "status", "bl", "kat", "sort", "p"];

window.addEventListener("hashchange", router);
window.addEventListener("load", async () => {
  initTheme();
  setupSearchListeners();

  if (!window.location.hash) {
    window.location.hash = "#bestandsdaten";
    return;
  }

  await router();
});

function getUrlState() {
  const hash = window.location.hash || "#bestandsdaten";
  const [pagePart, queryPart = ""] = hash.split("?");
  const params = new URLSearchParams(queryPart);

  return {
    page: pagePart.replace("#", ""),
    search: params.get("q")?.trim() || "",
    id: params.get("id") || null,
    status: params.get("status") || "Alle",
    bl: params.get("bl") || "Alle",
    kat: params.get("kat") || "Alle",
    sort: params.get("sort") || "desc",
    p: Math.max(parseInt(params.get("p"), 10) || 1, 1)
  };
}

function updateUrl(page = null, patch = {}) {
  const current = getUrlState();
  const nextPage = page || current.page;
  const next = { ...current, ...patch };

  if (page && page !== current.page) next.p = 1;

  const params = new URLSearchParams();
  if (next.search) params.set("q", next.search);
  if (next.id) params.set("id", next.id);
  if (next.p > 1) params.set("p", String(next.p));
  if (next.status && next.status !== "Alle") params.set("status", next.status);
  if (next.bl && next.bl !== "Alle") params.set("bl", next.bl);
  if (next.kat && next.kat !== "Alle") params.set("kat", next.kat);
  if (next.sort && next.sort !== "desc") params.set("sort", next.sort);

  const newHash = params.toString() ? `#${nextPage}?${params.toString()}` : `#${nextPage}`;
  if (window.location.hash !== newHash) window.location.hash = newHash;
}

function setupSearchListeners() {
  const onSearch = (event) => {
    const el = event.target;
    if (!["filter-bestandsdaten-suche", "filter-beweg-suche"].includes(el.id)) return;

    const value = (event.detail?.value ?? el.value ?? "").trim();
    updateUrl(null, { search: value, p: 1 });
  };

  document.addEventListener("scale-input", onSearch);
  document.addEventListener("input", onSearch);
}

async function router() {
  const state = getUrlState();

  document.querySelectorAll(".page-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".nav-link").forEach(el => el.classList.remove("active"));

  document.getElementById(`page-${state.page}`)?.classList.remove("hidden");
  document.getElementById(`nav-${state.page}`)?.classList.add("active");

  loadStats();

  if (state.page === "monitoring") {
    loadMonitoring();
    if (!monitoringInterval) monitoringInterval = setInterval(loadMonitoring, 5000);
  } else {
    if (monitoringInterval) {
      clearInterval(monitoringInterval);
      monitoringInterval = null;
    }

    if (state.page === "bestandsdaten") await loadBestandsdaten(state);
    if (state.page === "bewegungsdaten") await loadBewegungsdaten(state);
  }

  const modal = document.getElementById("detail-modal");
  if (state.id) {
    showDetailModal(state.id, state.page);
  } else if (modal) {
    modal.opened = false;
  }

  syncSearchInput(state);
}

function syncSearchInput(state) {
  const activeSearchId = state.page === "bestandsdaten"
    ? "filter-bestandsdaten-suche"
    : "filter-beweg-suche";

  const searchInput = document.getElementById(activeSearchId);
  if (!searchInput) return;

  const value = state.search || "";
  if (searchInput.value !== value) {
    searchInput.value = value;
  }
}

async function fetchDataset(endpoint, params = {}) {
  const query = new URLSearchParams(params);
  const res = await fetch(`${API_BASE}/${endpoint}?${query}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function loadBestandsdaten(state) {
  try {
    const data = await fetchDataset("bestandsdaten", {
      page: state.p,
      page_size: pageSize,
      search: state.search,
      status: state.status
    });

    globalDataCache.bestandsdaten = data.items;
    renderBestandsTable(data.items);
    renderPagination("pagination-controls", data.total_pages, state.p);
    setApiStatus(true);
  } catch {
    setApiStatus(false);
  }
}

function renderBestandsTable(data) {
    const tbody = document.getElementById('table-bestandsdaten');
    const mode = document.body.getAttribute('data-mode') || 'light';
    if (!tbody) return;

    tbody.innerHTML = data.map(row => `
        <tr class="border-b hover:bg-magenta/5 cursor-pointer" onclick="updateUrl(null, {id: '${row.id}'})">
            <td class="p-4 opacity-40">${row.id}</td>
            <td class="p-4 font-bold">${row.ort}</td>
            <td class="p-4 font-mono">${row.ags}</td>
            <td class="p-4">${row.bundesland}</td>
            <td class="p-4 text-xs">${row.last_scanned}</td>
            <td class="p-4" onclick="event.stopPropagation()">
                <scale-button variant="ghost" size="small" href="${row.url}" target="_blank" mode="${mode}">
                    <scale-icon-navigation-external-link accessibility-title="Link öffnen" mode="${mode}"></scale-icon-navigation-external-link>
                </scale-button>
            </td>
        </tr>
    `).join('');
}

async function loadBewegungsdaten(state) {
  try {
    const data = await fetchDataset("bewegungsdaten", {
      page: state.p,
      page_size: pageSize,
      search: state.search,
      bundesland: state.bl,
      kategorie: state.kat,
      sort: state.sort
    });

    const items = Array.isArray(data.items) ? data.items : [];
    globalDataCache.bewegungsdaten = items;

    if (data.filter_options) updateBewegDropdowns(data.filter_options);
    renderBewegTable(items);
    renderPagination("pagination-controls-beweg", data.total_pages || 1, state.p);
    setApiStatus(true);
  } catch (err) {
    console.error("loadBewegungsdaten failed:", err);
    setApiStatus(false);
  }
}

function renderBewegTable(items) {
    const tbody = document.getElementById('table-bewegungsdaten');
    const mode = document.body.getAttribute('data-mode') || 'light';
    if (!tbody) return;

    tbody.innerHTML = items.map(row => `
        <tr class="border-b hover:bg-magenta/5 cursor-pointer" onclick="updateUrl(null, {id: '${row.massnahme || row.id}'})">
            <td class="p-3">
                <scale-tag variant="brand" mode="${mode}">${row.kategorie || 'BAU'}</scale-tag><br>
                <strong>${row.massnahme}</strong>
            </td>
            <td><strong>${row.ort || 'Unbekannt'}</strong><br><span class="text-xs opacity-70">${row.bundesland || ''}</span></td>
            <td>${row.adresse || '-'}</td>
            <td class="text-xs">Start: ${row.massnahme_start || '-'}<br>Ende: ${row.massnahme_ende || '-'}</td>
            <td class="text-xs opacity-50">${row.gefunden_am}</td>
            <td class="p-4" onclick="event.stopPropagation()">
                <scale-button variant="ghost" size="small" href="${row.massnahme_url}" target="_blank" mode="${mode}">
                    <scale-icon-navigation-external-link accessibility-title="Quelle öffnen" mode="${mode}"></scale-icon-navigation-external-link>
                </scale-button>
            </td>
        </tr>
    `).join('');
}

function showDetailModal(id, page) {
    const modal = document.getElementById('detail-modal');
    const content = document.getElementById('modal-content');
    const dataset = page === 'bestandsdaten' ? globalDataCache.bestandsdaten : globalDataCache.bewegungsdaten;
    const item = dataset.find(d => (d.id || d.massnahme || d.ags || '').toString() === id.toString());
    const mode = document.body.getAttribute('data-mode') || 'light';

    if (modal) {
        modal.setAttribute('mode', mode);
        modal.mode = mode;
    }

    if (item) {
        const bgClass = mode === 'dark' ? 'bg-zinc-900' : 'bg-zinc-50';
        const borderClass = mode === 'dark' ? 'border-zinc-800' : 'border-zinc-200';
        const textClass = mode === 'dark' ? 'text-white' : 'text-black';

        content.innerHTML = `<div class="p-4 grid grid-cols-1 gap-2 ${bgClass} ${textClass} rounded">
            ${Object.entries(item).map(([key, val]) => `
                <div class="flex border-b ${borderClass} py-2">
                    <span class="w-1/3 text-[10px] font-bold text-[#E20074] uppercase">${key.replace(/_/g, ' ')}</span>
                    <span class="w-2/3 text-sm break-words">${val || '-'}</span>
                </div>
            `).join('')}
        </div>`;
        modal.opened = true;
    }
}

function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    applyTheme(savedTheme === 'dark');
}

function applyTheme(isDark) {
    const modeStr = isDark ? 'dark' : 'light';
    localStorage.setItem('theme', modeStr);
    document.body.classList.toggle('dark-mode', isDark);
    document.body.setAttribute('data-mode', modeStr);
    document.querySelectorAll('[class*="hydrated"], scale-text-field, scale-button, scale-table, scale-card, scale-tag, scale-icon-action-light-dark-mode, scale-logo, scale-modal').forEach(el => {
        if (el.tagName.toLowerCase().startsWith('scale-')) {
            el.setAttribute('mode', modeStr);
            if ('mode' in el) el.mode = modeStr;
        }
    });
}

function toggleTheme() {
    applyTheme(!document.body.classList.contains('dark-mode'));
}

function setApiStatus(isOnline) {
    const dot = document.getElementById('api-status-dot');
    const label = document.getElementById('api-status-label');
    if (dot && label) {
        dot.className = isOnline ? "status-dot dot-online" : "status-dot dot-offline";
        label.innerText = isOnline ? "API LIVE" : "API OFFLINE";
    }
}

async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        const data = await res.json();
        document.getElementById('kpi-total').innerText = data.total;
        document.getElementById('kpi-done').innerText = data.done;
        document.getElementById('kpi-pending').innerText = data.pending;
    } catch (e) {}
}

function renderPagination(containerId, totalPages, current) {
    const navContainer = document.getElementById(containerId);
    if (!navContainer) return;
    navContainer.innerHTML = `
        <scale-button variant="secondary" size="small" ${current <= 1 ? 'disabled' : ''} onclick="updateUrl(null, { p: ${current - 1} })">Zurück</scale-button>
        <span class="text-xs font-bold px-4">Seite ${current} von ${totalPages || 1}</span>
        <scale-button variant="secondary" size="small" ${current >= totalPages ? 'disabled' : ''} onclick="updateUrl(null, { p: ${current + 1} })">Weiter</scale-button>
    `;
}

function updateBewegDropdowns(options) {
    const blSelect = document.getElementById('filter-beweg-bl');
    const katSelect = document.getElementById('filter-beweg-kat');
    if (blSelect && blSelect.options.length <= 1) {
        blSelect.innerHTML = '<option value="Alle">Bundesland: Alle</option>' + options.bundeslaender.map(b => `<option value="${b}">${b}</option>`).join('');
    }
    if (katSelect && katSelect.options.length <= 1) {
        katSelect.innerHTML = '<option value="Alle">Kategorie: Alle</option>' + options.kategorien.map(k => `<option value="${k}">${k}</option>`).join('');
    }
}

async function loadMonitoring() {
    try {
        const res = await fetch(`${API_BASE}/monitoring`);
        const data = await res.json();
        document.getElementById('live-ort').innerText = data.live.aktueller_ort || 'Standby';
        document.getElementById('live-funde').innerText = data.live.letzte_funde || '0';
        document.getElementById('live-status').innerText = data.live.status || 'Warte...';
        document.getElementById('live-time').innerText = "Stand: " + new Date().toLocaleTimeString('de-DE');
        document.getElementById('monitoring-log').innerText = data.history || 'Keine Logs vorhanden.';
        setApiStatus(true);
    } catch (e) { setApiStatus(false); }
}

setTimeout(() => {
    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.addEventListener('scale-close', () => updateUrl(null, { id: null }));
    }
}, 500);