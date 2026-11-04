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
