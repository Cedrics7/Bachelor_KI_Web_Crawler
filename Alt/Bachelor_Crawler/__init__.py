# Bachelor_Crawler – Aufbauend auf crawler_js
from .scraper_bachelor import get_subpages
from .robots_checker import RobotsChecker
from .privacy_guard import PrivacyGuard

__all__ = ["get_subpages", "RobotsChecker", "PrivacyGuard"]
