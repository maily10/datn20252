"""
fetch_vn30_stock_price.py
────────────────────────────────────────────────────────────────────────────
Lọc dữ liệu giá lịch sử OHLCV cho các mã trong VN-30 từ file CSV có sẵn.

Input:
  - vn30_constituents.csv : danh sách mã, khoảng thời gian thuộc VN-30
  - stock_prices.csv      : toàn bộ dữ liệu giá OHLCV (schema: id, symbol,
                            date, open, high, low, close, volume, created_at)

Output:
  - vn30_stock_price.csv  : chỉ giữ những phiên giao dịch mà mã đó
                            đang thuộc chỉ số VN-30
                            (symbol, date, open, high, low, close, volume)
"""

import os
import pandas as pd
from datetime import date

# ─── Đường dẫn ──────────────────────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR    = os.path.join(BASE_DIR, '..', 'vnstockprice', 'processed_output_v2')
CONSTITUENTS_CSV = os.path.join(PROCESSED_DIR, 'vn30_constituents.csv')
STOCK_PRICES_CSV = os.path.join(PROCESSED_DIR, 'stock_prices.csv')
OUTPUT_FILE      = os.path.join(BASE_DIR, 'vn30_stock_price.csv')


def main():
    today = pd.Timestamp(date.today())

    # ── 1. Đọc danh sách thành phần VN-30 ───────────────────────────────────
    print(f"Đọc vn30_constituents.csv ...")
    constituents = pd.read_csv(CONSTITUENTS_CSV, parse_dates=['from_date', 'to_date'])
    print(f"  {len(constituents)} bản ghi, {constituents['symbol'].nunique()} mã duy nhất")

    # Điền to_date = hôm nay cho các mã vẫn còn trong chỉ số
    constituents['to_date'] = constituents['to_date'].fillna(today)

    # ── 2. Đọc stock_prices.csv (file lớn ~334 MB) ──────────────────────────
    print("Đọc stock_prices.csv (có thể mất vài giây) ...")
    prices = pd.read_csv(
        STOCK_PRICES_CSV,
        usecols=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'],
        parse_dates=['date'],
    )
    print(f"  {len(prices):,} dòng, {prices['symbol'].nunique()} mã")

    # ── 3. Lọc theo từng mã + khoảng thời gian thuộc VN-30 ─────────────────
    print("Lọc dữ liệu theo khoảng thời gian VN-30 ...")
    frames = []

    for _, row in constituents.iterrows():
        symbol     = row['symbol']
        from_date  = row['from_date']
        to_date    = row['to_date']

        mask = (
            (prices['symbol'] == symbol) &
            (prices['date'] >= from_date) &
            (prices['date'] <= to_date)
        )
        subset = prices.loc[mask].copy()

        if subset.empty:
            print(f"  [{symbol}] ({from_date.date()} → {to_date.date()}): không có dữ liệu")
        else:
            print(f"  [{symbol}] ({from_date.date()} → {to_date.date()}): {len(subset):,} phiên")
            frames.append(subset)

    # ── 4. Gộp, dedup, sắp xếp & xuất ─────────────────────────────────────
    if not frames:
        print("\nKhông có dữ liệu phù hợp để xuất.")
        return

    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=['symbol', 'date'])
    result = result.sort_values(['symbol', 'date']).reset_index(drop=True)

    result.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"\nXuất {len(result):,} dòng → {OUTPUT_FILE}")
    print(f"Số mã: {result['symbol'].nunique()}  |  "
          f"Từ {result['date'].min().date()}  →  {result['date'].max().date()}")


if __name__ == '__main__':
    main()
