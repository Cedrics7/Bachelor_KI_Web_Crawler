"""
Einmaliges Fix-Skript: Vervollständigt relative massnahme_url-Einträge
in crawl_results anhand der zugehörigen crawl_targets.url (Basis-Domain).

Nur Einträge von heute werden angefasst (gefunden_am = heute).
Ausführen mit: python fix_urls.py
"""
from urllib.parse import urlparse, urljoin
from datetime import date
from database import get_db_connection


def fix_relative_urls():
    conn   = get_db_connection(as_dict=True)
    cur    = conn.cursor()
    heute  = date.today().strftime("%m/%d/%y")  # passt zum gespeicherten Format %x

    # Alle heutigen Einträge mit relativer oder fehlender URL laden
    cur.execute("""
        SELECT r.id, r.massnahme_url, r.ags, t.url AS basis_url
        FROM crawl_results r
        LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text
        WHERE r.gefunden_am = %s
    """, (heute,))
    rows = cur.fetchall()

    fixed   = 0
    skipped = 0

    for row in rows:
        raw_url  = row['massnahme_url'] or ''
        basis    = row['basis_url']     or ''
        parsed   = urlparse(raw_url)

        if parsed.scheme in ('http', 'https'):
            skipped += 1
            continue  # bereits absolut, nichts zu tun

        if not basis:
            print(f"  ⚠️  Kein basis_url für id={row['id']}, übersprungen")
            skipped += 1
            continue

        absolute_url = urljoin(basis, raw_url) if raw_url else basis
        cur.execute(
            "UPDATE crawl_results SET massnahme_url = %s WHERE id = %s",
            (absolute_url, row['id'])
        )
        print(f"  ✅ id={row['id']}: '{raw_url}' → '{absolute_url}'")
        fixed += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nFertig: {fixed} URLs korrigiert, {skipped} bereits korrekt oder übersprungen.")


if __name__ == "__main__":
    fix_relative_urls()
