/* =============================================================
   api.js — API-Kommunikation
   Pfade und Feldnamen entsprechen exakt api.py (FastAPI-Backend).
   ============================================================= */

'use strict';

const API_BASE = 'http://localhost:8000';

/* Hilfsfunktion: Query-String aus Objekt (leere/null/"Alle"-Werte überspringen) */
function buildQueryString(params) {
    const qs = Object.entries(params)
        .filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== 'Alle')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&');
    return qs ? `?${qs}` : '';
}

/* ----------------------------------------------------------
   GET /api/bestandsdaten
   Query: page, page_size, search, status
   Response: { items, total_count, page, page_size, total_pages }
---------------------------------------------------------- */
async function fetchBestandsdaten(params = {}) {
    const mapped = {
        page:      params.page      ?? 1,
        page_size: params.page_size ?? 50,
        search:    params.search    ?? null,
        status:    params.status    ?? 'Alle',
    };
    const qs = buildQueryString(mapped);
    const res = await fetch(`${API_BASE}/api/bestandsdaten${qs}`);
    if (!res.ok) throw new Error(`Bestandsdaten: HTTP ${res.status}`);
    return res.json();
}

/* ----------------------------------------------------------
   GET /api/bewegungsdaten
   Query: page, page_size, search, bundesland, kategorie, sort
   Response: { items, total_count, total_pages, page, filter_options }
---------------------------------------------------------- */
async function fetchBewegungsdaten(params = {}) {
    const mapped = {
        page:       params.page       ?? 1,
        page_size:  params.page_size  ?? 50,
        search:     params.search     ?? null,
        bundesland: params.bl         ?? 'Alle',
        kategorie:  params.kat        ?? 'Alle',
        sort:       params.sort       ?? 'desc',
    };
    const qs = buildQueryString(mapped);
    const res = await fetch(`${API_BASE}/api/bewegungsdaten${qs}`);
    if (!res.ok) throw new Error(`Bewegungsdaten: HTTP ${res.status}`);
    return res.json();
}

/* ----------------------------------------------------------
   GET /api/stats
   Response: { total, done, pending }
---------------------------------------------------------- */
async function fetchStats() {
    const res = await fetch(`${API_BASE}/api/stats`);
    if (!res.ok) throw new Error(`Stats: HTTP ${res.status}`);
    return res.json();
}

/* ----------------------------------------------------------
   GET /api/monitoring
   Response: {
       live: { aktueller_ort, status, letzte_funde, timestamp },
       history: "<log-text>"
   }
---------------------------------------------------------- */
async function fetchMonitoringData() {
    const res = await fetch(`${API_BASE}/api/monitoring`);
    if (!res.ok) throw new Error(`Monitoring: HTTP ${res.status}`);
    return res.json();
}

/* ----------------------------------------------------------
   GET /api/changelog
   Response: {
       versions: [
           {
               id, version, released_at, summary, is_current,
               items: [ { tag, description }, … ]
           }, …
       ]
   }
   Versionen kommen bereits absteigend sortiert vom Backend.
---------------------------------------------------------- */
async function fetchChangelog() {
    const res = await fetch(`${API_BASE}/api/changelog`);
    if (!res.ok) throw new Error(`Changelog: HTTP ${res.status}`);
    return res.json();   // { versions: [...] }
}

/* ----------------------------------------------------------
   Health-Check (kein dedizierter Endpoint in api.py —
   wir nutzen /api/stats als Proxy, timeout 3s)
---------------------------------------------------------- */
async function checkApiStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`, {
            signal: AbortSignal.timeout(3000),
        });
        return res.ok;
    } catch {
        return false;
    }
}
