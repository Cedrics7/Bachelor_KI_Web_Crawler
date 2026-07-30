"""
seed_pipeline.py
================
Reproduzierbarer Seed-Selektor fuer den Bachelor Crawler (Issue #3, Kap. 4/6).

Laedt Ziel-URLs aus municipalities_final_master.csv (oder einer anderen
CSV-Quelle) nach definierten Filterkriterien und einem fixen Zufalls-Seed,
so dass jeder Evaluationslauf exakt dieselben Domains in derselben
Reihenfolge crawlt.

Verwendung:
    pipeline = SeedPipeline.from_config("seed_config.json")
    domains = pipeline.get_domains()
    pipeline.save_snapshot("results/seed_snapshot_20260730.json")

Oder direkt:
    pipeline = SeedPipeline(
        csv_path="municipalities_final_master.csv",
        random_seed=42,
        filter_bundesland="Niedersachsen",
        min_einwohner=5000,
        max_domains=10,
    )
    for domain in pipeline.get_domains():
        print(domain.name, domain.url)
"""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class SeedDomain:
    """
    Eine einzelne Crawl-Zieldomain aus der Seed-Pipeline.

    Attribute:
        name:       Gemeindename
        url:        Crawl-Start-URL
        ags:        Amtlicher Gemeindeschlussel (optional, fuer DB-Verknuepfung)
        bundesland: Bundesland (optional)
        einwohner:  Einwohnerzahl (optional, fuer Thesis-Auswertung)
        max_pages:  Seitenlimit fuer diesen Crawl-Lauf
    """
    name:       str
    url:        str
    ags:        str   = ""
    bundesland: str   = ""
    einwohner:  int   = 0
    max_pages:  int   = 60


class SeedPipeline:
    """
    Reproduzierbarer Seed-Selektor.

    Alle Filterkriterien und der Zufalls-Seed werden beim Erstellen
    festgelegt und koennen als seed_config.json gespeichert werden.
    """

    # Standard-Spaltennamen in municipalities_final_master.csv
    # Anpassen falls die CSV andere Header hat.
    COL_NAME       = "ort"          # oder "name", "gemeinde"
    COL_URL        = "url"
    COL_AGS        = "ags"
    COL_BUNDESLAND = "bundesland"
    COL_EINWOHNER  = "einwohner"    # oder "einwohnerzahl"

    def __init__(
        self,
        csv_path: str = "municipalities_final_master.csv",
        random_seed: int = 42,
        filter_bundesland: Optional[str] = None,
        min_einwohner: int = 0,
        max_domains: int = 0,
        default_max_pages: int = 60,
        manual_overrides: Optional[List[dict]] = None,
    ):
        """
        Args:
            csv_path:           Pfad zur Gemeinde-CSV
            random_seed:        Zufalls-Seed fuer reproduzierbare Auswahl
            filter_bundesland:  Nur Gemeinden dieses Bundeslands (None = alle)
            min_einwohner:      Nur Gemeinden mit >= dieser Einwohnerzahl
            max_domains:        Maximale Anzahl Domains (0 = alle gefilterten)
            default_max_pages:  Standard-Seitenlimit pro Domain
            manual_overrides:   Feste Domains die immer enthalten sind,
                                unabhaengig vom Filter (fuer Thesis-Testdomains)
        """
        self.csv_path          = str(csv_path)
        self.random_seed       = random_seed
        self.filter_bundesland = filter_bundesland
        self.min_einwohner     = min_einwohner
        self.max_domains       = max_domains
        self.default_max_pages = default_max_pages
        self.manual_overrides  = manual_overrides or []
        self._domains: Optional[List[SeedDomain]] = None

    def get_domains(self) -> List[SeedDomain]:
        """
        Gibt die selektierten Domains zurueck (gecacht nach erstem Aufruf).
        Bei erneutem Aufruf wird immer dieselbe Liste zurueckgegeben.
        """
        if self._domains is None:
            self._domains = self._load_and_filter()
        return self._domains

    def _load_and_filter(self) -> List[SeedDomain]:
        """Laedt CSV, filtert und sortiert deterministisch."""
        rng = random.Random(self.random_seed)

        # 1. Manuelle Overrides zuerst (feste Thesis-Testdomains)
        overrides = [
            SeedDomain(
                name=o.get("name", ""),
                url=o.get("url", ""),
                ags=o.get("ags", ""),
                bundesland=o.get("bundesland", ""),
                einwohner=int(o.get("einwohner", 0)),
                max_pages=int(o.get("max_pages", self.default_max_pages)),
            )
            for o in self.manual_overrides
            if o.get("url")
        ]
        override_urls = {d.url for d in overrides}

        # 2. CSV laden (falls vorhanden)
        csv_domains: List[SeedDomain] = []
        p = Path(self.csv_path)
        if p.exists():
            try:
                with open(p, encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    # Spaltennamen normalisieren (lowercase, strip)
                    for row in reader:
                        row_norm = {k.strip().lower(): v.strip() for k, v in row.items()}
                        url = row_norm.get(self.COL_URL.lower(), "")
                        if not url or not url.startswith("http"):
                            continue
                        if url in override_urls:
                            continue

                        bl = row_norm.get(self.COL_BUNDESLAND.lower(), "")
                        if self.filter_bundesland and bl.lower() != self.filter_bundesland.lower():
                            continue

                        try:
                            einwohner = int(row_norm.get(self.COL_EINWOHNER.lower(), 0) or 0)
                        except ValueError:
                            einwohner = 0
                        if einwohner < self.min_einwohner:
                            continue

                        csv_domains.append(SeedDomain(
                            name=row_norm.get(self.COL_NAME.lower(), url),
                            url=url,
                            ags=row_norm.get(self.COL_AGS.lower(), ""),
                            bundesland=bl,
                            einwohner=einwohner,
                            max_pages=self.default_max_pages,
                        ))
            except Exception as exc:
                print(f"[SeedPipeline] CSV-Fehler: {exc}")
        else:
            print(f"[SeedPipeline] CSV nicht gefunden: {p} (nur manuelle Overrides genutzt)")

        # 3. Deterministisch mischen
        rng.shuffle(csv_domains)

        # 4. Limit anwenden (Overrides zaehlen nicht zum Limit)
        if self.max_domains > 0:
            csv_domains = csv_domains[:max(0, self.max_domains - len(overrides))]

        return overrides + csv_domains

    def to_config_dict(self) -> dict:
        """Gibt die Konfiguration als Dict zurueck (fuer seed_config.json)."""
        return {
            "random_seed":        self.random_seed,
            "csv_path":           self.csv_path,
            "filter_bundesland":  self.filter_bundesland,
            "min_einwohner":      self.min_einwohner,
            "max_domains":        self.max_domains,
            "default_max_pages":  self.default_max_pages,
            "manual_overrides":   self.manual_overrides,
        }

    def save_snapshot(self, path: str) -> None:
        """
        Speichert Konfiguration + selektierte Domains als JSON-Snapshot.
        Dieser Snapshot garantiert Reproduzierbarkeit (Kap. 4/6 Thesis).
        """
        domains = self.get_domains()
        snapshot = {
            "generated_at": datetime.now().isoformat(),
            "config":  self.to_config_dict(),
            "domains": [asdict(d) for d in domains],
            "total":   len(domains),
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        print(f"Seed-Snapshot gespeichert: {p} ({len(domains)} Domains)")

    @classmethod
    def from_config(cls, config_path: str) -> "SeedPipeline":
        """Laedt eine SeedPipeline aus einer seed_config.json."""
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        return cls(
            csv_path=cfg.get("csv_path", "municipalities_final_master.csv"),
            random_seed=cfg.get("random_seed", 42),
            filter_bundesland=cfg.get("filter_bundesland"),
            min_einwohner=cfg.get("min_einwohner", 0),
            max_domains=cfg.get("max_domains", 0),
            default_max_pages=cfg.get("default_max_pages", 60),
            manual_overrides=cfg.get("manual_overrides", []),
        )

    def print_summary(self) -> None:
        domains = self.get_domains()
        print(f"\n=== SeedPipeline ===")
        print(f"  CSV:              {self.csv_path}")
        print(f"  random_seed:      {self.random_seed}")
        print(f"  filter_bundesland:{self.filter_bundesland or '(alle)'}")
        print(f"  min_einwohner:    {self.min_einwohner}")
        print(f"  Domains gesamt:   {len(domains)}")
        for i, d in enumerate(domains, 1):
            print(f"  [{i:>3}] {d.name:<30} {d.url}")
