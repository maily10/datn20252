"""
Crawler for thitruongtaichinhtiente.vn
Target sections:
  - Thị trường  : /thi-truong          (channel_id = 4)
  - Chứng khoán : /thi-truong/chung-khoan  (channel_id = 231)

Pagination mechanism: AJAX via /api/getMoreArticle/
  Endpoint pattern:
    GET /api/getMoreArticle/channel_empty_{last_article_id}_{channel_id}_0
  The `last_article_id` is the numeric ID found at the end of the last article's URL.
  e.g. article URL: /ten-bai-viet-80240.html  → id = 80240

Strategy:
  1. Load page 1 HTML → extract all articles + their IDs
  2. For subsequent "pages", call the AJAX endpoint with the last seen ID
  3. Parse JSON response → extract article URLs + detect new last_id

Channel IDs discovered via browser inspection:
  - Chứng khoán : 231
  - Thị trường  : 4        (main market section)
"""

import re
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
from content_crawler.content_utils import probe_article_date


# Regex to extract numeric article ID from URL slug (e.g. /ten-bai-80240.html → 80240)
_ID_PATTERN = re.compile(r"-(\d+)\.html?$")


def _extract_id(url: str) -> str | None:
    m = _ID_PATTERN.search(url)
    return m.group(1) if m else None


class ThiTruongTaiChinhCrawler(BaseCrawler):

    BASE_URL = "https://thitruongtaichinhtiente.vn"
    API_URL = "https://thitruongtaichinhtiente.vn/api/getMoreArticle/channel_empty_{last_id}_{channel_id}_0"

    # slug → (page_path, channel_id, label)
    CATEGORY_MAP = {
        "chung-khoan":     ("thi-truong/chung-khoan", "231", "Chứng khoán"),
        "thi-truong":      ("thi-truong",             "4",   "Thị trường"),
    }

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)

    def get_categories(self) -> dict:
        return {slug: info[2] for slug, info in self.CATEGORY_MAP.items()}

    # ------------------------------------------------------------------ #
    # Override start_crawling to use AJAX-aware pagination instead of     #
    # the thread-pool page-number approach in BaseCrawler                 #
    # ------------------------------------------------------------------ #
    def start_crawling(self):
        from utils.utils import init_output_dirs
        urls_dpath, _ = init_output_dirs(self.output_dpath)
        total_urls = 0

        for slug, (page_path, channel_id, label) in self.CATEGORY_MAP.items():
            self.logger.info(f"Collecting URLs for category: {label}")
            urls = self._collect_category(page_path, channel_id)
            self.logger.info(f"  Found {len(urls)} URLs for [{label}]")

            safe_label = label.replace(" ", "_").replace("/", "-")
            out_fpath = f"{urls_dpath}/{safe_label}.txt"
            with open(out_fpath, "w", encoding="utf-8") as f:
                f.write("\n".join(urls))
            self.logger.info(f"  Saved to {out_fpath}")
            total_urls += len(urls)

        self.logger.info(f"Done. Total URLs collected: {total_urls}")

    def _collect_category(self, page_path: str, channel_id: str) -> list:
        """Collect all article URLs using HTML + AJAX pagination."""
        start_date = getattr(self, "start_date", "") or ""
        done_urls = getattr(self, "done_urls", set()) or set()

        all_urls = []
        seen = set()
        headers = {"User-Agent": "Mozilla/5.0"}

        # -- Step 1: Load initial page HTML --
        page_url = f"{self.BASE_URL}/{page_path}"
        try:
            resp = requests.get(page_url, timeout=15, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            self.logger.warning(f"[thitruong] Failed to fetch {page_url}: {e}")
            return []

        soup = BeautifulSoup(resp.content, "html.parser")

        # Extract article links visible on the initial HTML page
        link_tags = soup.select("h2.c-title a, h3.c-title a, .c-title a, h2 a, h3 a")
        last_id = None
        for tag in link_tags:
            href = tag.get("href", "").strip()
            if not href or ".html" not in href:
                continue
            full_url = href if href.startswith("http") else self.BASE_URL + "/" + href.lstrip("/")
            if full_url not in seen and full_url not in done_urls:
                all_urls.append(full_url)
                seen.add(full_url)
            art_id = _extract_id(full_url)
            if art_id:
                last_id = art_id  # keep updating to get the last (smallest) ID on page

        self.logger.info(f"  [thitruong] Page 1 HTML: {len(all_urls)} articles, last_id={last_id}")

        if last_id is None:
            self.logger.warning(f"  [thitruong] Could not determine last_id, stopping pagination")
            return all_urls

        # Early-stop: probe ngày bài cuối page 1
        if start_date and all_urls:
            probe_date = probe_article_date(all_urls[-1])
            if probe_date and probe_date < start_date:
                self.logger.info(
                    f"  [thitruong] Reached start_date {start_date} on page 1 (last={probe_date})"
                )
                return all_urls

        # -- Step 2: AJAX pagination --
        for page_num in range(2, self.total_pages + 1):
            api_url = self.API_URL.format(last_id=last_id, channel_id=channel_id)
            try:
                resp = requests.get(api_url, timeout=15, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                self.logger.warning(f"[thitruong] AJAX failed {api_url}: {e}")
                break

            if not data:
                self.logger.info(f"  [thitruong] AJAX returned empty, stopping at page {page_num}")
                break

            batch_urls = []
            batch_last_id = None
            for item in data:
                # JSON fields observed: FriendlyTitle, Id, or construct URL from FriendlyTitle + Id
                friendly = item.get("FriendlyTitle") or item.get("friendly_title") or ""
                art_id = str(item.get("Id") or item.get("id") or "")

                if friendly and art_id:
                    article_url = f"{self.BASE_URL}/{friendly}-{art_id}.html"
                    if article_url not in seen and article_url not in done_urls:
                        batch_urls.append(article_url)
                        seen.add(article_url)
                    batch_last_id = art_id  # last item = smallest id

            all_urls.extend(batch_urls)
            self.logger.info(f"  [thitruong] Page {page_num} AJAX: {len(batch_urls)} articles")

            # Early-stop khi bài cuối batch cũ hơn start_date
            if start_date and batch_urls:
                probe_date = probe_article_date(batch_urls[-1])
                if probe_date and probe_date < start_date:
                    self.logger.info(
                        f"  [thitruong] Reached start_date {start_date} at AJAX page {page_num} "
                        f"(last={probe_date}). Stopping."
                    )
                    break

            if batch_last_id:
                last_id = batch_last_id
            else:
                break  # can't continue without a new last_id

        return all_urls

    # Satisfy abstract method (not used directly, overridden via start_crawling)
    def get_urls_of_category_page(self, category_slug: str, page_number: int) -> list:
        return []
