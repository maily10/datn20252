"""
fetch_hose_index.py — Lấy VN-Index daily từ HOSE Index API + upload Supabase.

API spec (FiinPro/FiinTrade): /Market/GetHoseIndex
Trả về JSON với các trường: TradingDate, IndexValue, OpenIndex, CloseIndex,
HighestIndex, LowestIndex, TotalVolume, TotalValue, ForeignBuy*, ForeignSell*, …

Cấu hình trong `.env` (gốc dự án `e:/20252/datn/crawler/.env`):
    HOSE_API_BASE   = https://core.fiintrade.vn          # ví dụ — đổi cho khớp provider
    HOSE_API_TOKEN  = (nếu API cần auth Bearer/Cookie)
    HOSE_INDEX_CODE = VNINDEX (mặc định)

Chạy:
    python pipeline/fetch_hose_index.py                  # lấy 30 ngày gần nhất
    python pipeline/fetch_hose_index.py --days 365       # lấy 1 năm
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

THIS = Path(__file__).resolve()
DASH = THIS.parent.parent
ROOT = DASH.parent

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import requests
from supabase import create_client

SB = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

BASE = os.getenv("HOSE_API_BASE", "").rstrip("/")
TOKEN = os.getenv("HOSE_API_TOKEN", "")
INDEX_CODE = os.getenv("HOSE_INDEX_CODE", "VNINDEX")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_hose_index(start: str, end: str) -> list[dict]:
    """Gọi API /Market/GetHoseIndex để lấy chuỗi VN-Index từ start → end."""
    if not BASE:
        log("⚠️ HOSE_API_BASE chưa cấu hình trong .env — bỏ qua fetch (xem hướng dẫn ở docstring).")
        return []
    url = f"{BASE}/Market/GetHoseIndex"
    params = {
        "ComGroupCode": INDEX_CODE,
        "From": start, "To": end,
        "Type": 0,                  # daily
    }
    headers = {"Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = data if isinstance(data, list) else data.get("data") or data.get("items") or []
        log(f"  Lấy được {len(rows)} dòng từ {url}")
        return rows
    except Exception as e:
        log(f"❌ Fetch lỗi: {type(e).__name__}: {str(e)[:160]}")
        return []


def normalize_row(r: dict) -> dict | None:
    """Map field API → cột bảng Supabase."""
    td = r.get("TradingDate")
    if not td:
        return None
    return {
        "com_group_code": r.get("ComGroupCode") or INDEX_CODE,
        "trading_date": td[:10],
        "index_value": r.get("IndexValue"),
        "index_change": r.get("IndexChange"),
        "percent_index_change": r.get("PercentIndexChange"),
        "reference_index": r.get("ReferenceIndex"),
        "open_index": r.get("OpenIndex"),
        "close_index": r.get("CloseIndex"),
        "highest_index": r.get("HighestIndex"),
        "lowest_index": r.get("LowestIndex"),
        "total_match_volume": r.get("TotalMatchVolume"),
        "total_match_value": r.get("TotalMatchValue"),
        "total_deal_volume": r.get("TotalDealVolume"),
        "total_deal_value": r.get("TotalDealValue"),
        "total_volume": r.get("TotalVolume"),
        "total_value": r.get("TotalValue"),
        "total_stock_up_price": r.get("TotalStockUpPrice"),
        "total_stock_down_price": r.get("TotalStockDownPrice"),
        "total_stock_no_change": r.get("TotalStockNoChangePrice"),
        "foreign_buy_value_total": r.get("ForeignBuyValueTotal"),
        "foreign_buy_volume_total": r.get("ForeignBuyVolumeTotal"),
        "foreign_sell_value_total": r.get("ForeignSellValueTotal"),
        "foreign_sell_volume_total": r.get("ForeignSellVolumeTotal"),
    }


def upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    SB.table("hose_index_daily").upsert(rows, on_conflict="com_group_code,trading_date").execute()
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="số ngày lùi về quá khứ")
    args = parser.parse_args()

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    log(f"Fetch HOSE Index {INDEX_CODE} từ {start} → {end} ...")
    raw = fetch_hose_index(start, end)
    if not raw:
        log("Không có dữ liệu — bỏ qua upload.")
        return

    rows = [r for r in (normalize_row(x) for x in raw) if r]
    log(f"Normalized {len(rows)} dòng → upsert hose_index_daily")
    n = upsert(rows)
    log(f"✅ Upserted {n} dòng VN-Index")


if __name__ == "__main__":
    main()
