/* =============================================================
   router.js — URL-State-Router & App-Initialisierung
   ============================================================= */

'use strict';

const PAGES = ['bestandsdaten', 'bewegungsdaten', 'monitoring', 'changelog'];

/* ----------------------------------------------------------
   Monitoring-Interval: dediziert starten/stoppen
---------------------------------------------------------- */
let _monitoringInterval = null;
let _kpiInterval        = null;

function _startMonitoringRefresh() {
    if (_monitoringInterval) return;
    _monitoringInterval = setInterval(loadMonitoring, 10_000);
}

function _stopMonitoringRefresh() {
    if (_monitoringInterval) {
        clearInterval(_monitoringInterval);
        _monitoringInterval = null;
    }
}

function _startKpiRefresh() {
    if (_kpiInterval) return;
    _kpiInterval = setInterval(_refreshKpis, 30_000);
}

async function _refreshKpis() {
    try {
        const stats = await fetchStats();
        renderKPIs(stats.total ?? 0, stats.done ?? 0, stats.pending ?? 0);
    } catch { /* still */ }
}

/* ----------------------------------------------------------
   URL-State lesen
---------------------------------------------------------- */
function getState() {
    const p = new URLSearchParams(window.location.search);
    return {
        page:   p.get('page')   || 'bestandsdaten',
        id:     p.get('id')     || null,
        idtype: p.get('idtype') || 'bestand',
        search: p.get('search') || '',
        status: p.get('status') || 'Alle',
        bl:     p.get('bl')     || 'Alle',
        kat:    p.get('kat')    || 'Alle',
        sort:   p.get('sort')   || 'desc',
        p:      parseInt(p.get('p') || '1', 10),
    };
}

/* ----------------------------------------------------------
   URL-State schreiben
---------------------------------------------------------- */
function updateUrl(page, overrides = {}) {
    const current = getState();
    const next    = { ...current, ...overrides };
    if (page && PAGES.includes(page)) next.page = page;
    if (next.page !== current.page)   next.p    = 1;

    const params = new URLSearchParams();
    const skip   = { sort: 'desc', p: 1, status: 'Alle', bl: 'Alle', kat: 'Alle', idtype: 'bestand' };
    Object.entries(next).forEach(([k, v]) => {
        if (v !== null && v !== '' && !(k in skip && String(v) === String(skip[k])))
            params.set(k, v);
    });

    const url = params.toString() ? `?${params}` : window.location.pathname;
    history.pushState(null, '', url);
    render();
}

/* ----------------------------------------------------------
   Haupt-Render
---------------------------------------------------------- */
async function render() {
    const state = getState();

    PAGES.forEach((pg) => {
        document.getElementById(`nav-${pg}`)?.classList.toggle('active', pg === state.page);
        document.getElementById(`page-${pg}`)?.classList.toggle('hidden', pg !== state.page);
    });

    if (state.page === 'monitoring') {
        _startMonitoringRefresh();
    } else {
        _stopMonitoringRefresh();
    }

    if (state.page === 'changelog') {
        await loadChangelog();
        return;
    }

    _syncFilters(state);

    if (state.page === 'bestandsdaten')  await loadBestandsdaten(state);
    if (state.page === 'bewegungsdaten') await loadBewegungsdaten(state);
    if (state.page === 'monitoring')     await loadMonitoring();

    const modal = document.getElementById('detail-modal');
    if (state.id) {
        await loadModal(state.id, state.idtype);
    } else if (modal) {
        modal.removeAttribute('opened');
    }
}

/* ----------------------------------------------------------
   Bestandsdaten laden
---------------------------------------------------------- */
async function loadBestandsdaten(state) {
    try {
        const [data, stats] = await Promise.all([
            fetchBestandsdaten({ page: state.p, search: state.search, status: state.status }),
            fetchStats(),
        ]);
        renderBestandsTable(data.items);
        renderPagination('pagination-controls', state.p, data.total_pages ?? 1, 'goToPage');
        renderKPIs(stats.total ?? 0, stats.done ?? 0, stats.pending ?? 0);
        _syncScaleModes();
    } catch (err) {
        console.error('Bestandsdaten:', err);
    }
}

/* ----------------------------------------------------------
   Bewegungsdaten laden
---------------------------------------------------------- */
async function loadBewegungsdaten(state) {
    try {
        const [data, stats] = await Promise.all([
            fetchBewegungsdaten({ page: state.p, search: state.search, bl: state.bl, kat: state.kat, sort: state.sort }),
            fetchStats(),
        ]);
        renderBewegTable(data.items);
        renderPagination('pagination-controls-beweg', state.p, data.total_pages ?? 1, 'goToPage');
        renderKPIs(stats.total ?? 0, stats.done ?? 0, stats.pending ?? 0);

        const opts = data.filter_options ?? {};
        _populateSelect('filter-beweg-bl',  'Bundesland: Alle', opts.bundeslaender, state.bl);
        _populateSelect('filter-beweg-kat', 'Kategorie: Alle',  opts.kategorien,    state.kat);
        _syncScaleModes();
    } catch (err) {
        console.error('Bewegungsdaten:', err);
    }
}

/* ----------------------------------------------------------
   Monitoring laden
---------------------------------------------------------- */
async function loadMonitoring() {
    try {
        const data = await fetchMonitoringData();
        renderMonitoring(data);
    } catch (err) {
        console.error('Monitoring:', err);
        renderMonitoring({ live: {}, history: `Fehler beim Laden: ${err.message}` });
    }
}

/* ----------------------------------------------------------
   Changelog laden
---------------------------------------------------------- */
async function loadChangelog() {
    try {
        const data = await fetchChangelog();
        renderChangelog(data);
    } catch (err) {
        console.error('Changelog:', err);
        const container = document.getElementById('changelog-list');
        if (container) {
            container.innerHTML = `<p class="changelog-empty" style="color:#E20074">Fehler beim Laden des Changelogs: ${err.message}</p>`;
        }
    }
}

/* ----------------------------------------------------------
   Modal laden — unterscheidet Bestand vs. Bewegung
---------------------------------------------------------- */
async function loadModal(id, idtype) {
    try {
        if (idtype === 'bewegung') {
            const data = await fetchBewegungsdaten({ page: 1, page_size: 1000 });
            const row  = data.items?.find((r) => String(r.id) === String(id));
            if (row) renderModalBewegung(row);
        } else {
            const data = await fetchBestandsdaten({ search: null, status: 'Alle', page: 1, page_size: 500 });
            const row  = data.items?.find((r) => String(r.id) === String(id));
            if (row) renderModal(row);
        }
    } catch (err) {
        console.error('Modal:', err);
    }
}

/* Pagination */
function goToPage(page) {
    updateUrl(null, { p: page });
}

/* ----------------------------------------------------------
   Filter DOM → State synchronisieren
---------------------------------------------------------- */
function _syncFilters(state) {
    _setVal('filter-bestandsdaten-status', state.status);
    _setVal('filter-beweg-bl',   state.bl);
    _setVal('filter-beweg-kat',  state.kat);
    _setVal('filter-beweg-sort', state.sort);
    const suche = document.getElementById('filter-bestandsdaten-suche');
    if (suche && suche.value !== state.search) suche.value = state.search;
}

function _setVal(id, value) {
    const el = document.getElementById(id);
    if (el && el.value !== value) el.value = value;
}

function _populateSelect(id, defaultLabel, values, current) {
    const el = document.getElementById(id);
    if (!el || !values) return;
    el.innerHTML = [`<option value="Alle">${defaultLabel}</option>`]
        .concat((values ?? []).map((v) =>
            `<option value="${v}"${v === current ? ' selected' : ''}>${v}</option>`))
        .join('');
}

function _syncScaleModes() {
    const mode = window._isDark ? (window._isDark() ? 'dark' : 'light') : 'light';
    document.querySelectorAll('scale-button,scale-tag,scale-table,scale-text-field,scale-modal,[mode]')
        .forEach((el) => {
            el.setAttribute('mode', mode);
            if ('mode' in el) el.mode = mode;
        });
}

/* ----------------------------------------------------------
   Browser-Back/Forward
---------------------------------------------------------- */
window.addEventListener('popstate', render);

document.addEventListener('scale-close', (e) => {
    if (e.target?.id === 'detail-modal') {
        updateUrl(null, { id: null, idtype: null });
    }
});

/* ----------------------------------------------------------
   Search-Debounce
---------------------------------------------------------- */
let _searchTimer = null;
function _onSearchInput(id, key) {
    document.getElementById(id)?.addEventListener('scale-input', (e) => {
        clearTimeout(_searchTimer);
        _searchTimer = setTimeout(() =>
            updateUrl(null, { [key]: e.detail?.value ?? e.target.value, p: 1 }), 350);
    });
}

/* ----------------------------------------------------------
   Initialisierung
---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', async () => {
    _onSearchInput('filter-bestandsdaten-suche', 'search');
    _onSearchInput('filter-beweg-suche',         'search');

    /* Footer-Version aus DB */
    try {
        const clData   = await fetchChangelog();
        const versions = clData?.versions ?? [];
        const current  = versions.find((v) => v.is_current) ?? versions[0];
        if (current) {
            const el = document.getElementById('footer-version');
            if (el) el.textContent = `v${current.version}`;
        }
    } catch { /* bleibt statisch */ }

    /* KPIs sofort laden und alle 30s refreshen — seitenunabhängig */
    _refreshKpis();
    _startKpiRefresh();

    render();

    /* API-Status pollen */
    checkApiStatus().then(renderApiStatus);
    setInterval(() => checkApiStatus().then(renderApiStatus), 30_000);
});
