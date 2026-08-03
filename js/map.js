/**
 * map.js – Leaflet-Kartenansicht für das Crawler-Dashboard
 *
 * KEIN ES-Modul-Export – initMap wird als window.initMap registriert,
 * damit router.js (non-module) die Funktion direkt aufrufen kann.
 */

(function () {
    'use strict';

    var _mapInstance = null;

    function initMap() {
        if (_mapInstance) {
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

        fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var de = data.features.find(function (f) { return f.properties.ISO_A2 === 'DE'; });
                if (de) {
                    L.geoJSON(de, {
                        style: {
                            color:       '#e20074',
                            weight:      2,
                            fillColor:   '#e20074',
                            fillOpacity: 0.04,
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
                _legendRow('#28a745', 'Pr\u00e4ziser Standort (Stra\u00dfe)') +
                _legendRow('#ffc107', 'Ungef\u00e4hrer Standort (Ort)');
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
                        '<strong>' + (item.massnahme || 'Ma\u00dfnahme') + '</strong><br>' +
                        (item.ort || '') + (item.bundesland ? ' \u00b7 ' + item.bundesland : '') + '<br>' +
                        '<small>' + (item.adresse || '') + '</small>'
                    ).addTo(map);
                });
            })
            .catch(function (err) {
                console.warn('map-data konnte nicht geladen werden:', err);
            });
    }

    window.initMap = initMap;

}());
