/* =============================================================
   config.js — Betriebsmodus des Dashboards
   -------------------------------------------------------------
   Demo-Modus : statisch, Beispieldaten im Browser (keine API, keine DB)
   Live-Modus : echte FastAPI-Schnittstelle (api.py)

   Standard:  Live nur, wenn die Seite von der FastAPI selbst kommt
              (localhost / 127.0.0.1 auf Port 8000, siehe api.py)
              Alles andere -> Demo, z. B. Hosting, file:// oder ein
              lokaler Testserver wie `python -m http.server 8080`
   Override:  localStorage.setItem('crawlerMode', 'demo' | 'live')

   Hinweis Karte: OpenStreetMap-Kacheln brauchen einen Referer. Bei
   file:// gibt es keinen -> Seite ueber http(s) oeffnen.
   ============================================================= */

'use strict';

(function () {
    var loc   = window.location;
    var host  = loc.hostname;
    var local = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    var liveHost = local && loc.port === '8000';
    var forced = null;
    try { forced = window.localStorage.getItem('crawlerMode'); } catch (e) { /* ignorieren */ }

    window.DEMO_MODE = forced === 'demo' ? true
                     : forced === 'live' ? false
                     : !liveHost;
}());
