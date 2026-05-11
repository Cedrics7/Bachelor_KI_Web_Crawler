/* =============================================================
   render.js — DOM-Render-Funktionen
   ============================================================= */

'use strict';

function externalLinkIcon() {
    return `
        <svg class="icon-external"
             xmlns="http://www.w3.org/2000/svg" width="16" height="16"
             viewBox="0 0 24 24" fill="none"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true">
            <path d="M14 3h7v7"/>
            <path d="M10 14L21 3"/>
            <path d="M21 14v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        </svg>`;
}

/* ----------------------------------------------------------
   Kategorie-Badge
---------------------------------------------------------- */
const KAT_COLORS = {
    'Sanierung':      { bg: '#E20074', fg: '#fff' },
    'Neubau':         { bg: '#0064A3', fg: '#fff' },
    'Privatisierung': { bg: '#7D3F98', fg: '#fff' },
    'Tiefbau':        { bg: '#00884A', fg: '#fff' },
};

function _katBadge(kat) {
    const c = KAT_COLORS[kat] ?? { bg: '#727272', fg: '#fff' };
    return `<span style="display:inline-block;font-size:0.6rem;font-weight:700;text-transform:uppercase;
        letter-spacing:0.05em;padding:0.15rem 0.5rem;border-radius:3px;
        background:${c.bg};color:${c.fg};white-space:nowrap;">${esc(kat ?? '-')}</span>`;
}

/* ----------------------------------------------------------
   KPI-Cards
---------------------------------------------------------- */
function renderKPIs(total, done, pending) {
    _animateNumber('kpi-total',   total);
    _animateNumber('kpi-done',    done);
    _animateNumber('kpi-pending', pending);
}

function _animateNumber(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        el.textContent = Number(target).toLocaleString('de-DE');
        return;
    }
    const start    = parseInt(el.textContent.replace(/[^\d]/g, '')) || 0;
    const duration = 800;
    const startTs  = performance.now();
    requestAnimationFrame(function step(ts) {
        const progress = Math.min((ts - startTs) / duration, 1);
        const eased    = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased).toLocaleString('de-DE');
        if (progress < 1) requestAnimationFrame(step);
    });
}

/* ----------------------------------------------------------
   Bestandsdaten-Tabelle
---------------------------------------------------------- */
function renderBestandsTable(items) {
    const mode  = _mode();
    const tbody = document.getElementById('table-bestandsdaten');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = _emptyRow(6, 'Keine Einträge gefunden.');
        return;
    }

    tbody.innerHTML = items.map((row) => `
        <tr class="table-row" onclick="updateUrl(null, { id: ${row.id}, idtype: 'bestand' })">
            <td>${row.id}</td>
            <td>${esc(row.ort)}</td>
            <td>${esc(row.ags)}</td>
            <td>${esc(row.bundesland ?? '-')}</td>
            <td>${esc(row.last_scanned ?? '-')}</td>
            <td>
                <scale-button variant="ghost" size="small"
                    href="${esc(row.url)}" target="_blank"
                    mode="${mode}" aria-label="Quelle öffnen"
                    onclick="event.stopPropagation()">
                    ${externalLinkIcon()}
                </scale-button>
            </td>
        </tr>
    `).join('');
}

/* ----------------------------------------------------------
   Bewegungsdaten-Tabelle — mit Kategorie-Badge + Modal
---------------------------------------------------------- */
function renderBewegTable(items) {
    const mode  = _mode();
    const tbody = document.getElementById('table-bewegungsdaten');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = _emptyRow(6, 'Keine Einträge gefunden.');
        return;
    }

    tbody.innerHTML = items.map((row) => `
        <tr class="table-row" onclick="updateUrl(null, { id: ${row.id}, idtype: 'bewegung' })">
            <td class="col-massnahme">
                ${_katBadge(row.kategorie)}
                <div style="margin-top:0.3rem">${esc(row.massnahme)}</div>
            </td>
            <td>
                ${esc(row.ort)}
                <br><small style="opacity:0.55">${esc(row.bundesland ?? '')}</small>
            </td>
            <td>${esc(row.adresse ?? '-')}</td>
            <td>${_dateRange(row.massnahme_start, row.massnahme_ende)}</td>
            <td>${esc(row.gefunden_am ?? row.end_time ?? '-')}</td>
            <td style="text-align:right">
                <scale-button variant="ghost" size="small"
                    href="${esc(row.massnahme_url ?? '#')}" target="_blank"
                    mode="${mode}" aria-label="Quelle öffnen"
                    onclick="event.stopPropagation()">
                    ${externalLinkIcon()}
                </scale-button>
            </td>
        </tr>
    `).join('');
}

/* ----------------------------------------------------------
   Pagination
---------------------------------------------------------- */
function renderPagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const mode = _mode();
    container.innerHTML = `
        <scale-button variant="secondary" size="small" mode="${mode}"
            ${currentPage <= 1 ? 'disabled' : ''}
            onclick="${onPageChange}(${currentPage - 1})">
            &larr; Zurück
        </scale-button>
        <span class="pagination-info">Seite ${currentPage} / ${totalPages}</span>
        <scale-button variant="secondary" size="small" mode="${mode}"
            ${currentPage >= totalPages ? 'disabled' : ''}
            onclick="${onPageChange}(${currentPage + 1})">
            Weiter &rarr;
        </scale-button>`;
}

/* ----------------------------------------------------------
   Modal — Bestandsdaten
---------------------------------------------------------- */
function renderModal(row) {
    const content = document.getElementById('modal-content');
    if (!content) return;

    const fields = [
        ['ID',            row.id],
        ['Ort',           row.ort],
        ['AGS',           row.ags],
        ['Bundesland',    row.bundesland],
        ['Letzter Crawl', row.last_scanned ?? '-'],
        ['URL', row.url
            ? `<a href="${esc(row.url)}" target="_blank" rel="noopener noreferrer">${esc(row.url)}</a>`
            : '-'],
    ];

    content.innerHTML = `<div class="modal-body">${fields.map(([k, v]) => `
        <div class="modal-row">
            <span class="modal-key">${k}</span>
            <span class="modal-val">${v ?? '-'}</span>
        </div>`).join('')}</div>`;

    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.heading = `Ort: ${row.ort}`;
        modal.setAttribute('opened', '');
    }
}

/* ----------------------------------------------------------
   Modal — Bewegungsdaten
---------------------------------------------------------- */
function renderModalBewegung(row) {
    const content = document.getElementById('modal-content');
    if (!content) return;

    const fields = [
        ['Kategorie',   _katBadge(row.kategorie)],
        ['Maßnahme',   row.massnahme],
        ['Adresse',     row.adresse ?? '-'],
        ['Ort',         row.ort],
        ['Bundesland',  row.bundesland ?? '-'],
        ['Zeitraum',    _dateRange(row.massnahme_start, row.massnahme_ende)],
        ['Gefunden am', row.gefunden_am ?? row.end_time ?? '-'],
        ['Quelle', row.massnahme_url
            ? `<a href="${esc(row.massnahme_url)}" target="_blank" rel="noopener noreferrer">${esc(row.massnahme_url)}</a>`
            : '-'],
    ];

    content.innerHTML = `<div class="modal-body">${fields.map(([k, v]) => `
        <div class="modal-row">
            <span class="modal-key">${k}</span>
            <span class="modal-val">${v ?? '-'}</span>
        </div>`).join('')}</div>`;

    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.heading = `${esc(row.kategorie ?? 'Maßnahme')}: ${esc(row.ort)}`;
        modal.setAttribute('opened', '');
    }
}

/* ----------------------------------------------------------
   Monitoring
---------------------------------------------------------- */
function renderMonitoring(data) {
    const live = data.live ?? {};
    _setText('live-ort',    live.aktueller_ort ?? '-');
    _setText('live-funde',  live.letzte_funde  ?? 0);
    _setText('live-status', live.status        ?? 'Unbekannt');
    _setText('live-time',   live.timestamp     ?? '');

    const logEl = document.getElementById('monitoring-log');
    if (logEl) {
        const text = data.history ?? 'Keine Logs vorhanden.';
        logEl.textContent = text;
        logEl.scrollTop   = logEl.scrollHeight;
    }
}

/* ----------------------------------------------------------
   Changelog
---------------------------------------------------------- */
const TAG_COLORS = {
    feat:     { bg: '#E20074', fg: '#ffffff' },
    fix:      { bg: '#00884A', fg: '#ffffff' },
    refactor: { bg: '#0064A3', fg: '#ffffff' },
    perf:     { bg: '#7D3F98', fg: '#ffffff' },
    style:    { bg: '#009AA0', fg: '#ffffff' },
    chore:    { bg: '#727272', fg: '#ffffff' },
    docs:     { bg: '#8B5A00', fg: '#ffffff' },
};

function _tagBadge(tag) {
    const color = TAG_COLORS[tag?.toLowerCase()] ?? { bg: '#727272', fg: '#ffffff' };
    return `<span class="changelog-tag" style="background:${color.bg};color:${color.fg}">${esc(tag ?? 'other')}</span>`;
}

function renderChangelog(data) {
    const container = document.getElementById('changelog-list');
    if (!container) return;

    const versions = data?.versions ?? [];
    if (versions.length === 0) {
        container.innerHTML = `<p class="changelog-empty">Keine Versionen gefunden.</p>`;
        return;
    }

    container.innerHTML = versions.map((v) => {
        const isCurrent = v.is_current;
        const items     = v.items ?? [];
        const itemsHtml = items.length > 0
            ? `<ul class="changelog-items">${items.map((it) => `
                <li class="changelog-item">
                    ${_tagBadge(it.tag)}
                    <span class="changelog-item-text">${esc(it.description)}</span>
                </li>`).join('')}</ul>`
            : `<p class="changelog-no-items">Keine Einträge.</p>`;

        return `
        <article class="changelog-card${isCurrent ? ' changelog-card--current' : ''}">
            <header class="changelog-card-header">
                <div class="changelog-version-row">
                    <span class="changelog-version">v${esc(v.version)}</span>
                    ${isCurrent ? '<span class="changelog-badge-current">Aktuell</span>' : ''}
                </div>
                <div class="changelog-meta">
                    <span class="changelog-date">${esc(v.released_at ?? '')}</span>
                    ${v.summary ? `<span class="changelog-summary">${esc(v.summary)}</span>` : ''}
                </div>
            </header>
            ${itemsHtml}
        </article>`;
    }).join('');

    const currentVersion = versions.find((v) => v.is_current) ?? versions[0];
    if (currentVersion) {
        const footerEl = document.getElementById('footer-version');
        if (footerEl) footerEl.textContent = `v${currentVersion.version}`;
    }
}

/* ----------------------------------------------------------
   API-Status
---------------------------------------------------------- */
function renderApiStatus(online) {
    const dot   = document.getElementById('api-status-dot');
    const label = document.getElementById('api-status-label');
    if (!dot || !label) return;
    dot.className     = `status-dot ${online ? 'dot-online' : 'dot-offline'}`;
    label.textContent = online ? 'API LIVE' : 'API OFFLINE';
}

/* ----------------------------------------------------------
   Hilfsfunktionen
---------------------------------------------------------- */
function esc(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g,  '&amp;')
        .replace(/</g,  '&lt;')
        .replace(/>/g,  '&gt;')
        .replace(/"/g,  '&quot;');
}

function _dateRange(von, bis) {
    if (!von && !bis) return '-';
    return `${von ?? ''}${bis ? ` – ${bis}` : ''}`;
}

function _mode() {
    return window._isDark ? (window._isDark() ? 'dark' : 'light') : 'light';
}

function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function _emptyRow(cols, msg) {
    return `<tr><td colspan="${cols}" style="text-align:center;padding:2rem;opacity:0.5;">${msg}</td></tr>`;
}
