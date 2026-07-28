from Bachelor_Crawler_vollstaendig.focused_crawler import FocusedCrawler

if __name__ == '__main__':
    crawler = FocusedCrawler(config={'js_rendering': False, 'max_pages': 25})
    results, report = crawler.crawl('https://example.com', max_pages=5)
    report.print_summary()
