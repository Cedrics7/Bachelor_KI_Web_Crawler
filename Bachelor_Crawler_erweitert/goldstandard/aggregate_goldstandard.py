#!/usr/bin/env python3
"""
aggregate_goldstandard.py (v2)
--------------------------------
Aggregiert granulare Goldstandard-Einträge (z.B. saarlouis_alt.json, leer_alt.json)
auf das Niveau von Themen-/Kategorieseiten, analog zum Barssel-Goldstandard.

NEU in v2: Statt eine ganze Gruppe zu blockieren, wenn sie gemischte
relevant/kategorie-Werte enthält (v1-Verhalten -> zu wenig Reduktion,
siehe Beispiel "Aktuelle-Mitteilungen" mit 9 URLs), wird jede Gruppe jetzt
zuerst nach (relevant, kategorie) in Teilgruppen zerlegt. Jede Teilgruppe
wird für sich aggregiert, wenn sie groß genug ist. Ergebnis: der relevante
Eltern-Eintrag bleibt separat erhalten, aber z.B. 8 irrelevante Geschwister-
Unterseiten werden zu einem Eintrag zusammengefasst.

Nutzung:
    python aggregate_goldstandard.py saarlouis_alt.json saarlouis.json --depth 3 --min-group-size 2
    python aggregate_goldstandard.py leer_alt.json leer.json --depth 3 --min-group-size 2

Empfohlenes Vorgehen zum Erreichen von ~55-60 Einträgen:
    1. Erst mit --depth 3 --min-group-size 2 laufen lassen und die
       ausgegebene Anzahl prüfen.
    2. Reicht das nicht, --depth 2 probieren (aggressiver, fasst z.B.
       /Politik-Verwaltung/Verwaltung/* komplett zusammen) und
       --min-group-size hochsetzen (z.B. 6-9), um zu verhindern, dass
       auch kleine, eigenständige Themenseiten mit verschluckt werden.
    3. Iterativ --min-group-size in 1er-Schritten anpassen, bis
       total_entries im gewünschten Bereich liegt.

Es gibt keinen "richtigen" Einheitswert für --depth/--min-group-size über
alle Kommunen hinweg, weil sich die URL-Strukturen der Websites
unterscheiden -- das ist beabsichtigt und sollte in 6.1/6.3 auch so
begründet werden (Aggregation orientiert sich an der jeweiligen Seiten-
architektur, nicht an einer festen Regel).
"""
import json
import argparse
from urllib.parse import urlparse
from collections import defaultdict


def parent_key(url: str, depth: int) -> str:
    p = urlparse(url)
    segs = [s for s in p.path.split('/') if s]
    return p.netloc + '/' + '/'.join(segs[:depth])


def aggregate(entries, depth=3, min_group_size=3):
    groups = defaultdict(list)
    for e in entries:
        groups[parent_key(e["url"], depth)].append(e)

    new_entries = []
    for key, group in groups.items():
        # Innerhalb der Gruppe nach (relevant, kategorie) trennen,
        # dann jede Teilgruppe separat aggregieren
        sub = defaultdict(list)
        for g in group:
            sub[(g["relevant"], g.get("kategorie", ""))].append(g)

        for (rel, kat), items in sub.items():
            if len(items) < min_group_size:
                new_entries.extend(items)
                continue

            shortest = min(items, key=lambda g: len(g["url"]))
            merged = {
                "url": shortest["url"],
                "relevant": rel,
                "kategorie": kat,
                "notiz": f"AGGREGIERT: repräsentiert {len(items)} granulare Einzelseiten/-meldungen "
                         f"unter '{key}' mit relevant={rel} (auf Themenseiten-Niveau reduziert, "
                         f"analog Barssel-Granularität).",
                "quelle": "aggregiert",
                "aggregierte_urls": [g["url"] for g in items],
            }
            new_entries.append(merged)

    return new_entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_file")
    ap.add_argument("output_file")
    ap.add_argument("--depth", type=int, default=3,
                     help="Anzahl Pfadsegmente, die als 'Themenseite' gelten (Standard: 3)")
    ap.add_argument("--min-group-size", type=int, default=2,
                     help="Ab wie vielen Geschwister-URLs (gleiches relevant+kategorie) wird aggregiert (Standard: 2)")
    args = ap.parse_args()

    with open(args.input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data["entries"] if isinstance(data, dict) else data
    new_entries = aggregate(entries, depth=args.depth, min_group_size=args.min_group_size)

    if isinstance(data, dict):
        data["entries"] = new_entries
        data["total_entries"] = len(new_entries)
        data["total_relevant"] = sum(1 for e in new_entries if e.get("relevant"))
        data["aggregation_hinweis"] = (
            f"Automatisch aggregiert mit depth={args.depth}, min_group_size={args.min_group_size}. "
            f"Ursprüngliche Einzel-URLs siehe Feld 'aggregierte_urls' je Eintrag bzw. Originaldatei."
        )
        out = data
    else:
        out = new_entries

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Eingabe:  {len(entries)} Einträge")
    print(f"Ausgabe:  {len(new_entries)} Einträge")


if __name__ == "__main__":
    main()
