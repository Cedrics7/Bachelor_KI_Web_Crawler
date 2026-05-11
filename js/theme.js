/* =============================================================
   theme.js — Theme-Verwaltung (Scale-konform)

   Verantwortlichkeiten:
   - Kein FOUC (Flash of Unstyled Content): IIFE läuft sofort
   - html.light / html.dark für CSS-Kontext
   - body[data-mode] für Scale Web Components
   - scale-button + Scale-Icons erhalten mode-Prop
   - View Transition API für animierten Wechsel (Fallback vorhanden)
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
        };

        /* View Transition API — animierter Wechsel */
        if (document.startViewTransition) {
            document.startViewTransition(doApply);
        } else {
            doApply();
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