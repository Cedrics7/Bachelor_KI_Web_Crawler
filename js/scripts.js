/**
 * KONFIGURATION & INITIALISIERUNG
 */
const API_BASE = "http://localhost:8000/api";
const pageSize = 50;
let currentPage = 1;
let currentBewegPage = 1;
let monitoringInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    setupEventListeners();
    switchPage('bestandsdaten');
});

function setupEventListeners() {
    // Bestandsdaten Filter
    const searchInput = document.getElementById('filter-bestandsdaten-suche');
    if (searchInput) searchInput.addEventListener('scale-change', () => loadBestandsdaten(1));
    
    const statusSelect = document.getElementById('filter-bestandsdaten-status');
    if (statusSelect) statusSelect.addEventListener('change', () => loadBestandsdaten(1));

    // Bewegungsdaten Filter
    const bewegSearch = document.getElementById('filter-beweg-suche');
    if (bewegSearch) bewegSearch.addEventListener('scale-change', () => loadBewegungsdaten(1));

    const bewegBL = document.getElementById('filter-beweg-bl');
    if (bewegBL) bewegBL.addEventListener('change', () => loadBewegungsdaten(1));

    const bewegKat = document.getElementById('filter-beweg-kat');
    if (bewegKat) bewegKat.addEventListener('change', () => loadBewegungsdaten(1));

    const bewegDatum = document.getElementById('filter-beweg-datum');
    if (bewegDatum) bewegDatum.addEventListener('scale-change', () => loadBewegungsdaten(1));
}

/**
 * THEME MANAGEMENT
 */
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = savedTheme === 'dark' || (!savedTheme && systemPrefersDark);
    applyTheme(isDark);
}

function toggleTheme() {
    const isDark = !document.body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    applyTheme(isDark);
}

function applyTheme(isDark) {
    const modeStr = isDark ? 'dark' : 'light';
    document.body.classList.toggle('dark-mode', isDark);
    document.body.setAttribute('data-mode', modeStr);

    const scaleElements = document.querySelectorAll('[class*="hydrated"], scale-text-field, scale-button, scale-table, scale-card, scale-tag, scale-icon-action-light-dark-mode, scale-logo');
    scaleElements.forEach(el => {
        if (el.tagName.toLowerCase().startsWith('scale-')) {
            el.setAttribute('mode', modeStr);
            if ('mode' in el) el.mode = modeStr;
        }
    });
}

/**
 * NAVIGATION & CORE API
 */
async function switchPage(pageId) {
    document.querySelectorAll('.page-content').forEach(p => p.classList.add('hidden'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    
    const targetPage = document.getElementById('page-' + pageId);
    const targetNav = document.getElementById('nav-' + pageId);
    
    if (targetPage) targetPage.classList.remove('hidden');
    if (targetNav) targetNav.classList.add('active');

    loadStats();
    
    if (pageId === 'monitoring') {
        loadMonitoring();
        if (!monitoringInterval) monitoringInterval = setInterval(loadMonitoring, 5000);
    } else {
        clearInterval(monitoringInterval);
        monitoringInterval = null;
        if (pageId === 'bestandsdaten') await loadBestandsdaten();
        if (pageId === 'bewegungsdaten') await loadBewegungsdaten();
    }
}

async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        const data = await res.json();
        document.getElementById('kpi-total').innerText = data.total;
        document.getElementById('kpi-done').innerText = data.done;
        document.getElementById('kpi-pending').innerText = data.pending;
        setApiStatus(true);
    } catch (e) { setApiStatus(false); }
}

function setApiStatus(isOnline) {
    const dot = document.getElementById('api-status-dot');
    const label = document.getElementById('api-status-label');
    if (!dot || !label) return;
    dot.className = isOnline ? "status-dot dot-online" : "status-dot dot-offline";
    label.innerText = isOnline ? "API LIVE" : "API OFFLINE";
}

/**
 * BESTANDSDATEN (TARGETS)
 */
async function loadBestandsdaten(page = 1) {
    currentPage = page;
    const searchVal = document.getElementById('filter-bestandsdaten-suche').value || "";


    try {
        const url = `${API_BASE}/bestandsdaten?page=${page}&page_size=${pageSize}&search=${encodeURIComponent(searchVal)}`;
        const res = await fetch(url);
        const data = await res.json();

        renderBestandsTable(data.items);
        renderPagination('pagination-controls', data.total_pages, data.page, 'loadBestandsdaten');
        setApiStatus(true);
    } catch (e) { setApiStatus(false); }
}

function renderBestandsTable(items) {
    const tbody = document.getElementById('table-bestandsdaten');
    tbody.innerHTML = items.map(row => `
        <tr>
            <td>${row.id}</td>
            <td><strong>${row.ort || '-'}</strong></td>
            <td>${row.ags || '-'}</td>
            <td>${row.bundesland || '-'}</td>
            <td>${row.last_scanned || 'Nie'}</td>
            <td>
                <scale-button variant="secondary" size="small" href="${row.url || '#'}" target="_blank">Öffnen</scale-button>
            </td>
        </tr>
    `).join('');
}

/**
 * BEWEGUNGSDATEN (RESULTS)
 */
async function loadBewegungsdaten(page = 1) {
    currentBewegPage = page;
    const searchVal = document.getElementById('filter-beweg-suche').value || "";
    const blVal = document.getElementById('filter-beweg-bl').value || "Alle";
    const katVal = document.getElementById('filter-beweg-kat').value || "Alle";
    const sortVal = document.getElementById('filter-beweg-sort').value || "desc";

    try {
        const params = new URLSearchParams({
            page: page,
            page_size: pageSize,
            search: searchVal,
            bundesland: blVal,
            kategorie: katVal,
            sort: sortVal
        });

        const res = await fetch(`${API_BASE}/bewegungsdaten?${params}`);
        const data = await res.json();

        if (data.filter_options) updateBewegDropdowns(data.filter_options);

            renderBewegTable(data.items);
            renderPagination('pagination-controls-beweg', data.total_pages, data.page, 'loadBewegungsdaten');
            setApiStatus(true);
        } catch (e) {
            console.error(e);
            setApiStatus(false);
        }
}
function renderBewegTable(items) {
    const mode = document.body.getAttribute('data-mode') || 'light';
    const tbody = document.getElementById('table-bewegungsdaten');

    tbody.innerHTML = items.map(row => {

        return `
        <tr>
            <td class="p-3">
                <scale-tag mode="${mode}" variant="brand">${row.kategorie || 'BAU'}</scale-tag>
                <br><strong>${row.massnahme}</strong>
            </td>
            <td><strong>${row.ort || 'Unbekannt'}</strong><br><span class="text-xs opacity-70">${row.bundesland || ''}</span></td>
            <td><strong>${row.adresse || '-'}</strong></td>
            <td>
                <span class="text-xs">Start: ${row.massnahme_start || '-'}</span><br>
                <span class="text-xs">Ende: ${row.massnahme_ende || '-'}</span>
            </td>
            <td><span class="font-mono text-xs">${row.gefunden_am}</span></td>
            <td>
                <scale-button mode="${mode}" variant="secondary" size="small" href="${row.massnahme_url || '#'}" target="_blank">
                    Quelle
                </scale-button>
            </td>
        </tr>`;
    }).join('');
}

function updateBewegDropdowns(options) {
    const blSelect = document.getElementById('filter-beweg-bl');
    const katSelect = document.getElementById('filter-beweg-kat');
    
    if (blSelect && blSelect.options.length <= 1) {
        blSelect.innerHTML = '<option value="Alle">Bundesland: Alle</option>' +
            options.bundeslaender.map(b => `<option value="${b}">${b}</option>`).join('');
    }
    if (katSelect && katSelect.options.length <= 1) {
        katSelect.innerHTML = '<option value="Alle">Kategorie: Alle</option>' +
            options.kategorien.map(k => `<option value="${k}">${k}</option>`).join('');
    }
}

/**
 * UTILS (Pagination & Monitoring)
 */
function renderPagination(containerId, totalPages, current, funcName) {
    const navContainer = document.getElementById(containerId);
    if (!navContainer) return;
    
    navContainer.innerHTML = `
        <scale-button variant="secondary" size="small" ${current <= 1 ? 'disabled' : ''} 
            onclick="${funcName}(${current - 1})">Zurück</scale-button>
        <span class="text-xs font-bold">Seite ${current} von ${totalPages || 1}</span>
        <scale-button variant="secondary" size="small" ${current >= totalPages ? 'disabled' : ''} 
            onclick="${funcName}(${current + 1})">Weiter</scale-button>
    `;
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