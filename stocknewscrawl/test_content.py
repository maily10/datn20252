"""Quick test: verify content is extracted correctly from all 4 sources."""
import sys
sys.path.append('.')
from content_crawler.factory import get_content_crawler

TEST_URLS = {
    "thitruongtaichinhtiente.vn": "https://thitruongtaichinhtiente.vn/mot-ngan-hang-chi-tra-co-tuc-tien-mat-30-cao-nhat-toan-nganh-82132.html",
    "thoibaotaichinhvietnam.vn": "https://thoibaotaichinhvietnam.vn/quang-ninh-xu-ly-hon-1100-vu-buon-lau-gian-lan-thuong-mai-va-hang-gia-195658.html",
    "baodautu.vn": "https://baodautu.vn/chung-khoan-eurocapital-bi-xu-phat-d569930.html",
    "vneconomy.vn": "https://vneconomy.vn/cii-va-hfic-duoc-giao-nghien-cuu-du-an-cai-tao-xa-lo-ha-noi-2.htm",
}

for site, url in TEST_URLS.items():
    print(f"\n{'='*60}")
    print(f"Site: {site}")
    crawler = get_content_crawler(url)
    if not crawler:
        print("  ERROR: No crawler found!")
        continue
    result = crawler.extract_article(url)
    if not result:
        print("  ERROR: extract_article returned None!")
        continue
    print(f"  title   : {result['title'][:80]}")
    print(f"  summary : {result['summary'][:80]}" if result['summary'] else "  summary : (empty)")
    print(f"  content : {len(result['content'])} chars")
    print(f"  content_preview: {result['content'][:120]}" if result['content'] else "  content : NULL!")
    print(f"  pub_at  : {result['published_at']}")
    print(f"  image   : {result['image_url'][:60]}" if result['image_url'] else "  image   : (empty)")
