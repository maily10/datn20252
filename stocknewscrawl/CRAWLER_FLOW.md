# Luồng thu thập dữ liệu tin tức (Crawler Pipeline)

> Module `stocknewscrawl/` — thu thập tin tức tài chính/chứng khoán từ 4 báo điện tử Việt Nam, xuất ra 2 file CSV chuẩn hoá (links + content) sẵn sàng nạp vào Supabase.

## 1. Tổng quan kiến trúc — pipeline 2 pha

Hệ thống tách thành **2 pha độc lập**, chạy tuần tự:

```
┌──────────────────────────────────────────────────────────────────┐
│  PHA 1 — THU THẬP URL (URL Collection)                             │
│  main.py / crawl_all_sites.py  →  crawler/*                        │
│  Input : crawler_config.yml                                        │
│  Output: result/urls/*.txt  (danh sách URL bài viết)               │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHA 2 — TRÍCH XUẤT NỘI DUNG (Content Extraction)                  │
│  crawl_content.py  →  content_crawler/*                            │
│  Input : result/urls/*.txt                                         │
│  Output: vnstocknewsdata/news_links.csv  +  news_content.csv       │
└──────────────────────────────────────────────────────────────────┘
```

**Lý do tách 2 pha:**
- Thu thập URL nhanh (chỉ đọc trang danh mục), trích nội dung chậm (đọc từng bài) → tách ra để retry/resume độc lập.
- Có thể crawl URL của cả 4 nguồn trước, rồi mới trích nội dung hàng loạt.

## 2. Các thành phần (component) và vai trò

| Thành phần | File | Vai trò |
|---|---|---|
| **Config** | `crawler_config.yml` | Khai báo nguồn, số trang, mốc ngày, số luồng |
| **Entry (1 site)** | `main.py` | Chạy thu thập URL cho 1 nguồn |
| **Entry (4 sites)** | `crawl_all_sites.py` | Chạy thu thập URL cho tất cả nguồn, gộp kết quả |
| **URL Factory** | `crawler/factory.py` | Chọn crawler theo `webname` (Factory Pattern) |
| **Base URL crawler** | `crawler/base_crawler.py` | Logic chung: duyệt trang, early-stop, dedup (Template Method) |
| **URL crawler/nguồn** | `crawler/{vneconomy,baodautu,...}.py` | Cài đặt cách lấy URL + phân trang riêng từng site |
| **Entry trích nội dung** | `crawl_content.py` | Đọc URL → trích nội dung → ghi CSV (đa luồng) |
| **Content Factory** | `content_crawler/factory.py` | Chọn content crawler theo **domain** của URL |
| **Base content crawler** | `content_crawler/base_content_crawler.py` | Hợp đồng `extract_article(url) → dict` |
| **Content crawler/nguồn** | `content_crawler/{...}_content.py` | Cài đặt cách trích title/summary/content/date riêng từng site |
| **Tiện ích chung** | `content_crawler/content_utils.py` | Bóc nội dung, parse ngày, probe ngày, kiểm tra trùng/ngày |
| **Logger** | `logger/log.py` | Cấu hình log |
| **Utils** | `utils/utils.py` | Đọc config YAML, tạo thư mục |

## 3. PHA 1 — Thu thập URL (chi tiết)

### 3.1 Điểm vào và cấu hình
`crawl_all_sites.py` đọc `crawler_config.yml`:
```yaml
webname: ...          # nguồn (bị override khi chạy all-sites)
total_pages: 200      # số trang tối đa duyệt mỗi chuyên mục
start_date: "2022-01-01"   # mốc dừng sớm (early-stop)
end_date: ""          # lọc ở pha 2
num_workers: 5        # số luồng song song
```

### 3.2 Luồng xử lý (`base_crawler.py`)
Với mỗi nguồn → mỗi **chuyên mục** (category) → gọi `get_urls_of_category()`:

```
start_crawling()                                  # base_crawler.py:96
  └─ for category in get_categories():            # vd: Chứng khoán, Thị trường, Đầu tư
       urls = get_urls_of_category(category)
       ghi → result/urls/{category}.txt
```

`get_urls_of_category()` có **2 chế độ**:

**A. Tuần tự + early-stop** (khi `start_date` ≠ "") — `_collect_sequential()`:
```
for page = 1 → total_pages:
    page_urls = get_urls_of_category_page(category, page)   # đặc thù từng site
    nếu page rỗng 2 lần liên tiếp → DỪNG (hết bài)
    bỏ URL đã có trong done_urls (resume)
    probe_article_date(url_cuối_trang)                       # lấy ngày bài cũ nhất trang
    nếu ngày < start_date → DỪNG (đã chạm mốc 2022)
```

**B. Song song** (khi `start_date` = "") — `_collect_parallel()`:
```
ThreadPoolExecutor(num_workers) chạy đồng thời total_pages trang
gộp + dedup
```

### 3.3 Cơ chế đặc thù từng nguồn (`get_urls_of_category_page`)
| Nguồn | Phân trang | Selector lấy link bài |
|---|---|---|
| VnEconomy | `?page=N` | `h2.story__title a` |
| Báo Đầu Tư | `/pN` (trang 1 không hậu tố) | `a.fs32.fbold`, `a.fs22.fbold`, … |
| Thời Báo TC | AJAX "Xem thêm" → thử `?page=N`, `/page/N`, `?p=N` | `a.article-link` |
| Thị trường TC | (tương tự) | (tương tự) |

### 3.4 Đầu ra Pha 1
File text, mỗi dòng 1 URL: `result/urls/{site}_{category}.txt`
→ `crawl_all_sites.py` gộp toàn bộ + đếm URL duy nhất.

## 4. PHA 2 — Trích xuất nội dung (chi tiết)

### 4.1 Luồng xử lý (`crawl_content.py`)
```
1. Đọc tất cả result/urls/*.txt → list URL duy nhất
2. Load done_urls từ news_links.csv (resume → bỏ URL đã crawl)
3. ThreadPoolExecutor(num_workers):
     mỗi URL:
       crawler = get_content_crawler(url)        # chọn theo domain
       article = crawler.extract_article(url)    # trả dict 7 trường
       sleep(0.2)                                # lịch sự, tránh bị chặn
       LỌC: published_date ∈ [start_date, end_date]?
            (bài thiếu ngày → vẫn giữ, nhượng bộ)
       ghi 1 dòng → news_links.csv
       ghi 1 dòng → news_content.csv
       flush ngay (an toàn nếu gián đoạn)
```

### 4.2 `extract_article(url)` — trích 1 bài (đặc thù từng nguồn)
Thứ tự đọc (QUAN TRỌNG về mặt kỹ thuật):
```
1. title       ← <meta og:title>  (fallback: <h1>)
2. summary     ← <meta og:description>  (fallback: .sapo)
3. image_url   ← <meta og:image>
4. published_at/date  ← meta article:published_time
                        fallback: thẻ ngày trong <body> (đặc thù site)
5. content     ← extract_best_content(soup)   ← GỌI CUỐI vì xoá DOM in-place
```
> Lưu ý thiết kế: `extract_best_content` **xoá noise trong DOM ngay tại chỗ**, nên mọi trường khác (đặc biệt **ngày** nằm trong `<body>`) phải đọc **trước** bước này — nếu không sẽ mất.

Selector ngày theo nguồn:
| Nguồn | Nguồn ngày |
|---|---|
| VnEconomy | `<meta article:published_time>` (trong `<head>`) |
| Báo Đầu Tư | `<span class="post-time">` (vd "- 14/04/2026 21:04") |
| Thời Báo TC | `<span class="format_date">` + `<span class="format_time">` |

### 4.3 Tiện ích chung (`content_utils.py`)
- **`extract_best_content(soup)`** — bóc toàn bộ nội dung:
  1. Xoá thẻ noise (`nav/header/footer/aside/script/figure`…)
  2. Xoá element có class/id noise (`sidebar/comment/share/ads`…) qua regex
  3. Gom **tất cả `<p>`** còn lại, lọc đoạn quá ngắn / footer (©, "tòa soạn"…)
- **`parse_datetime(raw)`** — parser đa định dạng (ISO, `dd/mm/yyyy`, `HH:MM dd/mm/yyyy`, US format…) → `(ISO timestamp, YYYY-MM-DD)`; có regex bắt ngày dự phòng.
- **`probe_article_date(url)`** — tải nhanh 1 bài, chỉ lấy ngày (cho early-stop ở Pha 1).
- **`check_article()`** — gộp kiểm tra trùng URL + ngày trong khoảng.

## 5. Schema dữ liệu đầu ra (2 file CSV liên kết)

**`news_links.csv`** — metadata bài viết:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | int | Khoá chính, tự tăng |
| `url` | text | URL bài (unique) |
| `title` | text | Tiêu đề |
| `source` | text | Tên nguồn báo |
| `published_at` | timestamp | Thời điểm đăng (ISO) |
| `published_date` | date | Ngày đăng (YYYY-MM-DD) |
| `status` | text | "published" |
| `created_at` | timestamp | Thời điểm crawl |

**`news_content.csv`** — nội dung bài viết:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `news_id` | int | Khoá ngoại → `news_links.id` |
| `content` | text | Toàn bộ nội dung |
| `summary` | text | Sapo/mô tả |
| `image_url` | text | Ảnh đại diện |
| `created_at` | timestamp | Thời điểm crawl |

→ Liên kết **1-1** qua `news_links.id = news_content.news_id`.

## 6. Bốn nguồn dữ liệu

| Nguồn | Domain | Chuyên mục crawl |
|---|---|---|
| VnEconomy | vneconomy.vn | Doanh nghiệp niêm yết, Thị trường, Đầu tư, Khung pháp lý |
| Báo Đầu Tư | baodautu.vn | Đầu tư tài chính, Chứng khoán, Thị trường |
| Thời Báo Tài Chính VN | thoibaotaichinhvietnam.vn | Tài chính, Đầu tư, Chứng khoán, Thị trường |
| Thị trường Tài chính Tiền tệ | thitruongtaichinhtiente.vn | (tài chính, chứng khoán) |

## 7. Kỹ thuật & design pattern dùng trong hệ thống

| Kỹ thuật | Áp dụng | Lợi ích |
|---|---|---|
| **Factory Pattern** | `get_crawler(webname)`, `get_content_crawler(url)` | Thêm nguồn mới không sửa code lõi |
| **Template Method** | `BaseCrawler`/`BaseContentCrawler` định nghĩa khung, subclass cài chi tiết | Tái sử dụng logic duyệt trang/early-stop |
| **Đa luồng** | `ThreadPoolExecutor` ở cả 2 pha | Tăng tốc I/O-bound |
| **Resume / Incremental** | `done_urls` đọc từ CSV → bỏ bài đã crawl | Chạy tiếp không trùng |
| **Early-stop theo ngày** | `probe_article_date` + `start_date` | Không duyệt thừa quá khứ |
| **Polite crawling** | `sleep(0.2)`, User-Agent header | Giảm rủi ro bị chặn |
| **Ghi an toàn** | `flush()` mỗi dòng, append mode | Không mất data nếu gián đoạn |

## 8. Sơ đồ tuần tự (sequence) tổng thể

```
Người dùng
   │ python crawl_all_sites.py --sites vneconomy baodautu ...
   ▼
crawl_all_sites ──► get_crawler(webname) ──► SiteCrawler.start_crawling()
   │                                              │
   │                                              ▼
   │                              for category: get_urls_of_category()
   │                                  ├─ get_urls_of_category_page()  (HTTP GET trang DS)
   │                                  └─ probe_article_date()         (early-stop < start_date)
   │                                              │
   │                                              ▼
   │                                   result/urls/{site}_{cat}.txt
   ▼
Người dùng
   │ python crawl_content.py --start-date 2022-01-01
   ▼
crawl_content ──► đọc *.txt ──► ThreadPool:
       for url:
         get_content_crawler(url) ──► extract_article(url)  (HTTP GET bài)
              ├─ title/summary/image/date  (đọc từ soup nguyên)
              └─ extract_best_content       (bóc nội dung, xoá noise)
         lọc theo [start_date, end_date]
         ghi → news_links.csv + news_content.csv
```

## 9. Lệnh chạy điển hình (end-to-end)

```bash
# Pha 1 — thu thập URL 4 nguồn (đọc start_date từ config)
python crawl_all_sites.py

# hoặc chỉ vài nguồn:
python crawl_all_sites.py --sites vneconomy baodautu

# Pha 2 — trích nội dung, lọc theo ngày
python crawl_content.py --start-date 2022-01-01 --workers 5
```
