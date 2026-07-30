"""
output_schema.py
================
Strukturiertes Ausgabeschema fuer LLM-extrahierte Projektdaten (Issue #2, Kap. 5.4).

Jede vom LLM analysierte Seite erzeugt ein MassnahmeRecord-Objekt.
Dieses Schema ist direkt an die Kategorien aus domain_model.py gekoppelt
und erlaubt quantitative Auswertung (Projekte pro Typ / Ort / Zeitraum).

Verwendung:
    record = MassnahmeRecord.from_llm_item(
        item={"kategorie": "Glasfaser / Breitband", "massnahme": "...", ...},
        quelle_url="https://leer.de/glasfaser",
    )
    if record.is_valid():
        print(record.to_dict())
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Gueltiger Kategorie-Kanon (abgeleitet aus llm_client._ZIEL_KATEGORIEN
# und domain_model.DomainModel.DEFAULT_KEYWORDS)
# ---------------------------------------------------------------------------
GUELTIGE_KATEGORIEN = {
    # LLM-Zielkategorien (llm_client.py)
    "Glasfaser / Breitband",
    "5G / Mobilfunk",
    "Stromnetz / Energieversorgung",
    "Wasserversorgung / Abwasser",
    "Straßenbau / Verkehrsinfrastruktur",
    "Sonstige kommunale Infrastruktur",
    # Domain-Model-Kategorien (domain_model.py) – Alias-Mapping
    "bauen",
    "umwelt",
    "wirtschaft",
    "infrastruktur",
    "verwaltung",
}

# Mapping von LLM-Kategorie → domain_model-Kategorie (fuer Thesis-Auswertung)
KATEGORIE_MAPPING = {
    "Glasfaser / Breitband":             "infrastruktur",
    "5G / Mobilfunk":                    "infrastruktur",
    "Stromnetz / Energieversorgung":      "umwelt",
    "Wasserversorgung / Abwasser":        "infrastruktur",
    "Straßenbau / Verkehrsinfrastruktur": "infrastruktur",
    "Sonstige kommunale Infrastruktur":   "bauen",
}


@dataclass
class MassnahmeRecord:
    """
    Strukturiertes Ausgabeobjekt fuer eine vom LLM extrahierte Massnahme.

    Pflichtfelder: projekttyp, quelle, kategorie_domain
    Optionale Felder: ort, zeitraum_start, zeitraum_ende, konfidenz, adresse

    Thesis-Referenz: Kap. 5.4 – LLM-Extraktion und Ausgabeformat
    """
    projekttyp:       str             # Kurzbezeichnung der Massnahme
    quelle:           str             # Vollstaendige Quell-URL
    kategorie_llm:    str             # Originale LLM-Kategorie
    kategorie_domain: str             # Gemappte domain_model-Kategorie
    ort:              Optional[str]   = None   # Ortsname (aus adresse extrahiert)
    adresse:          Optional[str]   = None   # Vollstaendige Adresse
    zeitraum_start:   Optional[str]   = None   # ISO 8601 oder None
    zeitraum_ende:    Optional[str]   = None   # ISO 8601 oder None
    konfidenz:        float            = 1.0   # Konfidenz-Score \u2208 [0.0, 1.0]
    extrahiert_am:    str             = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )

    def is_valid(self) -> bool:
        """Prueft ob alle Pflichtfelder gesetzt sind."""
        return bool(self.projekttyp and self.quelle and self.kategorie_domain)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_llm_item(cls, item: dict, quelle_url: str) -> "MassnahmeRecord":
        """
        Erzeugt ein MassnahmeRecord aus einem LLM-Massnahmen-Dict.

        Erwartet:
            item = {
                "kategorie":        "Glasfaser / Breitband",
                "massnahme":        "Glasfaserausbau Innenstadt",
                "adresse":          "Marktplatz 1, Leer",
                "massnahme_start":  "2024-03-01",
                "massnahme_ende":   "2025-06-30",
                "quelle_url":       "https://leer.de/glasfaser"
            }
        """
        kat_llm = item.get("kategorie", "") or ""
        kat_domain = KATEGORIE_MAPPING.get(kat_llm, "verwaltung")

        # Ort aus Adresse extrahieren (letztes Komma-Element oder Adresse selbst)
        adresse = item.get("adresse") or None
        ort = None
        if adresse:
            parts = [p.strip() for p in adresse.split(",")]
            ort = parts[-1] if parts else adresse

        return cls(
            projekttyp=item.get("massnahme") or "",
            quelle=item.get("quelle_url") or quelle_url,
            kategorie_llm=kat_llm,
            kategorie_domain=kat_domain,
            ort=ort,
            adresse=adresse,
            zeitraum_start=item.get("massnahme_start") or None,
            zeitraum_ende=item.get("massnahme_ende") or None,
            konfidenz=float(item.get("konfidenz", 1.0)),
        )


class ProjectDataExport:
    """
    Sammelt MassnahmeRecords eines Crawl-Laufs und exportiert sie als JSON.
    Ermoeglicht quantitative Auswertung fuer Kap. 6 der Thesis.

    Verwendung:
        export = ProjectDataExport(domain="leer.de")
        export.add(record)
        export.save_json("results/leer_projekte.json")
        print(export.summary())
    """

    def __init__(self, domain: str = ""):
        self.domain = domain
        self._records: List[MassnahmeRecord] = []

    def add(self, record: MassnahmeRecord) -> None:
        """Fuegt einen validen Record hinzu (ungueltige werden verworfen)."""
        if record.is_valid():
            self._records.append(record)

    def add_from_llm_result(self, llm_result: dict, quelle_url: str) -> int:
        """
        Verarbeitet ein vollstaendiges LLM-Ergebnis ({"massnahmen": [...]}).
        Gibt Anzahl hinzugefuegter Records zurueck.
        """
        added = 0
        for item in llm_result.get("massnahmen", []):
            record = MassnahmeRecord.from_llm_item(item, quelle_url)
            if record.is_valid():
                self._records.append(record)
                added += 1
        return added

    @property
    def total(self) -> int:
        return len(self._records)

    def by_kategorie(self) -> dict:
        """Anzahl Massnahmen pro domain_model-Kategorie."""
        result = {}
        for r in self._records:
            result[r.kategorie_domain] = result.get(r.kategorie_domain, 0) + 1
        return result

    def by_ort(self) -> dict:
        """Anzahl Massnahmen pro Ort."""
        result = {}
        for r in self._records:
            key = r.ort or "(unbekannt)"
            result[key] = result.get(key, 0) + 1
        return result

    def summary(self) -> str:
        lines = [
            f"ProjectDataExport: {self.domain}",
            f"  Massnahmen gesamt:  {self.total}",
            f"  Nach Kategorie:     {self.by_kategorie()}",
            f"  Nach Ort:           {self.by_ort()}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "total": self.total,
            "by_kategorie": self.by_kategorie(),
            "by_ort": self.by_ort(),
            "massnahmen": [r.to_dict() for r in self._records],
        }

    def save_json(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"Projektdaten gespeichert: {p} ({self.total} Massnahmen)")
