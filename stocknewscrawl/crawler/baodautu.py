"""
Crawler for baodautu.vn
Target sections:
  - Đầu tư tài chính : /dau-tu-tai-chinh-d6/
  - Chứng khoán      : /chung-khoan-d16/
  - Thị trường       : /thi-truong-d5/

Pagination: {category_url}/p{N}  e.g. /dau-tu-tai-chinh-d6/p2
Article links: a[href] with classes fs32, fs22, fs18, fs16 that are title links.
"""

import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from crawler.base_crawler import BaseCrawler


class BaoDauTuCrawler(BaseCrawler):

    BASE_URL = "https://baodautu.vn"

    # slug → (url_path, label)
    CATEGORY_MAP = {
        "dau-tu-tai-chinh-d6": ("dau-tu-tai-chinh-d6", "Đầu tư tài chính"),
        "chung-khoan-d16":     ("chung-khoan-d16",      "Chứng khoán"),
        "thi-truong-d5":       ("thi-truong-d5",        "Thị trường"),
    }

    # CSS selectors for article title links (excludes image/thumb links)
    TITLE_SELECTORS = [
        "a.fs32.fbold",
        "a.fs22.fbold",
        "a.fs18.fbold",
        "a.fs16.fbold",
        "a.title_thumb_square",
    ]

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)

    def get_categories(self) -> dict:
        return {slug: info[1] for slug, info in self.CATEGORY_MAP.items()}

    def get_urls_of_category_page(self, category_slug: str, page_number: int) -> list:
        """
        Fetch one page of article URLs from baodautu.vn.
        URL pattern: https://baodautu.vn/{path}/p{page_number}
        Page 1 has no suffix.
        """
        path = self.CATEGORY_MAP[category_slug][0]
        if page_number == 1:
            page_url = f"{self.BASE_URL}/{path}/"
        else:
            page_url = f"{self.BASE_URL}/{path}/p{page_number}"

        try:
            resp = requests.get(page_url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as e:
            self.logger.warning(f"[baodautu] Failed to fetch {page_url}: {e}")
            return []

        soup = BeautifulSoup(resp.content, "html.parser")
        urls = []
        seen = set()

        for selector in self.TITLE_SELECTORS:
            for tag in soup.select(selector):
                href = tag.get("href", "").strip()
                if not href or href in seen:
                    continue
                # Skip non-article links (images, category links, etc.)
                if href.startswith("/") and href.count("/") < 2:
                    continue  # top-level category link
                full_url = href if href.startswith("http") else self.BASE_URL + href
                if full_url not in seen:
                    urls.append(full_url)
                    seen.add(full_url)

        if not urls:
            self.logger.info(f"[baodautu] No articles on {page_url} (may be last page)")

        return urls
