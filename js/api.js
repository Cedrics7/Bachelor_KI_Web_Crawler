/* =============================================================
   api.js — Fetch-Wrapper für alle Backend-Endpunkte
   ============================================================= */

'use strict';

const API_BASE = '';

async function _get(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${path}`);
    return res.json();
}

function fetchBestandsdaten({ page = 1, page_size = 50, search = '', status = 'Alle', bl = 'Alle' } = {}) {
    const p = new URLSearchParams({ page, page_size });
    if (search)            p.set('search',     search);
    if (status !== 'Alle') p.set('status',     status);
    if (bl     !== 'Alle') p.set('bundesland', bl);
    return _get(`/api/bestandsdaten?${p}`);
}

function fetchBestandsdatenById(id) {
    return _get(`/api/bestandsdaten/${encodeURIComponent(id)}`);
}

function fetchBewegungsdaten({ page = 1, page_size = 50, search = '', bl = 'Alle', kat = 'Alle', sort = 'desc' } = {}) {
    const p = new URLSearchParams({ page, page_size, sort });
    if (search)         p.set('search',     search);
    if (bl  !== 'Alle') p.set('bundesland', bl);
    if (kat !== 'Alle') p.set('kategorie',  kat);
    return _get(`/api/bewegungsdaten?${p}`);
}

function fetchStats({ status = 'Alle', bl = 'Alle' } = {}) {
    const p = new URLSearchParams();
    if (status !== 'Alle') p.set('status',     status);
    if (bl     !== 'Alle') p.set('bundesland', bl);
    const qs = p.toString();
    return _get(`/api/stats${qs ? '?' + qs : ''}`);
}

function fetchBewegungStats({ bl = 'Alle', kat = 'Alle' } = {}) {
    const p = new URLSearchParams();
    if (bl  !== 'Alle') p.set('bundesland', bl);
    if (kat !== 'Alle') p.set('kategorie',  kat);
    const qs = p.toString();
    return _get(`/api/bewegung_stats${qs ? '?' + qs : ''}`);
}

function fetchMonitoringData() {
    return _get('/api/monitoring');
}

function fetchChangelog() {
    return _get('/api/changelog');
}

function fetchMapData({ bl = 'Alle', kat = 'Alle', limit = 1000 } = {}) {
    const p = new URLSearchParams({ limit });
    if (bl  !== 'Alle') p.set('bundesland', bl);
    if (kat !== 'Alle') p.set('kategorie',  kat);
    return _get(`/api/map-data?${p}`);
}

async function checkApiStatus() {
    try {
        const res = await fetch('/api/stats', { signal: AbortSignal.timeout(4000) });
        return res.ok;
    } catch {
        return false;
    }
}
