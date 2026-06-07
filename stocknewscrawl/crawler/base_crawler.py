from abc import ABC, abstractmethod
import concurrent.futures

from tqdm import tqdm

from utils.utils import init_output_dirs
from content_crawler.content_utils import probe_article_date


class BaseCrawler(ABC):

    @abstractmethod
    def get_urls_of_category_page(self, category_slug: str, page_number: int) -> list:
        """
        Get list of article URLs from a listing/category page.
        @param category_slug: category identifier (slug or ID)
        @param page_number: page number (1-indexed)
        @return list of article URL strings
        """
        return []

    # ------------------------------------------------------------------ #
    # URL collection
    # ------------------------------------------------------------------ #
    def get_urls_of_category(self, category_slug: str) -> list:
        """
        Thu thập URL của 1 chuyên mục.

        - Nếu self.start_date được set ("YYYY-MM-DD") → duyệt page TUẦN TỰ.
          Sau mỗi page, probe ngày của URL CUỐI cùng (cũ nhất trên page):
            * Nếu ngày < start_date → dừng (đã chạm mốc).
            * Nếu page rỗng → dừng (hết listing).
        - Nếu start_date rỗng → giữ cơ chế song song cũ.

        Dedup theo self.done_urls (nếu có) để bỏ luôn URL đã crawl.
        """
        start_date = getattr(self, "start_date", "") or ""
        done_urls = getattr(self, "done_urls", set()) or set()

        if not start_date:
            return self._collect_parallel(category_slug, done_urls)
        return self._collect_sequential(category_slug, start_date, done_urls)

    def _collect_parallel(self, category_slug: str, done_urls: set) -> list:
        args = (
            [category_slug] * self.total_pages,
            range(1, self.total_pages + 1),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            results = list(
                tqdm(executor.map(self.get_urls_of_category_page, *args),
                     total=self.total_pages, desc=f"Pages [{category_slug}]")
            )
        urls = sum(results, [])
        urls = [u for u in urls if u not in done_urls]
        return list(dict.fromkeys(urls))  # dedup giữ thứ tự

    def _collect_sequential(self, category_slug: str, start_date: str, done_urls: set) -> list:
        all_urls = []
        seen = set()
        empty_streak = 0

        pbar = tqdm(range(1, self.total_pages + 1), desc=f"Pages [{category_slug}]")
        for page_num in pbar:
            page_urls = self.get_urls_of_category_page(category_slug, page_num)
            if not page_urls:
                empty_streak += 1
                if empty_streak >= 2:
                    self.logger.info(f"  [{category_slug}] Stop: 2 empty pages in a row at p{page_num}")
                    break
                continue
            empty_streak = 0

            new_urls = [u for u in page_urls if u not in seen and u not in done_urls]
            for u in new_urls:
                seen.add(u)
            all_urls.extend(new_urls)

            # Probe ngày của URL cuối trên page (cũ nhất) để biết đã chạm mốc chưa
            probe_url = page_urls[-1]
            article_date = probe_article_date(probe_url)
            if article_date:
                pbar.set_postfix_str(f"last={article_date}")
                if article_date < start_date:
                    self.logger.info(
                        f"  [{category_slug}] Reached start_date {start_date} at p{page_num} "
                        f"(last={article_date}). Stopping."
                    )
                    break
        pbar.close()
        return all_urls

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def start_crawling(self):
        """Entry point: collect URLs for all configured categories and save to files."""
        urls_dpath, _ = init_output_dirs(self.output_dpath)
        total_urls = 0

        categories = self.get_categories()
        for slug, label in categories.items():
            self.logger.info(f"Collecting URLs for category: {label} ({slug})")
            urls = self.get_urls_of_category(slug)
            self.logger.info(f"  Found {len(urls)} URLs for [{label}]")

            safe_label = label.replace(" ", "_").replace("/", "-")
            out_fpath = f"{urls_dpath}/{safe_label}.txt"
            with open(out_fpath, "w", encoding="utf-8") as f:
                f.write("\n".join(urls))

            self.logger.info(f"  Saved to {out_fpath}")
            total_urls += len(urls)

        self.logger.info(f"Done. Total URLs collected: {total_urls}")

    @abstractmethod
    def get_categories(self) -> dict:
        """Return dict of {slug: label} for all categories to crawl."""
        return {}
