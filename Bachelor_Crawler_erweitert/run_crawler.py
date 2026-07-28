"""
Einstiegspunkt für Bachelor_Crawler_erweitert.
Konfiguration erfolgt über .env im Projektroot oder Umgebungsvariablen.
Beispiel:
    CRAWLER_LLM_ENABLED=true CRAWLER_DB_ENABLED=true python -m Bachelor_Crawler_erweitert.run_crawler
"""
from Bachelor_Crawler_erweitert.focused_crawler import FocusedCrawler

if __name__ == '__main__':
    # Optionale Overrides – Defaults kommen aus config.py / .env
    crawler = FocusedCrawler(run_id='test_run_01')
    results, report = crawler.crawl('https://example.com', max_pages=5)
    report.print_summary()
