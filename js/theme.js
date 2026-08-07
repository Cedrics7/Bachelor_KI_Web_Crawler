/* =============================================================
   theme.js — Theme-Verwaltung (Scale-konform)

   Verantwortlichkeiten:
   - Kein FOUC (Flash of Unstyled Content): IIFE läuft sofort
   - html.light / html.dark für CSS-Kontext
   - body[data-mode] für Scale Web Components
   - scale-button + Scale-Icons erhalten mode-Prop
   - View Transition API für animierten Wechsel (Fallback vorhanden)
   - Feature (Issue #9): Kartenansicht (map.js) wird bei jedem
     Theme-Wechsel über window.setMapTheme() benachrichtigt, damit
     Tile-Layer + Legende sofort mitschalten, auch wenn die Karte
     gerade geöffnet ist.

   Bugfix: Ist die Kartenansicht (page-karte) gerade sichtbar, wird
   die View Transition API übersprungen. Leaflets Kachel-Grid scheint
   mit dem Vorher/Nachher-Screenshot-Crossfade der View Transition zu
   kollidieren — der alte Kartenzustand blieb nach einem Klick auf den
   Theme-Toggle teils "hängen" (v.a. Dark -> Light), obwohl setMapTheme()
   korrekt aufgerufen wurde. Ohne View Transition wird das Theme direkt
   angewendet, das Problem trat dort nie auf.
   ============================================================= */

(function () {
    'use strict';

    /* ----------------------------------------------------------
       1. Initialer Theme-Status lesen
       Kein localStorage (Sandbox-Restriction) — System-Präferenz.
    ---------------------------------------------------------- */
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    let isDark = prefersDark;

    /* Sofort anwenden — noch vor DOMContentLoaded, kein Flackern */
    _applyThemeImmediate(isDark);

    /* ----------------------------------------------------------
       2. System-Präferenz-Änderungen verfolgen
    ---------------------------------------------------------- */
    window.matchMedia('(prefers-color-scheme: dark)')
        .addEventListener('change', (e) => {
            isDark = e.matches;
            applyTheme(isDark);
        });

    /* ----------------------------------------------------------
       3. Internes sofort-Apply (kein Transition beim Laden)
    ---------------------------------------------------------- */
    function _applyThemeImmediate(dark) {
        const mode = dark ? 'dark' : 'light';
        document.documentElement.className = mode;
        document.body && document.body.setAttribute('data-mode', mode);
    }

    /* ----------------------------------------------------------
       Prüft, ob die Kartenansicht gerade sichtbar ist.
    ---------------------------------------------------------- */
    function _isKartePageVisible() {
        const el = document.getElementById('page-karte');
        return !!el && !el.classList.contains('hidden');
    }

    /* ----------------------------------------------------------
       4. applyTheme() — öffentlich, mit View Transition
       Wird von toggleTheme() und intern aufgerufen.
    ---------------------------------------------------------- */
    function applyTheme(dark) {
        const mode = dark ? 'dark' : 'light';

        const doApply = () => {
            /* HTML-Klasse + body-Attribut */
            document.documentElement.className = mode;
            document.body.setAttribute('data-mode', mode);

            /* Alle Scale-Komponenten mit mode-Prop aktualisieren.
               Selector: Elemente die bereits ein mode-Attribut haben
               oder Scale-spezifisch sind. */
            const scaleSelector = [
                '[mode]',
                'scale-button',
                'scale-tag',
                'scale-modal',
                'scale-table',
                'scale-text-field',
                'scale-icon-action-light-dark-mode',
            ].join(',');

            document.querySelectorAll(scaleSelector).forEach((el) => {
                el.setAttribute('mode', mode);
                if ('mode' in el) el.mode = mode;
            });

            /* Kartenansicht (map.js) mitschalten, falls initialisiert */
            if (window.setMapTheme) {
                window.setMapTheme(dark);
            }
        };

        /* Karte sichtbar -> View Transition überspringen (siehe Kommentar
           oben), direkt anwenden. Sonst wie gehabt mit Crossfade. */
        if (document.startViewTransition && !_isKartePageVisible()) {
            document.startViewTransition(doApply);
        } else {
            doApply();
            /* Sicherheitsnetz: falls die Karte doch gerade erst nach
               doApply() initialisiert wurde oder ein Tile-Repaint hängt,
               nach einem Frame nochmal anstoißen. */
            if (window.setMapTheme) {
                requestAnimationFrame(() => window.setMapTheme(dark));
            }
        }
    }

    /* ----------------------------------------------------------
       5. toggleTheme() — public (onclick aus HTML)
    ---------------------------------------------------------- */
    function toggleTheme() {
        isDark = !isDark;
        applyTheme(isDark);
    }

    /* ----------------------------------------------------------
       6. Exports als globale Funktionen
    ---------------------------------------------------------- */
    window.toggleTheme = toggleTheme;
    window.applyTheme  = applyTheme;
    window._isDark     = () => isDark;
})();
