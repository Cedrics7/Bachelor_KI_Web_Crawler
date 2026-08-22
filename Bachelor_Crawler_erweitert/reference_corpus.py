"""
reference_corpus.py
===================
Referenzkorpus-Modul fuer den Focused Crawler.

Ein Referenzkorpus (Goldstandard) enthaelt manuell annotierte URLs einer
Zieldomain, die als relevant oder nicht relevant klassifiziert wurden.

Dieser Goldstandard ist notwendig, um Recall und damit F1-Score
berechen zu koennen:

    Recall = |relevant_gefunden ∩ goldstandard_relevant| / |goldstandard_relevant|

Ohne Referenzkorpus ist nur die Harvest Rate (Precision) messbar.

Verwendung:
    corpus = ReferenceCorpus.from_json("goldstandard/leer_alt.json")
    recall = corpus.compute_recall(crawled_urls=["https://leer.de/wirtschaft", ...])
    print(f"Recall: {recall:.4f}")

Kategorien (aus domain_model.py):
    bauen, umwelt, wirtschaft, infrastruktur, verwaltung

FIX (2026-08-13):
    _normalize_for_compare() entfernte bisher nur das 'www.'-Praefix, nicht
    aber das Schema (http:// vs https://). Da viele Kommunen-Webseiten
    inzwischen zwingend auf https redirecten, annotierte Goldstandard-URLs
    aber teils noch mit http:// angelegt wurden, matchten viele tatsaechlich
    korrekte Treffer NICHT -> Recall wurde faelschlich 0.0 (z.B. Potsdam,
    Hagen). Das Schema wird jetzt vollstaendig entfernt und zusaetzlich
    ein optionaler 'index.html'/'index.php'-Suffix normalisiert.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_INDEX_SUFFIX_RE = re.compile(r"/(index\.(html?|php))$", re.IGNORECASE)


def _normalize_for_compare(url: str) -> str:
    """
    Zentrale Normalisierungsfunktion fuer URL-Vergleiche zwischen
    Crawler-Ergebnissen und Goldstandard-Eintraegen.

    Entfernt: Schema (http/https), Trailing Slash, Query-Parameter,
    'www.'-Praefix, optionale index.html/index.php-Suffixe, und
    vereinheitlicht Gross-/Kleinschreibung.

    Wichtig: Das Schema wird komplett entfernt, NICHT nur 'www.', da sonst
    http- und https-Varianten derselben Seite als unterschiedlich gelten
    und Recall-Berechnungen faelschlich 0.0 liefern.
    """
    u = url.strip()

    # Query-Parameter und Fragment entfernen, bevor irgendetwas anderes passiert
    if "?" in u:
        u = u.split("?")[0]
    if "#" in u:
        u = u.split("#")[0]

    u = u.lower()

    # Schema vollstaendig entfernen (http:// und https:// gleichbehandeln)
    u = _SCHEME_RE.sub("", u)

    # 'www.'-Praefix entfernen (nach Schema-Entfernung steht es jetzt am Anfang)
    if u.startswith("www."):
        u = u[len("www."):]

    u = u.rstrip("/")

    # index.html / index.php am Pfadende ist aequivalent zum Verzeichnis selbst
    u = _INDEX_SUFFIX_RE.sub("", u)

    return u


@dataclass
class CorpusEntry:
    """
    Eine einzelne annotierte Seite im Referenzkorpus.

    Attribute:
        url:        Vollstaendige URL der Seite (normalisiert, ohne Trailing Slash)
        relevant:   True = relevant fuer kommunale Projekte, False = nicht relevant
        kategorie:  Kategorie aus domain_model.py (bauen/umwelt/wirtschaft/infrastruktur/verwaltung)
                    Leer lassen wenn nicht relevant.
        notiz:      Optionale Begruendung fuer die Annotation
    """
    url: str
    relevant: bool
    kategorie: str = ""
    notiz: str = ""

    def normalized_url(self) -> str:
        """Gibt die URL normalisiert zurueck (siehe _normalize_for_compare)."""
        return _normalize_for_compare(self.url)


class ReferenceCorpus:
    """
    Verwaltet den Goldstandard einer Testdomain.

    Beispiel:
        corpus = ReferenceCorpus(domain="leer.de")
        corpus.add(CorpusEntry(url="https://leer.de/wirtschaft", relevant=True, kategorie="wirtschaft"))
        corpus.save_json("goldstandard/leer_alt.json")
    """

    VALID_CATEGORIES = {"bauen", "umwelt", "wirtschaft", "infrastruktur", "verwaltung", ""}

    def __init__(self, domain: str = "", annotator: str = "", date: str = ""):
        """
        Args:
            domain:     Domain-Name (z. B. 'leer.de')
            annotator:  Name des Annotators (fuer Thesis-Dokumentation)
            date:       Datum der Annotation (ISO 8601: YYYY-MM-DD)
        """
        self.domain = domain
        self.annotator = annotator
        self.date = date
        self._entries: List[CorpusEntry] = []

    def add(self, entry: CorpusEntry) -> None:
        """Fuegt eine annotierte Seite hinzu."""
        if entry.kategorie not in self.VALID_CATEGORIES:
            raise ValueError(f"Unbekannte Kategorie '{entry.kategorie}'. Gueltig: {self.VALID_CATEGORIES}")
        self._entries.append(entry)

    @property
    def relevant_urls(self) -> Set[str]:
        """Menge aller relevanten URLs (normalisiert)."""
        return {e.normalized_url() for e in self._entries if e.relevant}

    @property
    def total_relevant(self) -> int:
        """Anzahl relevanter Seiten im Goldstandard."""
        return len(self.relevant_urls)

    @property
    def total_entries(self) -> int:
        """Gesamtanzahl annotierter Seiten."""
        return len(self._entries)

    def _domain_matches(self, crawled_urls: List[str]) -> bool:
        """
        Grobe Plausibilitaetspruefung: pruefit ob wenigstens eine gecrawlte
        URL zur annotierten Domain passt. Hilft, Domain-Mismatches
        (z.B. 'gemeindesinn.de' vs. annotiert 'gemeinde-sinn.de')
        fruehzeitig sichtbar zu machen statt sie in Recall=0.0 zu verstecken.
        """
        if not self.domain:
            return True
        target = self.domain.lower().replace("www.", "")
        for u in crawled_urls:
            netloc = _normalize_for_compare(u).split("/")[0]
            if target in netloc or netloc in target:
                return True
        return False

    def compute_recall(self, crawled_urls: List[str]) -> float:
        """
        Berechnet Recall des Crawlers gegen diesen Goldstandard.

        Recall = gefundene relevante URLs / alle relevanten URLs im Goldstandard

        Args:
            crawled_urls: Liste aller vom Crawler besuchten URLs

        Returns:
            Recall ∈ [0.0, 1.0], oder 0.0 wenn Goldstandard leer ist
        """
        if self.total_relevant == 0:
            return 0.0

        crawled_normalized = {_normalize_for_compare(u) for u in crawled_urls}
        found_relevant = self.relevant_urls & crawled_normalized
        recall = round(len(found_relevant) / self.total_relevant, 4)

        # Diagnose: wenn Recall trotz vorhandenem Goldstandard und vorhandenen
        # gecrawlten URLs exakt 0.0 ist, liegt hoechstwahrscheinlich ein
        # Domain-Mismatch oder Formatierungsfehler vor. Beispiele ausgeben,
        # damit die Ursache sofort sichtbar ist statt stillschweigend 0.0.
        if recall == 0.0 and crawled_normalized:
            gs_sample = list(self.relevant_urls)[:3]
            crawled_sample = list(crawled_normalized)[:3]
            print("  [GOLDSTANDARD-DEBUG] Recall=0.0 trotz vorhandener Daten:")
            print(f"    Goldstandard-Domain:   {self.domain}")
            print(f"    Goldstandard-Beispiele: {gs_sample}")
            print(f"    Gecrawlte Beispiele:    {crawled_sample}")
            if not self._domain_matches(crawled_urls):
                print(
                    "    -> WARNUNG: Keine der gecrawlten URLs enthaelt die "
                    f"Goldstandard-Domain '{self.domain}'. Vermutlich Domain-Mismatch "
                    "(z.B. Bindestrich-Schreibweise oder falsche Szenario-Zuordnung) "
                    "-- Recall ist in diesem Fall nicht aussagekraeftig."
                )
            else:
                print(
                    "    -> Domain stimmt grundsaetzlich ueberein. Pruefe Pfad-Tiefe "
                    "(_MAX_PATH_DEPTH), max_pages-Budget oder ob die Zielseiten "
                    "ueberhaupt innerhalb des Crawl-Radius liegen."
                )

        return recall

    def compute_f1(self, precision: float, crawled_urls: List[str]) -> float:
        """
        Berechnet F1-Score aus Precision (Harvest Rate) und Recall gegen Goldstandard.

        Args:
            precision:    Harvest Rate des Crawlers (= Precision beim Focused Crawling)
            crawled_urls: Liste aller gecrawlten URLs

        Returns:
            F1-Score ∈ [0.0, 1.0]
        """
        recall = self.compute_recall(crawled_urls)
        if precision + recall == 0:
            return 0.0
        return round(2 * (precision * recall) / (precision + recall), 4)

    def category_distribution(self) -> Dict[str, int]:
        """Gibt Verteilung der Kategorien im Goldstandard zurueck."""
        dist: Dict[str, int] = {}
        for e in self._entries:
            if e.relevant and e.kategorie:
                dist[e.kategorie] = dist.get(e.kategorie, 0) + 1
        return dist

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "annotator": self.annotator,
            "date": self.date,
            "total_entries": self.total_entries,
            "total_relevant": self.total_relevant,
            "entries": [
                {
                    "url": e.url,
                    "relevant": e.relevant,
                    "kategorie": e.kategorie,
                    "notiz": e.notiz,
                }
                for e in self._entries
            ],
        }

    def save_json(self, path: str) -> None:
        """Speichert den Goldstandard als JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"Goldstandard gespeichert: {p} ({self.total_relevant} relevante Seiten)")

    @classmethod
    def from_json(cls, path: str) -> "ReferenceCorpus":
        """Laedt einen Goldstandard aus einer JSON-Datei."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        corpus = cls(
            domain=data.get("domain", ""),
            annotator=data.get("annotator", ""),
            date=data.get("date", ""),
        )
        for e in data.get("entries", []):
            corpus.add(CorpusEntry(
                url=e["url"],
                relevant=e["relevant"],
                kategorie=e.get("kategorie", ""),
                notiz=e.get("notiz", ""),
            ))
        return corpus

    def print_summary(self) -> None:
        """Gibt eine Zusammenfassung des Goldstandards aus."""
        print(f"\n=== Goldstandard: {self.domain} ===")
        print(f"  Annotator:       {self.annotator}")
        print(f"  Datum:           {self.date}")
        print(f"  Gesamt annotiert:{self.total_entries}")
        print(f"  Davon relevant:  {self.total_relevant}")
        print(f"  Kategorie-Vert.: {self.category_distribution()}")
