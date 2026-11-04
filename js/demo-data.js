/* =============================================================
   demo-data.js — Beispieldaten und simulierte API fuer den Demo-Modus
   -------------------------------------------------------------
   Antwortet im selben Format wie api.py. Alle Daten sind frei
   erfunden (nur Ortsnamen und Koordinaten sind real) und werden
   deterministisch erzeugt, damit die Demo reproduzierbar bleibt.
   ============================================================= */

(function () {
    'use strict';

    if (!window.DEMO_MODE) return;

    /* ---------- Zufall (deterministisch) ---------- */
    function mulberry32(a) {
        return function () {
            a |= 0; a = (a + 0x6D2B79F5) | 0;
            var t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }
    var rnd = mulberry32(20261104);
    function pick(arr) { return arr[Math.floor(rnd() * arr.length)]; }

    /* ---------- Datumshilfen ---------- */
    var DAY = 86400000;
    var now = new Date();
    var firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    var todayStart   = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    function p2(n) { return String(n).padStart(2, '0'); }
    function fmtDate(d)     { return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); }
    function fmtDateTime(d) { return fmtDate(d) + 'T' + p2(d.getHours()) + ':' + p2(d.getMinutes()) + ':' + p2(d.getSeconds()); }
    function fmtDe(d)       { return p2(d.getDate()) + '.' + p2(d.getMonth() + 1) + '.' + d.getFullYear(); }
    function fmtDeTime(d)   { return fmtDe(d) + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes()); }
    function fmtDeSec(d)    { return fmtDeTime(d) + ':' + p2(d.getSeconds()); }

    /* ---------- Orte: [Ort, AGS, Bundesland, lat, lng] ---------- */
    var CITIES = [
        ['Köln', '05315000', 'Nordrhein-Westfalen', 50.9375, 6.9603],
        ['Düsseldorf', '05111000', 'Nordrhein-Westfalen', 51.2277, 6.7735],
        ['Bochum', '05911000', 'Nordrhein-Westfalen', 51.4818, 7.2162],
        ['Hagen', '05914000', 'Nordrhein-Westfalen', 51.3671, 7.4633],
        ['Wuppertal', '05124000', 'Nordrhein-Westfalen', 51.2562, 7.1508],
        ['Bonn', '05314000', 'Nordrhein-Westfalen', 50.7374, 7.0982],
        ['Essen', '05113000', 'Nordrhein-Westfalen', 51.4556, 7.0116],
        ['Dortmund', '05913000', 'Nordrhein-Westfalen', 51.5136, 7.4653],
        ['Münster', '05515000', 'Nordrhein-Westfalen', 51.9607, 7.6261],
        ['Bielefeld', '05711000', 'Nordrhein-Westfalen', 52.0302, 8.5325],
        ['Hannover', '03241001', 'Niedersachsen', 52.3759, 9.7320],
        ['Oldenburg', '03403000', 'Niedersachsen', 53.1435, 8.2146],
        ['Braunschweig', '03101000', 'Niedersachsen', 52.2689, 10.5268],
        ['Osnabrück', '03404000', 'Niedersachsen', 52.2799, 8.0472],
        ['München', '09162000', 'Bayern', 48.1351, 11.5820],
        ['Augsburg', '09761000', 'Bayern', 48.3705, 10.8978],
        ['Nürnberg', '09564000', 'Bayern', 49.4521, 11.0767],
        ['Regensburg', '09362000', 'Bayern', 49.0134, 12.1016],
        ['Hamburg', '02000000', 'Hamburg', 53.5511, 9.9937],
        ['Bremen', '04011000', 'Bremen', 53.0793, 8.8017],
        ['Berlin', '11000000', 'Berlin', 52.5200, 13.4050],
        ['Stuttgart', '08111000', 'Baden-Württemberg', 48.7758, 9.1829],
        ['Karlsruhe', '08212000', 'Baden-Württemberg', 49.0069, 8.4037],
        ['Freiburg im Breisgau', '08311000', 'Baden-Württemberg', 47.9990, 7.8421],
        ['Frankfurt am Main', '06412000', 'Hessen', 50.1109, 8.6821],
        ['Kassel', '06611000', 'Hessen', 51.3127, 9.4797],
        ['Wiesbaden', '06414000', 'Hessen', 50.0782, 8.2398],
        ['Mainz', '07315000', 'Rheinland-Pfalz', 49.9929, 8.2473],
        ['Trier', '07211000', 'Rheinland-Pfalz', 49.7499, 6.6371],
        ['Saarbrücken', '10041100', 'Saarland', 49.2402, 6.9969],
        ['Magdeburg', '15003000', 'Sachsen-Anhalt', 52.1205, 11.6276],
        ['Halle (Saale)', '15002000', 'Sachsen-Anhalt', 51.4825, 11.9700],
        ['Leipzig', '14713000', 'Sachsen', 51.3397, 12.3731],
        ['Dresden', '14612000', 'Sachsen', 51.0504, 13.7373],
        ['Erfurt', '16051000', 'Thüringen', 50.9848, 11.0299],
        ['Potsdam', '12054000', 'Brandenburg', 52.3906, 13.0645],
        ['Rostock', '13003000', 'Mecklenburg-Vorpommern', 54.0924, 12.0991],
        ['Schwerin', '13004000', 'Mecklenburg-Vorpommern', 53.6355, 11.4012],
        ['Kiel', '01002000', 'Schleswig-Holstein', 54.3233, 10.1228],
        ['Lübeck', '01003000', 'Schleswig-Holstein', 53.8655, 10.6866]
    ];

    function slug(s) {
        return s.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
                .replace(/[^a-z]+/g, '-').replace(/^-|-$/g, '');
    }

    /* ---------- Bestandsdaten (crawl_targets) ---------- */
    var TARGETS = CITIES.map(function (c, i) {
        var r = rnd(), scanned = null;
        if (r >= 0.18 && r < 0.72) {
            scanned = new Date(now.getTime() - rnd() * (now - firstOfMonth));
        } else if (r >= 0.72) {
            scanned = new Date(firstOfMonth.getTime() - (1 + rnd() * 40) * DAY);
        }
        return {
            id: i + 1, ort: c[0], ags: c[1], bundesland: c[2], lat: c[3], lng: c[4],
            _scanned: scanned,
            url: 'https://example.org/demo/ratsinformation/' + slug(c[0])
        };
    });

    /* ---------- Bewegungsdaten (crawl_results) ---------- */
    var KATEGORIEN = ['Sanierung', 'Neubau', 'Privatisierung', 'Tiefbau'];
    var STRASSEN = ['Hauptstraße', 'Bahnhofstraße', 'Gartenstraße', 'Schulstraße', 'Ringstraße',
                    'Industrieweg', 'Am Markt', 'Lindenallee', 'Bergstraße', 'Kirchweg', 'Hafenstraße', 'Mühlenweg'];
    var GEBIETE = ['Am Bahnhof', 'Nordpark', 'Südstadt-Quartier', 'Hafenviertel', 'Grüne Mitte', 'Am Stadtwald', 'Technologiepark'];
    var VORLAGEN = {
        'Sanierung':      ['Fahrbahnsanierung {s}', 'Gehwegsanierung {s}', 'Sanierung Fahrbahn und Gehweg {s}'],
        'Neubau':         ['Erschließung Neubaugebiet {g}', 'Neubau Gewerbegebiet {g}', 'Neubau Kreisverkehr {s}'],
        'Privatisierung': ['Veräußerung kommunaler Fläche {g}', 'Verkauf Gewerbegrundstück {s}'],
        'Tiefbau':        ['Tiefbauarbeiten Wasserleitung {s}', 'Kanalerneuerung {s}', 'Verlegung Fernwärmeleitung {s}']
    };

    var RESULTS = [];
    for (var i = 1; i <= 140; i++) {
        var city  = pick(TARGETS);
        var kat   = pick(KATEGORIEN);
        var str   = pick(STRASSEN);
        var geb   = pick(GEBIETE);
        var titel = pick(VORLAGEN[kat]).replace('{s}', str).replace('{g}', geb);
        var street = rnd() < 0.6;
        var start = new Date(now.getTime() + (rnd() * 240 - 90) * DAY);
        var ende  = new Date(start.getTime() + (30 + rnd() * 300) * DAY);
        var found = rnd() < 0.1
            ? new Date(todayStart.getTime() + rnd() * (now - todayStart))
            : new Date(now.getTime() - (rnd() * 60) * DAY);
        RESULTS.push({
            id: i,
            massnahme: titel,
            adresse: street ? str + ' ' + (1 + Math.floor(rnd() * 80)) + ', ' + city.ort : city.ort,
            ort: city.ort,
            ags: city.ags,
            bundesland: city.bundesland,
            kategorie: kat,
            massnahme_start: fmtDate(start),
            massnahme_ende: fmtDate(ende),
            massnahme_url: 'https://example.org/demo/ratsinformation/' + slug(city.ort) + '/vorlage-' + i,
            end_time: fmtDateTime(found),
            gefunden_am: fmtDateTime(found),
            lat: city.lat + (street ? (rnd() - 0.5) * 0.04 : 0),
            lng: city.lng + (street ? (rnd() - 0.5) * 0.06 : 0),
            geo_level: street ? 'street' : 'city',
            _found: found
        });
    }

    /* ---------- Hilfsfunktionen fuer die Endpunkte ---------- */
    function clean(row) {
        var o = {};
        Object.keys(row).forEach(function (k) { if (k.charAt(0) !== '_') o[k] = row[k]; });
        return o;
    }
    function unique(arr) { return arr.filter(function (v, i) { return v && arr.indexOf(v) === i; }).sort(); }
    function paginate(list, q) {
        var size = Math.max(1, Math.min(500, parseInt(q.get('page_size') || '50', 10)));
        var page = Math.max(1, parseInt(q.get('page') || '1', 10));
        var total = list.length;
        return {
            slice: list.slice((page - 1) * size, page * size),
            total_count: total, page: page, page_size: size,
            total_pages: Math.max(1, Math.ceil(total / size))
        };
    }
    function filterTargets(q) {
        var search = (q.get('search') || '').toLowerCase();
        var status = q.get('status') || 'Alle';
        var bl     = q.get('bundesland') || 'Alle';
        return TARGETS.filter(function (t) {
            if (search && t.ort.toLowerCase().indexOf(search) < 0 && t.ags.indexOf(search) < 0) return false;
            if (status === 'Gecrawlt'   && !t._scanned) return false;
            if (status === 'Ausstehend' &&  t._scanned) return false;
            if (bl !== 'Alle' && t.bundesland !== bl) return false;
            return true;
        });
    }
    function filterResults(q) {
        var search = (q.get('search') || '').toLowerCase();
        var bl  = q.get('bundesland') || 'Alle';
        var kat = q.get('kategorie') || 'Alle';
        return RESULTS.filter(function (r) {
            if (search && r.massnahme.toLowerCase().indexOf(search) < 0
                       && r.adresse.toLowerCase().indexOf(search) < 0
                       && r.ort.toLowerCase().indexOf(search) < 0) return false;
            if (bl  !== 'Alle' && r.bundesland !== bl)  return false;
            if (kat !== 'Alle' && r.kategorie  !== kat) return false;
            return true;
        });
    }
    function targetView(t) {
        return {
            id: t.id, ort: t.ort, ags: t.ags, bundesland: t.bundesland, url: t.url,
            last_scanned: t._scanned ? fmtDeTime(t._scanned) : '-'
        };
    }

    /* ---------- Endpunkte ---------- */
    var ROUTES = {
        '/api/stats': function (q) {
            var list = filterTargets(q);
            var done = list.filter(function (t) { return t._scanned && t._scanned >= firstOfMonth; }).length;
            return { total: list.length, done: done, pending: list.length - done };
        },
        '/api/bewegung_stats': function (q) {
            var list = filterResults(q);
            return {
                total: list.length,
                month: list.filter(function (r) { return r._found >= firstOfMonth; }).length,
                today: list.filter(function (r) { return r._found >= todayStart; }).length
            };
        },
        '/api/bestandsdaten': function (q) {
            var pg = paginate(filterTargets(q), q);
            return {
                items: pg.slice.map(targetView),
                total_count: pg.total_count, page: pg.page, page_size: pg.page_size, total_pages: pg.total_pages,
                filter_options: { bundeslaender: unique(TARGETS.map(function (t) { return t.bundesland; })) }
            };
        },
        '/api/bewegungsdaten': function (q) {
            var asc = (q.get('sort') || 'desc').toLowerCase() === 'asc';
            var list = filterResults(q).slice().sort(function (a, b) {
                return asc ? a._found - b._found : b._found - a._found;
            });
            var pg = paginate(list, q);
            return {
                items: pg.slice.map(clean),
                total_count: pg.total_count, total_pages: pg.total_pages, page: pg.page,
                filter_options: {
                    bundeslaender: unique(TARGETS.map(function (t) { return t.bundesland; })),
                    kategorien: unique(RESULTS.map(function (r) { return r.kategorie; }))
                }
            };
        },
        '/api/map-data': function (q) {
            var limit = Math.max(1, Math.min(5000, parseInt(q.get('limit') || '1000', 10)));
            return filterResults(q)
                .slice().sort(function (a, b) { return b._found - a._found; })
                .slice(0, limit)
                .map(function (r) {
                    return {
                        id: r.id, massnahme: r.massnahme, adresse: r.adresse, kategorie: r.kategorie,
                        massnahme_url: r.massnahme_url, massnahme_start: r.massnahme_start, massnahme_ende: r.massnahme_ende,
                        lat: r.lat, lng: r.lng, geo_level: r.geo_level, ort: r.ort, bundesland: r.bundesland
                    };
                });
        },
        '/api/monitoring': function () {
            var TICK = 6000;
            var tick = Math.floor(Date.now() / TICK);
            var cur  = TARGETS[tick % TARGETS.length];
            var funde = RESULTS.filter(function (r) { return r._found >= todayStart; }).length;
            var lines = [];
            for (var k = 0; k < 20; k++) {
                var t  = tick - k;
                var ct = TARGETS[((t % TARGETS.length) + TARGETS.length) % TARGETS.length];
                var ts = new Date(t * TICK);
                var n  = (t * 7919) % 4 === 0 ? 1 : 0;
                var msg = t % 10 === 0
                    ? 'INFO: Heartbeat – Crawler aktiv'
                    : 'CRAWL: ' + ct.ort + ' (' + ct.ags + ') geprüft – ' + n + ' neue Maßnahme(n)';
                lines.push('[' + fmtDe(ts) + ', ' + p2(ts.getHours()) + ':' + p2(ts.getMinutes()) + ':' + p2(ts.getSeconds()) + '] ' + msg + '\n');
            }
            return {
                live: {
                    aktueller_ort: cur.ort + ' (' + cur.ags + ')',
                    status: 'läuft (Demo-Simulation)',
                    letzte_funde: funde,
                    timestamp: fmtDeSec(new Date()),
                    started_at: fmtDe(todayStart) + ' 06:00:00',
                    stopped_at: null,
                    seconds_since_heartbeat: 3
                },
                history: lines.join('')
            };
        },
        '/api/changelog': function () {
            var d = function (m, t) { return fmtDe(new Date(now.getFullYear(), m - 1, t)); };
            return { versions: [
                { id: 5, version: '1.0.0', released_at: d(11, 4), summary: 'Demo-Modus', is_current: true, items: [
                    { tag: 'feat',  scope: 'frontend', description: 'Demo-Modus mit Beispieldaten: Das Dashboard läuft ohne API und Datenbank.' },
                    { tag: 'chore', scope: 'frontend', description: 'Scale-Komponenten werden im Demo-Modus per CDN geladen.' } ] },
                { id: 4, version: '0.9.0', released_at: d(10, 20), summary: 'Kartenansicht', items: [
                    { tag: 'feat',  scope: 'karte', description: 'Maßnahmen auf der Karte mit Zeitraum im Popup und Legende (präziser/ungefährer Standort).' },
                    { tag: 'style', scope: 'karte', description: 'Dark Mode über CSS-Filter statt zweiter Kartenquelle.' } ] },
                { id: 3, version: '0.8.0', released_at: d(10, 6), summary: 'Live-Monitoring', items: [
                    { tag: 'feat', scope: 'monitoring', description: 'Status, aktuelles Ziel, Funde heute und Crawler-Verlauf mit Auto-Refresh.' } ] },
                { id: 2, version: '0.7.0', released_at: d(9, 22), summary: 'Bewegungsdaten', items: [
                    { tag: 'feat', scope: 'bewegungsdaten', description: 'Filter nach Bundesland und Kategorie, Sortierung, Suche und Detailansicht.' } ] },
                { id: 1, version: '0.6.0', released_at: d(9, 8), summary: 'Bestandsdaten', items: [
                    { tag: 'feat', scope: 'bestandsdaten', description: 'Tabelle der Crawl-Ziele mit Status- und Bundesland-Filter sowie Pagination.' } ] }
            ] };
        }
    };

    window.DemoApi = {
        handle: function (path) {
            var parts = String(path).split('?');
            var pathname = parts[0];
            var q = new URLSearchParams(parts[1] || '');
            var byId = pathname.match(/^\/api\/bestandsdaten\/(.+)$/);
            var data;
            if (byId) {
                var id = parseInt(decodeURIComponent(byId[1]), 10);
                var t = TARGETS.filter(function (x) { return x.id === id; })[0];
                if (!t) throw new Error('HTTP 404: ' + path);
                data = targetView(t);
            } else if (ROUTES[pathname]) {
                data = ROUTES[pathname](q);
            } else {
                throw new Error('HTTP 404: ' + path);
            }
            return JSON.parse(JSON.stringify(data));
        }
    };

    /* ---------- fetch('/api/...') auf die Demo-API umleiten ---------- */
    var realFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        var url = typeof input === 'string' ? input : ((input && input.url) || '');
        if (url.indexOf('/api/') === 0) {
            try {
                return Promise.resolve(new Response(JSON.stringify(window.DemoApi.handle(url)), {
                    status: 200, headers: { 'Content-Type': 'application/json' }
                }));
            } catch (e) {
                return Promise.resolve(new Response(JSON.stringify({ detail: String(e.message) }), { status: 404 }));
            }
        }
        return realFetch(input, init);
    };

    /* ---------- Oberflaeche: Hinweisleiste + Statusanzeige ---------- */
    document.addEventListener('DOMContentLoaded', function () {
        window.renderApiStatus = function () {
            var dot   = document.getElementById('api-status-dot');
            var label = document.getElementById('api-status-label');
            if (dot)   dot.className = 'status-dot dot-online';
            if (label) label.textContent = 'DEMO-MODUS';
        };

        var bar = document.createElement('div');
        bar.setAttribute('role', 'note');
        bar.style.cssText = 'background:#fff8e1;color:#5d4037;border-bottom:1px solid #ffe0b2;padding:6px 16px;font-size:12px;text-align:center;';
        bar.textContent = 'Demo-Modus: Alle Daten sind frei erfundene Beispieldaten. Es werden keine API und keine Datenbank benötigt.';
        var accent = document.querySelector('.telekom-accent-bar');
        if (accent && accent.parentNode) accent.parentNode.insertBefore(bar, accent.nextSibling);
        else document.body.insertBefore(bar, document.body.firstChild);
    });
}());
