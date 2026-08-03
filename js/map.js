/* =============================================================
   map.js — Leaflet-Kartenansicht
   Zeigt Maßnahmen aus /api/map-data als Marker:
     🔴 Kleiner Punkt  = Straße bekannt (geo_level='street')
     🔵 Großer Kreis   = nur Ort bekannt (geo_level='city')
   ============================================================= */

'use strict';

let _mapInstance   = null;
let _markerLayer   = null;
let _mapDataCache  = null;

/* ----------------------------------------------------------
   Einstiegspunkt — wird von router.js aufgerufen
---------------------------------------------------------- */
async function initMap() {
    // Karte nur einmal initialisieren
    if (!_mapInstance) {
        _mapInstance = L.map('map', { zoomControl: true }).setView([51.1657, 10.4515], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
            maxZoom: 19,
        }).addTo(_mapInstance);

        _addLegend();
    }

    // Größe neu berechnen (wichtig wenn Karte vorher hidden war)
    setTimeout(() => _mapInstance.invalidateSize(), 50);

    // Daten nur einmal laden (Cache)
    if (!_mapDataCache) {
        try {
            const res = await fetch('/api/map-data');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            _mapDataCache = await res.json();
        } catch (err) {
            console.error('map.js: Fehler beim Laden der Kartendaten:', err);
            _showMapError();
            return;
        }
    }

    _renderMarkers(_mapDataCache);
}

/* ----------------------------------------------------------
   Marker rendern
---------------------------------------------------------- */
function _renderMarkers(data) {
    if (_markerLayer) {
        _mapInstance.removeLayer(_markerLayer);
    }
    _markerLayer = L.layerGroup().addTo(_mapInstance);

    let streetCount = 0, cityCount = 0;

    data.forEach((m) => {
        if (!m.lat || !m.lng) return;

        const isStreet = m.geo_level === 'street';
        isStreet ? streetCount++ : cityCount++;

        const marker = L.circleMarker([m.lat, m.lng], _markerStyle(isStreet));
        marker.bindPopup(_buildPopup(m));
        marker.addTo(_markerLayer);
    });

    console.debug(`map.js: ${streetCount} Straßen-Marker, ${cityCount} Orts-Marker gerendert.`);
}

/* ----------------------------------------------------------
   Marker-Style nach Präzision
---------------------------------------------------------- */
function _markerStyle(isStreet) {
    return isStreet
        ? { radius: 7,  color: '#E20074', fillColor: '#E20074', fillOpacity: 0.9, weight: 2 }
        : { radius: 13, color: '#0064A3', fillColor: '#0064A3', fillOpacity: 0.25, weight: 2 };
}

/* ----------------------------------------------------------
   Popup-Inhalt
---------------------------------------------------------- */
function _buildPopup(m) {
    const zeitraum = (m.massnahme_start || m.massnahme_ende)
        ? `${m.massnahme_start ?? '?'} – ${m.massnahme_ende ?? '?'}`
        : '–';
    const quelle = m.massnahme_url
        ? `<a href="${m.massnahme_url}" target="_blank" rel="noopener noreferrer">Quelle öffnen ↗</a>`
        : '';

    return `
        <div style="min-width:200px;font-size:0.85rem;line-height:1.5">
            <b style="display:block;margin-bottom:4px">${_esc(m.massnahme)}</b>
            <span style="font-size:0.75rem;opacity:0.7">${m.geo_level === 'street' ? '🎯 Straße' : '📍 Ort'}</span><br>
            📍 ${_esc(m.adresse || m.ort)}, ${_esc(m.bundesland ?? '')}<br>
            🏷 ${_esc(m.kategorie ?? '–')}<br>
            📅 ${zeitraum}<br>
            ${quelle}
        </div>`;
}

/* ----------------------------------------------------------
   Legende
---------------------------------------------------------- */
function _addLegend() {
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = function () {
        const div = L.DomUtil.create('div');
        div.style.cssText = [
            'background:var(--color-bg, #fff)',
            'border:1px solid #ccc',
            'border-radius:6px',
            'padding:10px 14px',
            'font-size:0.78rem',
            'line-height:1.8',
            'box-shadow:0 1px 4px rgba(0,0,0,.15)',
        ].join(';');
        div.innerHTML = [
            '<b style="display:block;margin-bottom:4px">Präzision</b>',
            '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;',
            'background:#E20074;margin-right:6px;vertical-align:middle"></span>Straße bekannt<br>',
            '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;',
            'background:#0064A3;opacity:0.4;margin-right:6px;vertical-align:middle"></span>Nur Ort bekannt',
        ].join('');
        return div;
    };
    legend.addTo(_mapInstance);
}

/* ----------------------------------------------------------
   Fehleranzeige
---------------------------------------------------------- */
function _showMapError() {
    const el = document.getElementById('map');
    if (el) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.5">Kartendaten konnten nicht geladen werden.</div>';
    }
}

function _esc(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
