"""
Crawler for vneconomy.vn
Target sections (under Chứng khoán):
  - Doanh nghiệp niêm yết : /doanh-nghiep-niem-yet.htm
  - Thị trường             : /thi-truong-chung-khoan.htm
  - Đầu tư                : /dau-tu-chung-khoan.htm
  - Khung pháp lý         : /khung-phap-ly-chung-khoan.htm

Pagination: ?page=N
Article links: h2.story__title > a  (relative URL, needs base_url prefix)
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


class VnEconomyCrawler(BaseCrawler):

    BASE_URL = "https://vneconomy.vn"

    # Category slug → (url_path, label)
    CATEGORY_MAP = {
        "doanh-nghiep-niem-yet": ("doanh-nghiep-niem-yet.htm",     "Doanh nghiệp niêm yết"),
        "thi-truong-chung-khoan": ("thi-truong-chung-khoan.htm",    "Thị trường"),
        "dau-tu-chung-khoan":    ("dau-tu-chung-khoan.htm",         "Đầu tư"),
        "khung-phap-ly-chung-khoan": ("khung-phap-ly-chung-khoan.htm", "Khung pháp lý"),
    }

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)

    def get_categories(self) -> dict:
        return {slug: info[1] for slug, info in self.CATEGORY_MAP.items()}

    def get_urls_of_category_page(self, category_slug: str, page_number: int) -> list:
        """
        Fetch one page of article URLs from vneconomy.vn.
        URL pattern: https://vneconomy.vn/{path}?page={page_number}
        Article links:  h2.story__title > a   (href is relative)
        """
        path = self.CATEGORY_MAP[category_slug][0]
        page_url = f"{self.BASE_URL}/{path}?page={page_number}"

        try:
            resp = requests.get(page_url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as e:
            self.logger.warning(f"[vneconomy] Failed to fetch {page_url}: {e}")
            return []

        soup = BeautifulSoup(resp.content, "html.parser")

        # Primary: <h2 class="story__title"><a href="...">
        title_tags = soup.select("h2.story__title a")
        # Fallback: <a class="link-layer-imt">
        if not title_tags:
            title_tags = soup.select("a.link-layer-imt")

        urls = []
        for tag in title_tags:
            href = tag.get("href", "").strip()
            if not href:
                continue
            full_url = href if href.startswith("http") else self.BASE_URL + "/" + href.lstrip("/")
            urls.append(full_url)

        if not urls:
            self.logger.info(f"[vneconomy] No articles on {page_url} (may be last page)")

        return urls
