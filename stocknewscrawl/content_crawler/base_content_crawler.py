"""
Base class for article content crawlers.
Each subclass implements extract_article(url) → dict with fields:
  - title        (str)
  - summary      (str)   : mô tả / sapo
  - content      (str)   : toàn bộ nội dung bài
  - image_url    (str)   : ảnh đại diện (có thể rỗng)
  - published_at (str)   : ISO timestamp  e.g. "2024-01-15T10:30:00"
  - published_date (str) : "YYYY-MM-DD"
  - source       (str)   : tên nguồn báo
"""

from abc import ABC, abstractmethod


class BaseContentCrawler(ABC):

    @abstractmethod
    def extract_article(self, url: str) -> dict:
        """
        Fetch and parse a single article URL.
        Returns a dict with keys:
            title, summary, content, image_url,
            published_at, published_date, source
        Returns None on failure.
        """
        return None
