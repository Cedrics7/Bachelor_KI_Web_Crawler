/**
 * map.js – Leaflet-Kartenansicht für das Crawler-Dashboard
 *
 * KEIN ES-Modul-Export – initMap wird als window.initMap registriert,
 * damit router.js (non-module) die Funktion direkt aufrufen kann.
 *
 * Bugfix (Issue #9): Auf mobilen Endgeräten wurde die Karte nicht
 * geladen, wenn der Tab "Karte" angeklickt wurde. Ursache: Der
 * #map-Container ist beim ersten Initialisieren noch über
 * "display:none" (.hidden) versteckt, Leaflet berechnet die
 * Kartengröße dadurch als 0x0 und zeigt danach nur graue Kacheln
 * bzw. gar nichts an. invalidateSize() wurde in einem früheren
 * Refactoring versehentlich entfernt und hier wieder ergänzt –
 * inkl. Aufruf bei jedem erneuten Tab-Wechsel und bei Resize/
 * Orientation-Change, damit es auch bei Rotation auf Mobilgeräten
 * funktioniert.
 */

(function () {
    'use strict';

    var _mapInstance = null;
    var _resizeBound = false;

    function initMap() {
        if (_mapInstance) {
            // Tab wurde erneut geöffnet: Containergröße kann sich
            // geändert haben (z.B. Rotation), daher neu berechnen.
            _invalidateSizeSoon(_mapInstance);
            _loadMapData(_mapInstance);
            return;
        }

        var map = L.map('map', {
            center:  [51.2, 10.4],
            zoom:    6,
            minZoom: 5,
            maxZoom: 13,
        });
        _mapInstance = map;

        var deBounds = L.latLngBounds(
            L.latLng(46.5, 5.5),
            L.latLng(55.5, 15.5)
        );
        map.setMaxBounds(deBounds);
        map.on('drag', function () {
            map.panInsideBounds(deBounds, { animate: false });
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
            maxZoom: 19,
        }).addTo(map);

        // ── Deutschland-Umriss: starke Magenta-Grenze + sichtbare Füllung ──
        fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var de = data.features.find(function (f) { return f.properties.ISO_A2 === 'DE'; });
                if (de) {
                    L.geoJSON(de, {
                        style: {
                            color:       '#e20074',
                            weight:      4,
                            opacity:     1,
                            fillColor:   '#e20074',
                            fillOpacity: 0.13,
                            dashArray:   null,
                            lineCap:     'round',
                            lineJoin:    'round',
                        }
                    }).addTo(map);
                }
            })
            .catch(function () {});

        var legend = L.control({ position: 'bottomright' });
        legend.onAdd = function () {
            var div = L.DomUtil.create('div');
            div.style.cssText = [
                'background:var(--color-surface,#fff)',
                'border:1px solid var(--color-border,#ddd)',
                'border-radius:8px',
                'padding:10px 14px',
                'font-size:13px',
                'line-height:1.8',
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

        // Fix: Container war beim Initialisieren evtl. noch "hidden"
        // (display:none) -> Leaflet kennt dann eine Größe von 0x0.
        // invalidateSize() zwingt Leaflet, die Größe nach dem Sichtbar-
        // werden neu zu berechnen. Mehrere Versuche (rAF + Timeout),
        // da mobile Browser das Layout teils verzögert fertigstellen.
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
                        '<small>' + (item.adresse || '') + '</small>'
                    ).addTo(map);
                });
                console.debug('map.js: ' + items.length + ' Maßnahmen auf der Karte gerendert.');
            })
            .catch(function (err) {
                console.warn('map-data konnte nicht geladen werden:', err);
            });
    }

    window.initMap = initMap;

}());
