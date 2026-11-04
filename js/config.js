/* =============================================================
   config.js — Betriebsmodus des Dashboards
   -------------------------------------------------------------
   Demo-Modus : statisch, Beispieldaten im Browser (keine API, keine DB)
   Live-Modus : echte FastAPI-Schnittstelle (api.py)

   Standard:  localhost / 127.0.0.1  -> Live
              alles andere (Hosting, file://) -> Demo
   Override:  localStorage.setItem('crawlerMode', 'demo' | 'live')
   ============================================================= */

'use strict';

(function () {
    var host  = window.location.hostname;
    var local = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    var forced = null;
    try { forced = window.localStorage.getItem('crawlerMode'); } catch (e) { /* ignorieren */ }

    window.DEMO_MODE = forced === 'demo' ? true
                     : forced === 'live' ? false
                     : !local;
}());

/* -------------------------------------------------------------
   OpenStreetMap Tile Usage Policy: Kachel-Anfragen brauchen einen
   gueltigen Referer. Leaflet 1.9.4 setzt dafuer nichts, deshalb
   bekommt jede Kachel (img) die Referrer-Policy direkt.
   Hinweis: Bei file:// gibt es keinen Referer -> Seite ueber einen
   Webserver oeffnen (http://localhost oder echtes Hosting).
   ------------------------------------------------------------- */
(function () {
    function patchLeafletTiles() {
        if (!window.L || !window.L.TileLayer || window.L.TileLayer.__referrerPatched) return;
        var policy = 'strict-origin-when-cross-origin';
        var createTile = window.L.TileLayer.prototype.createTile;
        window.L.TileLayer.prototype.createTile = function (coords, done) {
            var tile = createTile.call(this, coords, done);
            tile.referrerPolicy = policy;
            return tile;
        };
        window.L.TileLayer.__referrerPatched = true;
    }
    document.addEventListener('DOMContentLoaded', patchLeafletTiles);
}());
