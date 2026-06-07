"""
config.py — Cấu hình tập trung cho toàn bộ pipeline.

Tải biến môi trường từ .env nếu có, hoặc dùng giá trị mặc định.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[1]  # e:\20252\datn\crawler
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "Pho_bert_test" / ".env")  # Fallback cho GOOGLE_API_KEY

# ── Supabase ───────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojbafsimgwzoemzsqdbe.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "sb_publishable_DHA55mg2S7TPRFR960Lg7Q_QkHa0EXO",
)

# ── Supabase Storage bucket names ──────────────────────────────────────
BUCKET_RAW_NEWS = "raw-news"
BUCKET_RAW_PRICES = "raw-prices"
BUCKET_RAW_SENTIMENT = "raw-sentiment"
BUCKET_ML_ARTIFACTS = "ml-artifacts"

# ── Google Gemini ──────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# ── Đường dẫn dữ liệu ────────────────────────────────────────────────
STOCKNEWS_DIR = ROOT_DIR / "stocknewscrawl"
VNSTOCKPRICE_DIR = ROOT_DIR / "vnstockprice"
PHOBERT_DIR = ROOT_DIR / "Pho_bert_test"
PHOBERT_MODEL_DIR = ROOT_DIR / "phobert_best_model"
VOLUME_DIR = ROOT_DIR / "Volume_precedes_price"

# Files
NEWS_CONTENT_CSV = STOCKNEWS_DIR / "vnstocknewsdata" / "news_content.csv"
NEWS_LINKS_CSV = STOCKNEWS_DIR / "vnstocknewsdata" / "news_links.csv"
STOCK_PRICES_CSV = VNSTOCKPRICE_DIR / "processed_output_v2" / "stock_prices.csv"
VN30_CONSTITUENTS_CSV = VNSTOCKPRICE_DIR / "processed_output_v2" / "vn30_constituents.csv"
COMPANIES_CSV = VNSTOCKPRICE_DIR / "supabase_ready" / "companies.csv"
ALL_TRAIN_JSONL = PHOBERT_DIR / "data" / "all_train.jsonl"

# ── Pipeline settings ─────────────────────────────────────────────────
CRAWL_WORKERS = 5
BATCH_SIZE = 500          # Rows per upsert batch
CHUNK_SIZE = 50_000       # Rows per CSV read chunk (for large files)
