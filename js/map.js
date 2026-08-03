/**
 * map.js – Leaflet-Kartenansicht für das Crawler-Dashboard
 * Fixes: Deutschland-Zentrum, Bounds, Zoom-Limits, Legende repariert
 */

let _mapInstance = null;

export function initMap() {
    if (_mapInstance) {
        _loadMapData(_mapInstance);
        return;
    }

    // ── Karte auf Deutschland zentriert ───────────────────────────
    const map = L.map('map', {
        center:  [51.2, 10.4],   // geographische Mitte Deutschlands
        zoom:    6,
        minZoom: 5,              // kein Rauszoomen auf Weltkarte
        maxZoom: 13,
    });
    _mapInstance = map;

    // ── Deutschland-Bounds (harte Grenze) ────────────────────────
    const deBounds = L.latLngBounds(
        L.latLng(46.5, 5.5),    // SW (Süden/Westen)
        L.latLng(55.5, 15.5)    // NO (Norden/Osten)
    );
    map.setMaxBounds(deBounds);
    map.on('drag', () => map.panInsideBounds(deBounds, { animate: false }));

    // ── Tile-Layer ───────────────────────────────────────────
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
        maxZoom: 19,
    }).addTo(map);

    // ── Deutschland-Umriss (GeoJSON, Telekom Magenta) ───────────────
    fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
        .then(r => r.json())
        .then(data => {
            const de = data.features.find(f => f.properties.ISO_A2 === 'DE');
            if (de) {
                L.geoJSON(de, {
                    style: {
                        color: '#e20074', weight: 2,
                        fillColor: '#e20074', fillOpacity: 0.04,
                    }
                }).addTo(map);
            }
        })
        .catch(() => {});

    // ── Legende ───────────────────────────────────────────────
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = () => {
        const div = L.DomUtil.create('div');
        div.style.cssText = [
            'background:var(--color-surface,#fff)',
            'border:1px solid var(--color-border,#ddd)',
            'border-radius:8px', 'padding:10px 14px',
            'font-size:13px', 'line-height:1.8',
            'color:var(--color-text,#222)',
            'box-shadow:0 2px 6px rgba(0,0,0,.15)',
            'min-width:220px',
        ].join(';');
        div.innerHTML =
            '<strong style="display:block;margin-bottom:6px">Legende</strong>' +
            _legendRow('#28a745', 'Präziser Standort (Straße)') +
            _legendRow('#ffc107', 'Ungefährer Standort (Ort)');
        return div;
    };
    legend.addTo(map);

    _loadMapData(map);
}

function _legendRow(color, label) {
    return (
        '<div style="display:flex;align-items:center;gap:8px">' +
        '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;' +
        'background:' + color + ';flex-shrink:0"></span>' +
        '<span>' + label + '</span></div>'
    );
}

function _loadMapData(map) {
    fetch('/api/map-data')
        .then(r => r.json())
        .then(items => {
            map.eachLayer(layer => {
                if (layer instanceof L.CircleMarker) map.removeLayer(layer);
            });
            items.forEach(item => {
                const lat = parseFloat(item.lat);
                const lng = parseFloat(item.lng);
                if (isNaN(lat) || isNaN(lng)) return;
                const precise = item.geo_level === 'street';
                L.circleMarker([lat, lng], {
                    radius: 7, color: '#fff', weight: 1.5,
                    fillColor: precise ? '#28a745' : '#ffc107',
                    fillOpacity: 0.85,
                }).bindPopup(
                    '<strong>' + (item.massnahme || 'Maßnahme') + '</strong><br>' +
                    (item.ort || '') + (item.bundesland ? ' · ' + item.bundesland : '') + '<br>' +
                    '<small>' + (item.adresse || '') + '</small>'
                ).addTo(map);
            });
        })
        .catch(err => console.warn('map-data konnte nicht geladen werden:', err));
}
