import asyncio
import hashlib
import re
import httpx
from selectolax.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# --- KONFIGURATION ---
KEYWORDS = {
    "sanierung": r"sanierungsgebiet|stadtsanierung|fördergebiet",
    "neubau": r"neubaugebiet|bebauungsplan|b-plan|erschließung",
    "privatisierung": r"grundstücksverkauf|veräußerung|liegenschaften",
    "tiefbau": r"tiefbau|straßenbau|kanalsanierung|brückenbau"
}

# Erweiterung der Keywords um Portale
DISCOVERY_DOMAINS = [
    "bauleitplanung", "geoportal", "uvp-verbund",
    "landesplanung"
]

class SmartCrawler:
    def __init__(self, base_url, db_pool):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.db_pool = db_pool
        self.visited_urls = set()

    def get_hash(self, text):
        return hashlib.sha256(text.encode()).hexdigest()

    def calculate_relevance(self, text, url):
        """Prüft, ob die Seite für unsere Themen relevant ist."""
        combined = f"{text} {url}".lower()
        for topic, pattern in KEYWORDS.items():
            if re.search(pattern, combined):
                return topic
        return None

    async def extract_and_queue_links(self, tree, current_url, depth):
        for link in tree.css("a"):
            href = link.attributes.get("href")
            if not href: continue

            full_url = urljoin(current_url, href)
            target_domain = urlparse(full_url).netloc

            # Fall A: Interne Seite (Deep Crawl)
            if target_domain == self.domain:
                await self.queue.put((full_url, depth + 1))

            # Fall B: Discovery (Externe relevante Portale)
            elif any(d in target_domain for d in DISCOVERY_DOMAINS):
                if not await self.db.is_blacklisted(full_url):
                    print(f"[+] Discovery: Neues Portal gefunden -> {full_url}")
                    await self.db.add_discovery_target(full_url, source=current_url)


    async def crawl(self, current_url, depth=0, max_depth=3):
        if depth > max_depth or current_url in self.visited_urls:
            return

        self.visited_urls.add(current_url)
        print(f"[*] Crawling: {current_url} (Tiefe: {depth})")

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(current_url)
                if response.status_code != 200:
                    return

                html = response.text
                tree = HTMLParser(html)

                # 1. Content Hashing (Effizienz-Check)
                content_text = tree.body.text() if tree.body else ""
                new_hash = self.get_hash(content_text)

                # Check DB (Pseudocode für DB-Logik)
                # is_changed = await self.check_db_hash(current_url, new_hash)

                # 2. Relevanz-Check
                topic = self.calculate_relevance(content_text, current_url)

                if topic:
                    print(f"[!] TREFFER: {topic} auf {current_url}")
                    # Hier würde der Aufruf an GPT-4o-mini erfolgen
                    # await self.save_to_db(current_url, topic, new_hash)

                # 3. Discovery: Neue Links finden
                if depth < max_depth:
                    tasks = []
                    for link in tree.css("a"):
                        href = link.attributes.get("href")
                        if not href: continue

                        full_url = urljoin(self.base_url, href)
                        # Nur auf der gleichen Domain bleiben
                        if urlparse(full_url).netloc == self.domain:
                            tasks.append(self.crawl(full_url, depth + 1))

                    await asyncio.gather(*tasks)

        except Exception as e:
            print(f"[!] Fehler bei {current_url}: {e}")


async def main():
    # Hier deine Start-URLs der 1000 Kommunen laden
    start_urls = ["https://www.beispiel-kommune.de"]

    # DB Pool initialisieren (z.B. mit asyncpg)
    db_pool = None

    crawler_tasks = [SmartCrawler(url, db_pool).crawl(url) for url in start_urls]
    await asyncio.gather(*crawler_tasks)


if __name__ == "__main__":
    asyncio.run(main())