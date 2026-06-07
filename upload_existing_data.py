"""
upload_existing_data.py
========================
Script chạy MỘT LẦN — upload toàn bộ dữ liệu cũ lên Supabase.

Bước 1: Tạo buckets + Upload raw files lên Storage
Bước 2: ETL & Insert vào database theo đúng schema

Cách dùng:
    python upload_existing_data.py                     # Chạy tất cả
    python upload_existing_data.py --step buckets      # Chỉ tạo buckets
    python upload_existing_data.py --step upload       # Chỉ upload raw files
    python upload_existing_data.py --step companies    # Chỉ ETL companies
    python upload_existing_data.py --step dim_time     # Chỉ ETL dim_time
    python upload_existing_data.py --step vn30         # Chỉ ETL vn30_constituents
    python upload_existing_data.py --step prices       # Chỉ ETL stock_prices
    python upload_existing_data.py --step news         # Chỉ ETL news_links + news_content
    python upload_existing_data.py --step sentiment    # Chỉ ETL sentiment results
    python upload_existing_data.py --step all_db       # Chỉ ETL tất cả (không upload)
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipeline.config import (
    NEWS_CONTENT_CSV, NEWS_LINKS_CSV,
    STOCK_PRICES_CSV, VN30_CONSTITUENTS_CSV, COMPANIES_CSV,
    ALL_TRAIN_JSONL, PHOBERT_MODEL_DIR,
    BUCKET_RAW_NEWS, BUCKET_RAW_PRICES,
    BUCKET_RAW_SENTIMENT, BUCKET_ML_ARTIFACTS,
    CHUNK_SIZE,
)
from pipeline.supabase_client import (
    sb, ensure_buckets, upload_to_bucket,
    upsert_batch, insert_batch,
    log_pipeline_run, update_pipeline_run,
)

# ═══════════════════════════════════════════════════════════════════════
# STEP 1: Create Buckets + Upload Raw Files
# ═══════════════════════════════════════════════════════════════════════

def step_create_buckets():
    """Tạo tất cả buckets trên Supabase Storage."""
    print("\n" + "=" * 60)
    print("  📦 STEP: Create Storage Buckets")
    print("=" * 60)
    ensure_buckets()


def step_upload_raw_files():
    """Upload các file raw lên Supabase Storage."""
    print("\n" + "=" * 60)
    print("  ☁️  STEP: Upload Raw Files to Supabase Storage")
    print("=" * 60)

    today = datetime.now().strftime("%Y-%m-%d")

    uploads = [
        # (bucket, remote_path, local_path, content_type)
        (BUCKET_RAW_NEWS, f"existing/{today}/news_content.csv",
         NEWS_CONTENT_CSV, "text/csv"),
        (BUCKET_RAW_NEWS, f"existing/{today}/news_links.csv",
         NEWS_LINKS_CSV, "text/csv"),
        (BUCKET_RAW_SENTIMENT, f"existing/{today}/all_train.jsonl",
         ALL_TRAIN_JSONL, "application/jsonl"),
        (BUCKET_ML_ARTIFACTS, "phobert/config.json",
         PHOBERT_MODEL_DIR / "config.json", "application/json"),
        (BUCKET_ML_ARTIFACTS, "phobert/training_args.bin",
         PHOBERT_MODEL_DIR / "training_args.bin", "application/octet-stream"),
        (BUCKET_ML_ARTIFACTS, "phobert/tokenizer_config.json",
         PHOBERT_MODEL_DIR / "tokenizer_config.json", "application/json"),
    ]

    ok = 0
    for bucket, rpath, lpath, ctype in uploads:
        lpath = Path(lpath)
        if not lpath.exists():
            print(f"  ⏭️  Skip (not found): {lpath}")
            continue
        # Skip files > 50MB for free tier
        size_mb = lpath.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            print(f"  ⏭️  Skip (too large {size_mb:.0f}MB): {lpath.name}")
            continue
        if upload_to_bucket(bucket, rpath, lpath, ctype):
            ok += 1

    print(f"\n  Upload done: {ok}/{len(uploads)} files")


# ═══════════════════════════════════════════════════════════════════════
# STEP 2: ETL — Companies
# ═══════════════════════════════════════════════════════════════════════

def step_companies():
    """Insert companies từ supabase_ready/companies.csv."""
    print("\n" + "=" * 60)
    print("  🏢 STEP: ETL Companies")
    print("=" * 60)

    if not COMPANIES_CSV.exists():
        print(f"  ❌ File not found: {COMPANIES_CSV}")
        return

    df = pd.read_csv(COMPANIES_CSV)
    df = df[["symbol", "company_name"]].dropna(subset=["symbol"])
    df["symbol"] = df["symbol"].str.strip()
    df["company_name"] = df["company_name"].fillna("").str.strip()

    rows = df.to_dict("records")
    n = upsert_batch("companies", rows, on_conflict="symbol")
    print(f"  ✅ Companies: {n}/{len(rows)} upserted")


# ═══════════════════════════════════════════════════════════════════════
# STEP 3: ETL — dim_time
# ═══════════════════════════════════════════════════════════════════════

def step_dim_time():
    """Tạo dim_time từ min date → max date trong stock_prices."""
    print("\n" + "=" * 60)
    print("  📅 STEP: ETL dim_time")
    print("=" * 60)

    # Determine date range from stock prices
    if STOCK_PRICES_CSV.exists():
        sample = pd.read_csv(STOCK_PRICES_CSV, usecols=["date"], nrows=100_000)
        dates = pd.to_datetime(sample["date"])
        min_date = dates.min().date()
        max_date = dates.max().date()
    else:
        min_date = date(2020, 1, 1)
        max_date = date.today()

    # Extend range a bit
    min_date = min(min_date, date(2020, 1, 1))
    max_date = max(max_date, date.today() + timedelta(days=30))

    print(f"  Date range: {min_date} → {max_date}")

    rows = []
    current = min_date
    while current <= max_date:
        rows.append({
            "date": current.isoformat(),
            "year": current.year,
            "quarter": (current.month - 1) // 3 + 1,
            "month": current.month,
            "day": current.day,
            "day_of_week": current.isoweekday(),  # 1=Mon, 7=Sun
            "is_weekend": current.isoweekday() >= 6,
        })
        current += timedelta(days=1)

    n = upsert_batch("dim_time", rows, on_conflict="date")
    print(f"  ✅ dim_time: {n}/{len(rows)} upserted")


# ═══════════════════════════════════════════════════════════════════════
# STEP 4: ETL — VN-30 Constituents
# ═══════════════════════════════════════════════════════════════════════

def step_vn30():
    """Insert vn30_constituents."""
    print("\n" + "=" * 60)
    print("  📊 STEP: ETL vn30_constituents")
    print("=" * 60)

    if not VN30_CONSTITUENTS_CSV.exists():
        print(f"  ❌ File not found: {VN30_CONSTITUENTS_CSV}")
        return

    df = pd.read_csv(VN30_CONSTITUENTS_CSV)
    # Only keep columns matching schema
    keep = ["id", "symbol", "from_date", "to_date"]
    df = df[[c for c in keep if c in df.columns]]
    df["symbol"] = df["symbol"].str.strip()

    # Convert dates
    df["from_date"] = pd.to_datetime(df["from_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    mask = df["to_date"].notna() & (df["to_date"].astype(str).str.strip() != "")
    df.loc[mask, "to_date"] = pd.to_datetime(df.loc[mask, "to_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df.loc[~mask, "to_date"] = None

    rows = df.to_dict("records")
    # Replace NaN with None for JSON
    for row in rows:
        for k, v in row.items():
            if pd.isna(v):
                row[k] = None

    n = upsert_batch("vn30_constituents", rows, on_conflict="id")
    print(f"  ✅ vn30_constituents: {n}/{len(rows)} upserted")


# ═══════════════════════════════════════════════════════════════════════
# STEP 5: ETL — Stock Prices (large file — chunked)
# ═══════════════════════════════════════════════════════════════════════

def step_prices():
    """Insert stock_prices từ CSV lớn, theo chunks."""
    print("\n" + "=" * 60)
    print("  💰 STEP: ETL stock_prices (chunked)")
    print("=" * 60)

    if not STOCK_PRICES_CSV.exists():
        print(f"  ❌ File not found: {STOCK_PRICES_CSV}")
        return

    run_id = log_pipeline_run("etl_prices", source="upload_existing")
    total = 0
    failed = 0
    chunk_num = 0

    for chunk in pd.read_csv(STOCK_PRICES_CSV, chunksize=CHUNK_SIZE):
        chunk_num += 1

        # Keep only schema columns
        cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
        existing = [c for c in cols if c in chunk.columns]
        chunk = chunk[existing].copy()

        # Clean
        chunk["symbol"] = chunk["symbol"].str.strip()
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        chunk["volume"] = chunk["volume"].fillna(0).astype(int)
        for col in ["open", "high", "low", "close"]:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        # Drop rows with missing essential data
        chunk = chunk.dropna(subset=["symbol", "date"])

        rows = chunk.to_dict("records")
        # Clean NaN
        for row in rows:
            for k, v in row.items():
                try:
                    if pd.isna(v):
                        row[k] = None
                except (TypeError, ValueError):
                    pass

        n = upsert_batch("stock_prices", rows, on_conflict="symbol,date")
        total += n
        failed += len(rows) - n
        print(f"  ⏳ Chunk {chunk_num}: {n}/{len(rows)} OK (total: {total:,})")

    if run_id:
        update_pipeline_run(run_id, "success", total, failed)
    print(f"  ✅ stock_prices: {total:,} rows total")


# ═══════════════════════════════════════════════════════════════════════
# STEP 6: ETL — News (news_links + news_content)
# ═══════════════════════════════════════════════════════════════════════

def step_news():
    """Insert news_links + news_content từ CSV crawler."""
    print("\n" + "=" * 60)
    print("  📰 STEP: ETL news_links + news_content")
    print("=" * 60)

    run_id = log_pipeline_run("etl_news", source="upload_existing")

    # ── news_links ─────────────────────────────────────────────────
    total_links = 0
    if NEWS_LINKS_CSV.exists():
        df_links = pd.read_csv(NEWS_LINKS_CSV)
        cols_links = ["id", "url", "title", "source", "published_at", "published_date", "status", "created_at"]
        existing_cols = [c for c in cols_links if c in df_links.columns]
        df_links = df_links[existing_cols].copy()

        # Clean
        df_links = df_links.dropna(subset=["url"])
        df_links["url"] = df_links["url"].str.strip()
        if "title" in df_links.columns:
            df_links["title"] = df_links["title"].fillna("")

        rows_links = df_links.to_dict("records")
        for row in rows_links:
            for k, v in row.items():
                try:
                    if pd.isna(v):
                        row[k] = None
                except (TypeError, ValueError):
                    pass

        total_links = upsert_batch("news_links", rows_links, on_conflict="id")
        print(f"  ✅ news_links: {total_links}/{len(rows_links)} upserted")
    else:
        print(f"  ⏭️  news_links.csv not found")

    # ── news_content ────────────────────────────────────────────────
    total_content = 0
    if NEWS_CONTENT_CSV.exists():
        df_content = pd.read_csv(NEWS_CONTENT_CSV)
        cols_content = ["news_id", "content", "summary", "image_url", "created_at"]
        existing_cols = [c for c in cols_content if c in df_content.columns]
        df_content = df_content[existing_cols].copy()

        df_content = df_content.dropna(subset=["news_id"])
        df_content["news_id"] = df_content["news_id"].astype(int)

        rows_content = df_content.to_dict("records")
        for row in rows_content:
            for k, v in row.items():
                try:
                    if pd.isna(v):
                        row[k] = None
                except (TypeError, ValueError):
                    pass

        total_content = upsert_batch("news_content", rows_content, on_conflict="news_id")
        print(f"  ✅ news_content: {total_content}/{len(rows_content)} upserted")
    else:
        print(f"  ⏭️  news_content.csv not found")

    if run_id:
        update_pipeline_run(run_id, "success", total_links + total_content)


# ═══════════════════════════════════════════════════════════════════════
# STEP 7: ETL — Sentiment Results + Entities (from all_train.jsonl)
# ═══════════════════════════════════════════════════════════════════════

def step_sentiment():
    """
    Insert news_sentiment_results + news_entities + news_stock_mapping
    từ all_train.jsonl (output của Gemini pipeline).
    """
    print("\n" + "=" * 60)
    print("  🧠 STEP: ETL sentiment + entities from Gemini data")
    print("=" * 60)

    if not ALL_TRAIN_JSONL.exists():
        print(f"  ❌ File not found: {ALL_TRAIN_JSONL}")
        return

    run_id = log_pipeline_run("etl_sentiment", source="upload_existing")

    records = []
    with open(ALL_TRAIN_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    print(f"  Loaded {len(records)} records from all_train.jsonl")

    # ── news_sentiment_results ──────────────────────────────────────
    sentiment_rows = []
    entity_rows = []
    mapping_rows = []

    for rec in records:
        news_id = rec.get("id")
        if news_id is None:
            continue

        # Sentiment result
        label = rec.get("label", 1)  # 0/1/2
        label_text = rec.get("label_text", "trung_tinh")
        confidence = rec.get("confidence", 0.5)
        quality = rec.get("quality", "MEDIUM")

        # Convert confidence to prob distribution (approximate)
        probs = {0: 0.0, 1: 0.0, 2: 0.0}
        probs[label] = confidence
        remaining = 1.0 - confidence
        other_labels = [l for l in [0, 1, 2] if l != label]
        for ol in other_labels:
            probs[ol] = remaining / 2

        sentiment_rows.append({
            "news_id": news_id,
            "predicted_label": label,
            "label_text": label_text,
            "confidence_score": round(confidence, 4),
            "sentiment_score": round(confidence * (1 if label == 2 else (-1 if label == 0 else 0)), 4),
            "prob_negative": round(probs[0], 4),
            "prob_neutral": round(probs[1], 4),
            "prob_positive": round(probs[2], 4),
            "cap_do_tac_dong": rec.get("cap_do_tac_dong"),
            "khung_thoi_gian": rec.get("khung_thoi_gian"),
            "quality": quality,
            "model_version": "gemini-3-flash-voting-5x",
        })

        # ── Entities ────────────────────────────────────────────────
        entities = rec.get("entities", [])
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            entity_name = ent.get("entity", "").strip()
            if not entity_name:
                continue
            entity_rows.append({
                "news_id": news_id,
                "entity": entity_name,
                "type": ent.get("type", "unknown"),
                "sentiment": ent.get("sentiment", "neutral"),
            })

            # If entity looks like a stock symbol (2-4 uppercase letters)
            if ent.get("type") == "stock" and len(entity_name) <= 4 and entity_name.isupper():
                mapping_rows.append({
                    "news_id": news_id,
                    "symbol": entity_name,
                    "relevance": 0.8,
                    "sentiment_score": round(confidence * (1 if label == 2 else (-1 if label == 0 else 0)), 4),
                })

    # Insert sentiment
    n_sent = upsert_batch("news_sentiment_results", sentiment_rows, on_conflict="news_id")
    print(f"  ✅ news_sentiment_results: {n_sent}/{len(sentiment_rows)}")

    # Insert entities
    n_ent = insert_batch("news_entities", entity_rows)
    print(f"  ✅ news_entities: {n_ent}/{len(entity_rows)}")

    # Insert stock mappings (only for symbols that exist in companies)
    if mapping_rows:
        # Get valid symbols
        try:
            res = sb.table("companies").select("symbol").execute()
            valid_symbols = {r["symbol"] for r in res.data} if res.data else set()
            mapping_rows = [r for r in mapping_rows if r["symbol"] in valid_symbols]
        except Exception:
            pass
        n_map = insert_batch("news_stock_mapping", mapping_rows)
        print(f"  ✅ news_stock_mapping: {n_map}/{len(mapping_rows)}")

    if run_id:
        update_pipeline_run(run_id, "success", n_sent + n_ent)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

ALL_STEPS = {
    "buckets": step_create_buckets,
    "upload": step_upload_raw_files,
    "companies": step_companies,
    "dim_time": step_dim_time,
    "vn30": step_vn30,
    "prices": step_prices,
    "news": step_news,
    "sentiment": step_sentiment,
}

DB_STEPS = ["companies", "dim_time", "vn30", "prices", "news", "sentiment"]


def main():
    parser = argparse.ArgumentParser(
        description="Upload existing data to Supabase (one-time)"
    )
    parser.add_argument(
        "--step",
        choices=list(ALL_STEPS.keys()) + ["all", "all_db"],
        default="all",
        help="Chọn bước cần chạy (mặc định: all)",
    )
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  🚀 UPLOAD EXISTING DATA TO SUPABASE")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Step: {args.step}")
    print(f"{'=' * 60}")

    if args.step == "all":
        for name, func in ALL_STEPS.items():
            func()
    elif args.step == "all_db":
        for name in DB_STEPS:
            ALL_STEPS[name]()
    else:
        ALL_STEPS[args.step]()

    print(f"\n{'=' * 60}")
    print(f"  🎉 DONE!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
