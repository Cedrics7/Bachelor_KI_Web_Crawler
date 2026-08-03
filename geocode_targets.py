#!/usr/bin/env python3
"""
geocoding_targets.py
Geocoded alle crawl_results ohne Koordinaten via Nominatim.
Fallback-Kaskade: Adresse+Ort → nur Ort
Ausführen: python geocode_targets.py
"""

import time
import httpx
from PostSQL_Connect import get_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "Bachelor-KI-Crawler/1.0 (Telekom MMS)"}


def geocode(query: str) -> tuple[float | None, float | None]:
    """Gibt (lat, lng) zurück oder (None, None) bei keinem Treffer."""
    try:
        r = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "de"},
            headers=HEADERS,
            timeout=10,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  [WARN] Geocoding-Fehler für '{query}': {e}")
    return None, None


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT cr.id, cr.adresse, ct.ort, ct.bundesland
        FROM   crawl_results cr
        JOIN   crawl_targets  ct ON cr.ags = ct.ags
        WHERE  cr.lat IS NULL
          AND  cr.massnahme IS NOT NULL
        ORDER BY cr.id
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Geocoding {total} Einträge ...")

    updated = 0
    for i, (row_id, adresse, ort, bundesland) in enumerate(rows, 1):
        lat, lng, level = None, None, None

        # 1. Versuch: Straße + Ort (nur wenn adresse sinnvoll befüllt)
        if adresse and len(adresse.strip()) > 5:
            lat, lng = geocode(f"{adresse.strip()}, {ort}, {bundesland}")
            if lat:
                level = "street"

        # 2. Fallback: nur Ort + Bundesland
        if lat is None:
            lat, lng = geocode(f"{ort}, {bundesland}, Deutschland")
            if lat:
                level = "city"

        if lat is not None:
            cur.execute(
                "UPDATE crawl_results SET lat=%s, lng=%s, geo_level=%s WHERE id=%s",
                (lat, lng, level, row_id),
            )
            conn.commit()
            updated += 1
            label = "🎯 street" if level == "street" else "📍 city  "
            print(f"  [{i}/{total}] {label}  {ort} | {adresse or '–'}")
        else:
            print(f"  [{i}/{total}] ❌ kein Treffer  {ort} | {adresse or '–'}")

        time.sleep(1)  # Nominatim Rate-Limit: max 1 req/s

    cur.close()
    conn.close()
    print(f"\nFertig: {updated}/{total} Einträge geocoded.")


if __name__ == "__main__":
    main()
