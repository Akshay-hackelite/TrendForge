"""Sitemap URL discovery for creator / brand websites (no HTML scrape).

Implementation lives in app.services.topics.
"""

from app.services.topics import scrape_doctor_website

__all__ = ["scrape_doctor_website"]
