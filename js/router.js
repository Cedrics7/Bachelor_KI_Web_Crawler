/* =============================================================
   router.js — URL-State-Router & App-Initialisierung
   Response-Felder entsprechen api.py.
   ============================================================= */

'use strict';

const PAGES = ['bestandsdaten', 'bewegungsdaten', 'monitoring'];

/* URL-State lesen */
function getState() {
    const p = new URLSearchParams(window.location.search);
    return {
        page:   p.get('page')   || 'bestandsdaten',
        id:     p.get('id')     || null,
        search: p.get('search') || '',
        status: p.get('status') || 'Alle',
        bl:     p.get('bl')     || 'Alle',
        kat:    p.get('kat')    || 'Alle',
        sort:   p.get('sort')   || 'desc',
        p:      parseInt(p.get('p') || '1', 10),
    };
}

/* URL-State schreiben */
function updateUrl(page, overrides = {}) {
    const current = getState();
    const next    = { ...current, ...overrides };
    if (page && PAGES.includes(page)) next.page = page;
    if (next.page !== current.page)   next.p    = 1;

    const params = new URLSearchParams();
    const skip   = { sort: 'desc', p: 1, status: 'Alle', bl: 'Alle', kat: 'Alle' };
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

    /* Navigation + Seiten-Sichtbarkeit */
    PAGES.forEach((pg) => {
        document.getElementById(`nav-${pg}`)
            ?.classList.toggle('active', pg === state.page);
        document.getElementById(`page-${pg}`)
            ?.classList.toggle('hidden', pg !== state.page);
    });

    _syncFilters(state);

    if (state.page === 'bestandsdaten')  await loadBestandsdaten(state);
    if (state.page === 'bewegungsdaten') await loadBewegungsdaten(state);
    if (state.page === 'monitoring')     await loadMonitoring();

    /* Modal */
    const modal = document.getElementById('detail-modal');
    if (state.id) {
        await loadModal(state.id);
    } else if (modal) {
        modal.removeAttribute('opened');
    }
}

/* ----------------------------------------------------------
   Bestandsdaten laden
   api.py Response: { items, total_count, total_pages, page, page_size }
   /api/stats:      { total, done, pending }
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
   api.py Response: { items, total_count, total_pages, page, filter_options }
   filter_options: { bundeslaender: [...], kategorien: [...] }
---------------------------------------------------------- */
async function loadBewegungsdaten(state) {
    try {
        const data = await fetchBewegungsdaten({
            page: state.p,
            search: state.search,
            bl:   state.bl,
            kat:  state.kat,
            sort: state.sort,
        });

        renderBewegTable(data.items);
        renderPagination('pagination-controls-beweg', state.p, data.total_pages ?? 1, 'goToPage');

        /* Filter-Optionen aus filter_options befüllen */
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
   api.py Response: { live: {...}, history: "..." }
---------------------------------------------------------- */
async function loadMonitoring() {
    try {
        const data = await fetchMonitoringData();
        renderMonitoring(data);
    } catch (err) {
        console.error('Monitoring:', err);
        /* Fallback: leere Struktur anzeigen statt Absturz */
        renderMonitoring({ live: {}, history: `Fehler beim Laden: ${err.message}` });
    }
}

/* ----------------------------------------------------------
   Modal laden (einzelner Eintrag via id)
---------------------------------------------------------- */
async function loadModal(id) {
    try {
        const data = await fetchBestandsdaten({ search: null, status: 'Alle', page: 1, page_size: 500 });
        const row  = data.items?.find((r) => String(r.id) === String(id));
        if (row) renderModal(row);
    } catch (err) {
        console.error('Modal:', err);
    }
}

/* Pagination-Helfer */
function goToPage(page) {
    updateUrl(null, { p: page });
}

/* Filter-Felder mit URL-State befüllen */
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

/* Select-Optionen dynamisch befüllen */
function _populateSelect(id, defaultLabel, values, current) {
    const el = document.getElementById(id);
    if (!el || !values) return;
    el.innerHTML = [`<option value="Alle">${defaultLabel}</option>`]
        .concat((values ?? []).map((v) =>
            `<option value="${v}"${v === current ? ' selected' : ''}>${v}</option>`))
        .join('');
}

/* Scale-Mode nach dynamischem Render synchronisieren */
function _syncScaleModes() {
    const mode = window._isDark ? (window._isDark() ? 'dark' : 'light') : 'light';
    document.querySelectorAll('scale-button,scale-tag,scale-table,scale-text-field,scale-modal,[mode]')
        .forEach((el) => {
            el.setAttribute('mode', mode);
            if ('mode' in el) el.mode = mode;
        });
}

/* Browser-Back/Forward */
window.addEventListener('popstate', render);

document.addEventListener('scale-close', (e) => {
    if (e.target?.id === 'detail-modal') {
        updateUrl(null, { id: null });
    }
});

/* Search-Debounce */
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
document.addEventListener('DOMContentLoaded', () => {
    _onSearchInput('filter-bestandsdaten-suche', 'search');
    _onSearchInput('filter-beweg-suche',         'search');

    render();

    /* API-Status pollen */
    checkApiStatus().then(renderApiStatus);
    setInterval(() => checkApiStatus().then(renderApiStatus), 30_000);

    /* Monitoring Auto-Refresh */
    setInterval(() => {
        if (getState().page === 'monitoring') loadMonitoring();
    }, 10_000);
});
