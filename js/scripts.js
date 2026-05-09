document.addEventListener("DOMContentLoaded", () => {
        const searchInput = document.getElementById('filter-bestandsdaten-suche');
        if(searchInput) searchInput.addEventListener('scale-change', filterBestandsdaten);

        const bewegSearch = document.getElementById('filter-beweg-suche');
        if(bewegSearch) bewegSearch.addEventListener('scale-change', filterBewegungsdaten);

        const bewegDatum = document.getElementById('filter-beweg-datum');
        if(bewegDatum) bewegDatum.addEventListener('scale-change', filterBewegungsdaten);
    });

    function initTheme() {
        const savedTheme = localStorage.getItem('theme');
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isDark = savedTheme === 'dark' || (!savedTheme && systemPrefersDark);

        applyTheme(isDark);
    }

    function toggleTheme() {
        const isCurrentlyDark = document.body.classList.contains('dark-mode');
        const isDark = !isCurrentlyDark;

        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        applyTheme(isDark);
    }

function applyTheme(isDark) {
    const modeStr = isDark ? 'dark' : 'light';

    if (isDark) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }

    document.body.setAttribute('data-mode', modeStr);

    // Diese Logik deckt bereits ALLES ab, auch das Icon,
    // da das Icon eine Scale-Komponente ist!
    const scaleElements = document.querySelectorAll('[class*="hydrated"], scale-text-field, scale-button, scale-table, scale-card, scale-tag, scale-icon-action-light-dark-mode, scale-logo');

    scaleElements.forEach(el => {
        if (el.tagName.toLowerCase().startsWith('scale-')) {
            el.setAttribute('mode', modeStr);
            if ('mode' in el) {
                el.mode = modeStr;
            }
        }
    });

    // ENTFERNT: Die manuelle Zuweisung von themeIcon.innerHTML
    // Das Icon aktualisiert sich oben in der Schleife von selbst!
}

    initTheme();

    function setApiStatus(isOnline) {
        const dot = document.getElementById('api-status-dot');
        const label = document.getElementById('api-status-label');
        if (isOnline) {
            dot.className = "status-dot dot-online";
            label.innerText = "API LIVE";
        } else {
            dot.className = "status-dot dot-offline";
            label.innerText = "API OFFLINE";
        }
    }

    const API_BASE = "http://localhost:8000/api";
    let rawBestandsdaten = [];
    let rawBewegungsdaten = [];
    let monitoringInterval = null;

    async function switchPage(pageId) {
        document.querySelectorAll('.page-content').forEach(p => p.classList.add('hidden'));
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.getElementById('page-' + pageId).classList.remove('hidden');
        document.getElementById('nav-' + pageId).classList.add('active');

        loadStats();
        if (pageId === 'monitoring') {
            loadMonitoring();
            if(!monitoringInterval) monitoringInterval = setInterval(loadMonitoring, 5000);
        } else {
            clearInterval(monitoringInterval); monitoringInterval = null;
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

    let currentPage = 1;
const pageSize = 50;

async function loadBestandsdaten(page = 1) {
    currentPage = page;
    const searchVal = document.getElementById('filter-bestandsdaten-suche').value || "";

    try {
        const url = `${API_BASE}/bestandsdaten?page=${page}&page_size=${pageSize}&search=${encodeURIComponent(searchVal)}`;
        const res = await fetch(url);
        const data = await res.json();

        renderBestandsTable(data.items);
        renderPagination(data.total_pages, data.page);
        setApiStatus(true);
    } catch (e) {
        console.error(e);
        setApiStatus(false);
    }
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
                <scale-button variant="secondary" size="small" href="${row.url || '#'}" target="_blank">
                    Öffnen
                </scale-button>
            </td>
        </tr>
    `).join('');
}

function renderPagination(totalPages, current) {
    const navContainer = document.getElementById('pagination-controls');
    navContainer.innerHTML = `
        <scale-button variant="secondary" size="small" ${current <= 1 ? 'disabled' : ''}
            onclick="loadBestandsdaten(${current - 1})">Zurück</scale-button>

        <span class="text-xs font-bold">Seite ${current} von ${totalPages}</span>

        <scale-button variant="secondary" size="small" ${current >= totalPages ? 'disabled' : ''}
            onclick="loadBestandsdaten(${current + 1})">Weiter</scale-button>
    `;
}

// Suche-Event-Listener anpassen
document.getElementById('filter-bestandsdaten-suche').addEventListener('scale-change', (e) => {
    loadBestandsdaten(1); // Bei neuer Suche zurück auf Seite 1
});

    function filterBestandsdaten() {
        const searchElement = document.getElementById('filter-bestandsdaten-suche');
        const suche = (searchElement.value || "").toLowerCase();
        const status = document.getElementById('filter-bestandsdaten-status').value;
        const monatStart = new Date(); monatStart.setDate(1); monatStart.setHours(0,0,0,0);

        const filtered = rawBestandsdaten.filter(d => {
            const matchesSuche = (d.ort || "").toLowerCase().includes(suche) || (d.ags || "").includes(suche);
            let istGecrawlt = false;
            if(d.last_scanned && d.last_scanned !== "-") {
                const parts = d.last_scanned.split('.');
                const dObj = new Date(parts[2].split(' ')[0], parts[1]-1, parts[0]);
                istGecrawlt = dObj >= monatStart;
            }
            return status === "Gecrawlt" ? (matchesSuche && istGecrawlt) : (status === "Ausstehend" ? (matchesSuche && !istGecrawlt) : matchesSuche);
        });
        const tbody = document.getElementById('table-bestandsdaten');
        tbody.innerHTML = filtered.map(row => `
            <tr>
                <td>${row.id}</td>
                <td><strong>${row.ort || '-'}</strong></td>
                <td>${row.ags || '-'}</td>
                <td>${row.bundesland || '-'}</td>
                <td>${row.last_scanned || 'Nie'}</td>
                <td>
                    <scale-button variant="secondary" size="small" href="${row.url || '#'}" target="_blank">
                        Öffnen
                    </scale-button>
                </td>
            </tr>
        `).join('');
    }

let currentBewegPage = 1;

async function loadBewegungsdaten(page = 1) {
    currentBewegPage = page;
    const searchVal = document.getElementById('filter-beweg-suche').value || "";
    const blVal = document.getElementById('filter-beweg-bl').value || "Alle";
    const katVal = document.getElementById('filter-beweg-kat').value || "Alle";

    try {
        const params = new URLSearchParams({
            page: page,
            page_size: pageSize,
            search: searchVal,
            bundesland: blVal,
            kategorie: katVal
        });

        const res = await fetch(`${API_BASE}/bewegungsdaten?${params}`);
        const data = await res.json();

        // Dropdowns aktualisieren (nur wenn Optionen mitgeliefert wurden)
        if (data.filter_options) updateBewegDropdowns(data.filter_options);

        renderBewegTable(data.items);
        renderBewegPagination(data.total_pages, data.page);
        setApiStatus(true);
    } catch (e) {
        console.error(e);
        setApiStatus(false);
    }
}

function updateBewegDropdowns(options) {
    const blSelect = document.getElementById('filter-beweg-bl');
    const katSelect = document.getElementById('filter-beweg-kat');

    const prevBl = blSelect.value;
    const prevKat = katSelect.value;

    if (blSelect.options.length <= 1) { // Nur füllen wenn leer (außer "Alle")
        blSelect.innerHTML = '<option value="Alle">Bundesland: Alle</option>' +
            options.bundeslaender.map(b => `<option value="${b}">${b}</option>`).join('');
        blSelect.value = prevBl;
    }

    if (katSelect.options.length <= 1) {
        katSelect.innerHTML = '<option value="Alle">Kategorie: Alle</option>' +
            options.kategorien.map(k => `<option value="${k}">${k}</option>`).join('');
        katSelect.value = prevKat;
    }
}

function renderBewegTable(items) {
    const isDark = document.body.classList.contains('dark-mode');
    const currentMode = isDark ? 'dark' : 'light';
    const tbody = document.getElementById('table-bewegungsdaten');

    tbody.innerHTML = items.map(row => `
        <tr>
            <td>
                <scale-tag mode="${currentMode}" variant="brand">${row.kategorie || 'BAU'}</scale-tag>
                <br><strong>${row.massnahme}</strong>
            </td>
            <td><strong>${row.ort || 'Unbekannt'}</strong><br>${row.bundesland || ''}</td>
            <td>Start: ${row.massnahme_start || '-'}<br>Ende: ${row.massnahme_ende || '-'}</td>
            <td>
                <scale-button mode="${currentMode}" variant="secondary" size="small" href="${row.massnahme_url || '#'}" target="_blank">
                    Quelle
                </scale-button>
            </td>
        </tr>
    `).join('');
}

function renderBewegPagination(totalPages, current) {
    const navContainer = document.getElementById('pagination-controls-beweg');
    navContainer.innerHTML = `
        <scale-button variant="secondary" size="small" ${current <= 1 ? 'disabled' : ''} onclick="loadBewegungsdaten(${current - 1})">Zurück</scale-button>
        <span class="text-xs font-bold">Seite ${current} von ${totalPages}</span>
        <scale-button variant="secondary" size="small" ${current >= totalPages ? 'disabled' : ''} onclick="loadBewegungsdaten(${current + 1})">Weiter</scale-button>
    `;
}

// Event-Listener für Filter
document.getElementById('filter-beweg-suche').addEventListener('scale-change', () => loadBewegungsdaten(1));
document.getElementById('filter-beweg-bl').addEventListener('change', () => loadBewegungsdaten(1));
document.getElementById('filter-beweg-kat').addEventListener('change', () => loadBewegungsdaten(1));

    function filterBewegungsdaten() {
        const suche = (document.getElementById('filter-beweg-suche').value || "").toLowerCase();
        const bl = document.getElementById('filter-beweg-bl').value;
        const kat = document.getElementById('filter-beweg-kat').value;
        const datum = document.getElementById('filter-beweg-datum').value;

        const filtered = rawBewegungsdaten.filter(d => {
            const matchesSuche = (d.massnahme || "").toLowerCase().includes(suche);
            const matchesBL = bl === "Alle" || d.bundesland === bl;
            const matchesKat = kat === "Alle" || d.kategorie === kat;
            const matchesDatum = !datum || (d.massnahme_start && d.massnahme_start.includes(datum.split('-').reverse().join('.')));
            return matchesSuche && matchesBL && matchesKat && matchesDatum;
        });

const isDark = document.body.classList.contains('dark-mode');
    const currentMode = isDark ? 'dark' : 'light';

    const tbody = document.getElementById('table-bewegungsdaten');
    tbody.innerHTML = filtered.map(row => `
        <tr>
            <td>
                <scale-tag mode="${currentMode}" variant="brand">
                    ${row.kategorie || 'BAU'}
                </scale-tag>
                <br><strong>${row.massnahme}</strong>
            </td>
            <td><strong>${row.ort || 'Unbekannt'}</strong><br>${row.bundesland || ''}</td>
            <td>Start: ${row.massnahme_start || '-'}<br>Ende: ${row.massnahme_ende || '-'}</td>
            <td>
                <scale-button
                    mode="${currentMode}"
                    variant="secondary"
                    size="small"
                    href="${row.massnahme_url || '#'}"
                    target="_blank">
                    Quelle
                </scale-button>
            </td>
        </tr>
    `).join('');
}

    switchPage('bestandsdaten');