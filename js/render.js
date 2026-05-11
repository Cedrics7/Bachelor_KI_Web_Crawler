/* =============================================================
   render.js — DOM-Render-Funktionen
   Feldnamen entsprechen der api.py-Response-Struktur.
   ============================================================= */

'use strict';

/* ----------------------------------------------------------
   SVG External-Link Icon
   Bewusst KEIN currentColor — stattdessen schwarz/weiß je Mode,
   weil Scale-Icon-Buttons in Ghost-Variant sonst bläulich wirken.
   Farbe wird via CSS-Klasse gesteuert: .icon-external
---------------------------------------------------------- */
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
   KPI-Cards — animierte Zahlen
   api.py → /api/stats: { total, done, pending }
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
        el.textContent = Math.round(start + (target - start) * eased)
                           .toLocaleString('de-DE');
        if (progress < 1) requestAnimationFrame(step);
    });
}

/* ----------------------------------------------------------
   Bestandsdaten-Tabelle
   api.py Response-Felder: id, ort, ags, bundesland, last_scanned, url
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
        <tr class="table-row" onclick="updateUrl(null, { id: ${row.id} })">
            <td>${row.id}</td>
            <td>${esc(row.ort)}</td>
            <td>${esc(row.ags)}</td>
            <td>${esc(row.bundesland ?? '-')}</td>
            <td>${esc(row.last_scanned ?? '-')}</td>
            <td>
                <scale-button
                    variant="ghost"
                    size="small"
                    href="${esc(row.url)}"
                    target="_blank"
                    mode="${mode}"
                    aria-label="Quelle öffnen">
                    ${externalLinkIcon()}
                </scale-button>
            </td>
        </tr>
    `).join('');
}

/* ----------------------------------------------------------
   Bewegungsdaten-Tabelle
   api.py Response-Felder:
     massnahme, adresse, ort, massnahme_start, massnahme_ende,
     massnahme_url, bundesland, kategorie, end_time, gefunden_am
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
        <tr class="table-row">
            <td class="col-massnahme">${esc(row.massnahme)}</td>
            <td>
                ${esc(row.ort)}
                <br><small style="opacity:0.55">${esc(row.bundesland ?? '')}</small>
            </td>
            <td>${esc(row.adresse ?? '-')}</td>
            <td>${_dateRange(row.massnahme_start, row.massnahme_ende)}</td>
            <td>${esc(row.gefunden_am ?? row.end_time ?? '-')}</td>
            <td style="text-align:right">
                <scale-button
                    variant="ghost"
                    size="small"
                    href="${esc(row.massnahme_url ?? '#')}"
                    target="_blank"
                    mode="${mode}"
                    aria-label="Quelle öffnen">
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
   Detail-Modal
   Feldnamen: id, ort, ags, bundesland, last_scanned, url
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

    content.innerHTML = `
        <div class="modal-body">
            ${fields.map(([k, v]) => `
                <div class="modal-row">
                    <span class="modal-key">${k}</span>
                    <span class="modal-val">${v ?? '-'}</span>
                </div>`).join('')}
        </div>`;

    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.heading = `Ort: ${row.ort}`;
        modal.setAttribute('opened', '');
    }
}

/* ----------------------------------------------------------
   Monitoring
   api.py Response:
     live: { aktueller_ort, status, letzte_funde, timestamp }
     history: "<log-text>"
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
