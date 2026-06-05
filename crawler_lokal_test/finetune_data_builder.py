"""
finetune_data_builder.py
========================
Konvertiert vorhandene Eval-Outputs (z.B. von Claude als Ground-Truth)
in ein JSONL-Trainingsformat fuer Gemma Fine-Tuning.

Workflow:
  1. Legt claude-Outputs als Ground-Truth fest
  2. Generiert Trainingspaare: {instruction, input, output}
  3. Speichert als train.jsonl und eval.jsonl (80/20 Split)

Nutzung:
  cd crawler_lokal_test/
  python finetune_data_builder.py --input_dir ../output_eval --ground_truth_model claude-sonnet-4-6
"""

import argparse
import json
import os
import random
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Prompt-Template (identisch mit dem was Gemma spaeter sehen soll)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Du bist ein praeziser Extraktor fuer kommunale Baumassnahmen.
Lies den folgenden Text und extrahiere ausschliesslich konkrete, laufende oder
zukuenftige Bau-, Sanierungs- oder Infrastrukturmassnahmen als JSON."""


def build_instruction(base_url: str, today_str: str) -> str:
    return f"""AUFGABE: Extrahiere aus dem folgenden Webseitentext alle konkreten kommunalen
Bau-, Sanierungs- oder Infrastrukturmassnahmen.

REGELN:
1. Nur Massnahmen mit konkretem Start- ODER Enddatum erfassen.
2. Abgeschlossene Massnahmen (Ende vor {today_str}) WEGLASSEN.
3. Kein Datum erkennbar -> WEGLASSEN.
4. Adresse muss konkreten Strassennamen oder Stadtteil enthalten.
   'Hamburg, Deutschland' allein ist UNGUELTIG -> WEGLASSEN.
5. Keine passende Massnahme im Text -> {{"massnahmen": []}}

ERLAUBTE KATEGORIEN:
Strassenbau, Neubau, Sanierung, Brueckenbau, Tiefbau, Hochbau,
Ausschreibung, Energieversorgung, Wasserversorgung, Abwasser, Digitalisierung

Antworte NUR mit dem JSON-Objekt:
{{
    "massnahmen": [
        {{
            "kategorie": "...",
            "massnahme": "...",
            "adresse": "...",
            "massnahme_start": "YYYY-MM-DD oder null",
            "massnahme_ende": "YYYY-MM-DD oder null",
            "quelle_url": "https://..."
        }}
    ]
}}"""


# ---------------------------------------------------------------------------
# Validierung eines Massnahmen-Eintrags
# ---------------------------------------------------------------------------

def is_valid_massnahme(m: dict, today_str: str) -> bool:
    """Gibt True zurueck, wenn ein Eintrag als Ground-Truth brauchbar ist."""
    # Mindestlaenge Beschreibung
    if len(m.get("massnahme", "")) < 15:
        return False
    # Keine generische Adresse
    adresse = m.get("adresse", "").lower()
    if any(x in adresse for x in ["verschiedene", "mehrere", "stadtgebiet",
                                   "deutschland", "standorte"]):
        return False
    # Mindestens ein Datum
    if not m.get("massnahme_start") and not m.get("massnahme_ende"):
        return False
    # Nicht abgelaufen
    ende = m.get("massnahme_ende")
    if ende and ende < today_str:
        return False
    # URL muss absolut sein
    url = m.get("quelle_url", "")
    if not url.startswith("http"):
        return False
    return True


# ---------------------------------------------------------------------------
# Ground-Truth laden
# ---------------------------------------------------------------------------

def load_ground_truth(input_dir: str, model_id: str) -> list:
    """
    Liest alle flat JSON-Dateien des angegebenen Modells aus output_eval/.
    Gibt eine Liste von (ort, url, massnahmen) zurueck.
    """
    today_str = date.today().isoformat()
    results = []
    input_path = Path(input_dir)

    # Suche nach flachen Dateien: <ort-slug>_<model-id>.json
    for f in input_path.glob(f"*_{model_id}.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            ort = data.get("ort", "")
            url = data.get("url", "")
            raw_massnahmen = data.get("massnahmen", [])
            # Validierung
            valid = [m for m in raw_massnahmen if is_valid_massnahme(m, today_str)]
            if valid:
                results.append({"ort": ort, "url": url, "massnahmen": valid})
                print(f"  Geladen: {f.name} -> {len(valid)}/{len(raw_massnahmen)} gueltige Massnahmen")
            else:
                print(f"  Uebersprungen: {f.name} (keine gueltigen Massnahmen)")
        except Exception as e:
            print(f"  Fehler beim Laden von {f}: {e}")

    # Nested-Struktur: output_eval/<ort>/<model-id>/normalized.json
    for f in input_path.rglob(f"{model_id}/normalized.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            ort = data.get("ort", "")
            url = data.get("url", "")
            raw_massnahmen = data.get("massnahmen", [])
            valid = [m for m in raw_massnahmen if is_valid_massnahme(m, today_str)]
            if valid:
                results.append({"ort": ort, "url": url, "massnahmen": valid})
                print(f"  Geladen (nested): {f} -> {len(valid)} gueltige Massnahmen")
        except Exception as e:
            print(f"  Fehler: {f}: {e}")

    return results


# ---------------------------------------------------------------------------
# Trainingspaare generieren
# ---------------------------------------------------------------------------

def build_training_pairs(ground_truth: list, scraped_texts_dir: str = None) -> list:
    """
    Erstellt Trainingspaare im Alpaca-Format:
    {"instruction": ..., "input": <webseitentext>, "output": <json>}

    Wenn scraped_texts_dir vorhanden: laedt echte Webseitentexte.
    Sonst: generiert synthetische Beispiele aus den Massnahmen.
    """
    today_str = date.today().isoformat()
    pairs = []

    for entry in ground_truth:
        ort = entry["ort"]
        url = entry["url"]
        massnahmen = entry["massnahmen"]

        instruction = build_instruction(url, today_str)
        output_json = json.dumps({"massnahmen": massnahmen}, ensure_ascii=False, indent=2)

        # Versuche echten Webseitentext zu laden
        input_text = _load_scraped_text(ort, scraped_texts_dir)

        if not input_text:
            # Fallback: synthetischer Input aus den Massnahmen selbst
            input_text = _build_synthetic_input(ort, massnahmen)

        pairs.append({
            "instruction": instruction,
            "input": input_text[:8000],  # Max 8.000 Zeichen pro Beispiel
            "output": output_json,
            "metadata": {"ort": ort, "url": url, "massnahmen_count": len(massnahmen)}
        })

    # Negative Beispiele hinzufuegen (leere Ausgabe)
    pairs += _build_negative_examples(len(pairs))

    return pairs


def _load_scraped_text(ort: str, scraped_dir: str) -> str:
    """Laedt einen gecrawlten Rohtext fuer einen Ort, falls vorhanden."""
    if not scraped_dir:
        return ""
    slug = ort.lower().replace(" ", "_").replace("-", "_")
    for ext in [".txt", ".html"]:
        path = Path(scraped_dir) / f"{slug}{ext}"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return f.read()
    return ""


def _build_synthetic_input(ort: str, massnahmen: list) -> str:
    """Erstellt einen synthetischen Eingabetext aus den gefundenen Massnahmen."""
    lines = [f"Offizielle Website der Stadt {ort}\n"]
    for m in massnahmen:
        lines.append(f"Projekt: {m.get('massnahme', '')}")
        if m.get("adresse"):
            lines.append(f"Standort: {m['adresse']}")
        if m.get("massnahme_start"):
            lines.append(f"Baubeginn: {m['massnahme_start']}")
        if m.get("massnahme_ende"):
            lines.append(f"Fertigstellung: {m['massnahme_ende']}")
        if m.get("quelle_url"):
            lines.append(f"Weitere Infos: {m['quelle_url']}")
        lines.append("")
    return "\n".join(lines)


def _build_negative_examples(n_positive: int) -> list:
    """Generiert Negativbeispiele (kein JSON-Output ausser leerer Liste)."""
    today_str = date.today().isoformat()
    negatives = [
        {
            "instruction": build_instruction("https://example.de", today_str),
            "input": "Stellenausschreibung: Wir suchen einen erfahrenen Buchhalter (m/w/d) fuer unser Team. Bewerbungen bis 30.06.2026.",
            "output": json.dumps({"massnahmen": []}, ensure_ascii=False),
            "metadata": {"typ": "negativ", "grund": "Stellenausschreibung"}
        },
        {
            "instruction": build_instruction("https://example.de", today_str),
            "input": "Sommerfest 2026: Das jaehrliche Stadtfest findet am 15. Juli 2026 auf dem Marktplatz statt. Eintritt frei.",
            "output": json.dumps({"massnahmen": []}, ensure_ascii=False),
            "metadata": {"typ": "negativ", "grund": "Kulturveranstaltung"}
        },
        {
            "instruction": build_instruction("https://example.de", today_str),
            "input": "Fahrzeugbeschaffung: Die Feuerwehr hat zwei neue Loeschfahrzeuge bestellt. Lieferung geplant fuer Herbst 2026.",
            "output": json.dumps({"massnahmen": []}, ensure_ascii=False),
            "metadata": {"typ": "negativ", "grund": "Fahrzeugbeschaffung"}
        },
        {
            "instruction": build_instruction("https://example.de", today_str),
            "input": "Pressemitteilung: Der Buergermeister empfaengt eine Delegation aus der Partnerstadt. Gemeinsames Abendessen im Rathaus.",
            "output": json.dumps({"massnahmen": []}, ensure_ascii=False),
            "metadata": {"typ": "negativ", "grund": "Kulturelles Ereignis"}
        },
    ]
    # Anzahl Negative ca. 20% der Positiven
    n_neg = max(2, n_positive // 5)
    return negatives[:n_neg]


# ---------------------------------------------------------------------------
# Train / Eval Split & Speichern
# ---------------------------------------------------------------------------

def save_jsonl(pairs: list, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"  Gespeichert: {path} ({len(pairs)} Beispiele)")


def split_and_save(pairs: list, output_dir: str, eval_ratio: float = 0.2, seed: int = 42):
    random.seed(seed)
    random.shuffle(pairs)
    n_eval = max(1, int(len(pairs) * eval_ratio))
    eval_pairs  = pairs[:n_eval]
    train_pairs = pairs[n_eval:]
    save_jsonl(train_pairs, os.path.join(output_dir, "train.jsonl"))
    save_jsonl(eval_pairs,  os.path.join(output_dir, "eval.jsonl"))
    print(f"\nSplit: {len(train_pairs)} Train / {len(eval_pairs)} Eval")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemma Fine-Tuning Daten aufbereiten")
    parser.add_argument("--input_dir",          default="../output_eval",
                        help="Verzeichnis mit Eval-Outputs (flat JSONs)")
    parser.add_argument("--ground_truth_model", default="claude-sonnet-4-6",
                        help="Modell-ID, dessen Output als Ground-Truth gilt")
    parser.add_argument("--output_dir",          default="../finetune_data",
                        help="Zielverzeichnis fuer train.jsonl / eval.jsonl")
    parser.add_argument("--scraped_texts_dir",   default=None,
                        help="Optionales Verzeichnis mit gecrawlten Rohtexten (.txt)")
    parser.add_argument("--eval_ratio",          type=float, default=0.2)
    args = parser.parse_args()

    print(f"\n=== Gemma Fine-Tuning Daten-Builder ===")
    print(f"  Input-Dir:       {args.input_dir}")
    print(f"  Ground-Truth:    {args.ground_truth_model}")
    print(f"  Output-Dir:      {args.output_dir}")
    print(f"  Eval-Ratio:      {args.eval_ratio}")
    print()

    print("1. Lade Ground-Truth ...")
    gt = load_ground_truth(args.input_dir, args.ground_truth_model)
    print(f"   -> {len(gt)} Eintraege geladen")

    if not gt:
        print("FEHLER: Keine Ground-Truth-Daten gefunden.")
        print("Tipp: Fuehre zuerst crawler_eval.py mit claude-sonnet-4-6 aus.")
        exit(1)

    print("\n2. Baue Trainingspaare ...")
    pairs = build_training_pairs(gt, args.scraped_texts_dir)
    print(f"   -> {len(pairs)} Paare erstellt")

    print("\n3. Split und Speichern ...")
    split_and_save(pairs, args.output_dir, args.eval_ratio)

    print("\nFertig! Naechster Schritt: python finetune_gemma.py")
