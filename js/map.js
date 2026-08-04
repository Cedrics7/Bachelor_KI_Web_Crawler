/**
 * map.js – Leaflet-Kartenansicht für das Crawler-Dashboard
 *
 * KEIN ES-Modul-Export – initMap wird als window.initMap registriert,
 * damit router.js (non-module) die Funktion direkt aufrufen kann.
 *
 * Features (Issue #9):
 * - Dark-/Lightmode-Unterstützung: NUR EINE Kachelquelle (OSM Standard,
 *   deutsch beschriftet). Der Dark Mode wird per CSS-Filter (invert +
 *   hue-rotate) auf die Kachel-Ebene angewendet statt einen zweiten
 *   Kartendienst (z.B. CARTO Dark Matter) zu laden.
 *   Grund: CARTO Dark Matter zeigt bei niedrigem Zoom oft englische/
 *   internationale Ortsnamen ("Cologne" statt "Köln") statt der
 *   deutschen OSM-Namen — die CSS-Invertierung nutzt exakt dieselben
 *   Kacheln wie der Lightmode und ist daher immer sprachkonsistent.
 * - Zoom bis Hausnummern-Ebene: maxZoom 19.
 * - Zeitraum (Beginn/Ende) einer Maßnahme wird im Marker-Popup angezeigt.
 * - Deutsche Zoom-Button-Tooltips (Vergrößern/Verkleinern).
 */

(function () {
    'use strict';

    var _mapInstance   = null;
    var _resizeBound   = false;
    var _tiles         = null;
    var _umrissLayer   = null;

    function _currentlyDark() {
        if (window._isDark) return !!window._isDark();
        return document.documentElement.classList.contains('dark');
    }

    function initMap() {
        if (_mapInstance) {
            setMapTheme(_currentlyDark());
            _invalidateSizeSoon(_mapInstance);
            _loadMapData(_mapInstance);
            return;
        }

        var map = L.map('map', {
            center:      [51.2, 10.4],
            zoom:        6,
            minZoom:     5,
            maxZoom:     19,
            zoomControl: false,
        });
        _mapInstance = map;

        L.control.zoom({
            position:     'topleft',
            zoomInTitle:  'Vergrößern',
            zoomOutTitle: 'Verkleinern',
        }).addTo(map);

        var deBounds = L.latLngBounds(
            L.latLng(46.5, 5.5),
            L.latLng(55.5, 15.5)
        );
        map.setMaxBounds(deBounds);
        map.on('drag', function () {
            map.panInsideBounds(deBounds, { animate: false });
        });

        /* Einzige Kachelquelle — deutsch beschriftet, für Dark Mode
           wird nur ein CSS-Filter auf die Tile-Pane gelegt (siehe
           setMapTheme() + css/map-dark.css). */
        _tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
            maxZoom: 19,
        }).addTo(map);

        setMapTheme(_currentlyDark());

        var legend = L.control({ position: 'bottomright' });
        legend.onAdd = function () {
            var div = L.DomUtil.create('div', 'map-legend');
            div.style.cssText = [
                'background:var(--dashboard-bg-card,#fff)',
                'border:1px solid var(--dashboard-border,#ddd)',
                'border-radius:8px',
                'padding:10px 14px',
                'font-size:13px',
                'line-height:1.8',
                'color:var(--dashboard-text,#222)',
                'box-shadow:0 2px 6px rgba(0,0,0,.15)',
                'min-width:220px',
                'transition:background-color 0.4s cubic-bezier(0.4,0,0.2,1),color 0.4s cubic-bezier(0.4,0,0.2,1),border-color 0.4s cubic-bezier(0.4,0,0.2,1)',
            ].join(';');
            div.innerHTML =
                '<strong style="display:block;margin-bottom:6px">Legende</strong>' +
                _legendRow('#28a745', 'Präziser Standort (Straße)') +
                _legendRow('#ffc107', 'Ungefährer Standort (Ort)');
            return div;
        };
        legend.addTo(map);

        _invalidateSizeSoon(map);

        if (!_resizeBound) {
            window.addEventListener('resize', function () {
                if (_mapInstance) _mapInstance.invalidateSize();
            });
            window.addEventListener('orientationchange', function () {
                if (_mapInstance) _invalidateSizeSoon(_mapInstance);
            });
            _resizeBound = true;
        }

        _loadMapData(map);
    }

    /* ----------------------------------------------------------
       Theme-Wechsel: schaltet nur eine CSS-Klasse auf dem Karten-
       Container um. Die eigentliche Verdunkelung der Kachel-Ebene
       passiert per CSS-Filter (css/map-dark.css), NICHT über eine
       zweite Datenquelle — dadurch bleiben Ortsnamen in beiden
       Modi identisch (deutsch).
    ---------------------------------------------------------- */
    function setMapTheme(isDark) {
        if (!_mapInstance) return;
        var container = _mapInstance.getContainer();
        if (!container) return;
        container.classList.toggle('map-tiles-dark', !!isDark);
        _drawUmriss(_mapInstance, isDark);
    }

    function _drawUmriss(map, isDark) {
        if (_umrissLayer) {
            map.removeLayer(_umrissLayer);
            _umrissLayer = null;
        }
        fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var de = data.features.find(function (f) { return f.properties.ISO_A2 === 'DE'; });
                if (de) {
                    _umrissLayer = L.geoJSON(de, {
                        style: {
                            color:       '#e20074',
                            weight:      4,
                            opacity:     1,
                            fillColor:   '#e20074',
                            fillOpacity: isDark ? 0.22 : 0.13,
                            dashArray:   null,
                            lineCap:     'round',
                            lineJoin:    'round',
                        }
                    }).addTo(map);
                }
            })
            .catch(function () {});
    }

    function _invalidateSizeSoon(map) {
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(function () { map.invalidateSize(); });
        }
        setTimeout(function () { map.invalidateSize(); }, 100);
        setTimeout(function () { map.invalidateSize(); }, 400);
    }

    function _legendRow(color, label) {
        return (
            '<div style="display:flex;align-items:center;gap:8px">' +
            '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;' +
            'background:' + color + ';flex-shrink:0"></span>' +
            '<span>' + label + '</span></div>'
        );
    }

    function _formatDatum(d) {
        if (!d) return null;
        var parts = String(d).split('-');
        if (parts.length === 3) {
            return parts[2] + '.' + parts[1] + '.' + parts[0];
        }
        return d;
    }

    function _zeitraumZeile(item) {
        var start = _formatDatum(item.massnahme_start);
        var ende  = _formatDatum(item.massnahme_ende);
        if (!start && !ende) return '';
        var text = (start || '?') + ' – ' + (ende || '?');
        return '<div style="margin-top:4px">\uD83D\uDCC5 <strong>Zeitraum:</strong> ' + text + '</div>';
    }

    function _loadMapData(map) {
        fetch('/api/map-data?limit=5000')
            .then(function (r) { return r.json(); })
            .then(function (items) {
                map.eachLayer(function (layer) {
                    if (layer instanceof L.CircleMarker) map.removeLayer(layer);
                });
                items.forEach(function (item) {
                    var lat = parseFloat(item.lat);
                    var lng = parseFloat(item.lng);
                    if (isNaN(lat) || isNaN(lng)) return;
                    var precise = item.geo_level === 'street';
                    L.circleMarker([lat, lng], {
                        radius:      7,
                        color:       '#fff',
                        weight:      1.5,
                        fillColor:   precise ? '#28a745' : '#ffc107',
                        fillOpacity: 0.85,
                    }).bindPopup(
                        '<strong>' + (item.massnahme || 'Maßnahme') + '</strong><br>' +
                        (item.ort || '') + (item.bundesland ? ' · ' + item.bundesland : '') + '<br>' +
                        '<small>' + (item.adresse || '') + '</small>' +
                        _zeitraumZeile(item)
                    ).addTo(map);
                });
                console.debug('map.js: ' + items.length + ' Maßnahmen auf der Karte gerendert.');
            })
            .catch(function (err) {
                console.warn('map-data konnte nicht geladen werden:', err);
            });
    }

    window.initMap     = initMap;
    window.setMapTheme = setMapTheme;

}());
