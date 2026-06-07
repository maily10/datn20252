"""
crawl_vn_stock.py
Thu thập dữ liệu lịch sử chứng khoán Việt Nam (sàn HOSE)
Từ năm 2010 đến hiện tại, lưu vào CSV theo schema:
  - companies (symbol, company_name)
  - stock_prices (id, symbol, date, open, high, low, close, adj_close, volume, created_at)

Xử lý rate limit: tự động chờ 65 giây khi bị chặn và retry.
Checkpoint: lưu tiến độ sau mỗi mã, có thể resume nếu bị gián đoạn.
"""

import os
import time
import pandas as pd
from datetime import datetime, date
from vnstock import Listing, Quote

# ─── Cấu hình ──────────────────────────────────────────────────────────────
RATE_LIMIT_WAIT   = 65     # giây chờ khi bị rate limit (API nói chờ 53s → ta chờ 65s cho chắc)
MAX_RETRIES       = 5      # số lần retry mỗi mã
DELAY_PER_REQ    = 3.5    # giây delay giữa các request (20 req/phút → ~3s/req)
CHECKPOINT_FILE   = 'checkpoint_prices.csv'   # lưu tiến độ tạm thời
# ───────────────────────────────────────────────────────────────────────────


def is_rate_limit_error(e: Exception) -> bool:
    """Kiểm tra xem lỗi có phải do rate limit không."""
    msg = str(e).lower()
    keywords = ['rate limit', 'rate_limit', 'giới hạn', 'exceeded',
                'too many requests', '429', 'tối đa', 'wait to retry']
    return any(k in msg for k in keywords)


def _try_fetch(symbol: str, source: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Gọi API một lần, trả về DataFrame thô. Ném exception nếu lỗi."""
    quote = Quote(symbol=symbol, source=source)
    df = quote.history(start=start_date, end=end_date, interval='1D')
    return df


def fetch_with_retry(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Gọi API lấy lịch sử giá với retry tự động:
    - Rate limit      → chờ rồi retry
    - IntCastingNaNError (VCI) → fallback sang KBS (giữ NaN thay vì bỏ qua)
    - Lỗi khác        → retry tối đa MAX_RETRIES lần rồi bỏ qua
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = _try_fetch(symbol, 'VCI', start_date, end_date)
            return df

        except Exception as e:
            err_str = str(e)

            # VCI không xử lý được NaN → thử KBS (xử lý NaN mềm hơn)
            if 'IntCastingNaNError' in err_str or 'RetryError' in err_str:
                print(f"\n   🔄 VCI lỗi NaN cho {symbol}, thử KBS...", end='  ')
                try:
                    df = _try_fetch(symbol, 'KBS', start_date, end_date)
                    # Cho phép NaN ở volume/giá — không ép Int64 cứng
                    if df is not None and not df.empty:
                        for col in ['volume', 'open', 'high', 'low', 'close']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        print("✅ KBS OK")
                        return df
                    print("⚠️  KBS cũng không có dữ liệu")
                except Exception as e2:
                    print(f"❌ KBS cũng lỗi: {str(e2)[:80]}")
                return None  # cả hai nguồn đều thất bại

            if is_rate_limit_error(e):
                print(f"\n   ⏳ Rate limit! Chờ {RATE_LIMIT_WAIT}s rồi retry (lần {attempt}/{MAX_RETRIES})...")
                time.sleep(RATE_LIMIT_WAIT)
            else:
                print(f"\n   ❌ Lỗi [{type(e).__name__}]: {err_str[:120]}")
                if attempt < MAX_RETRIES:
                    time.sleep(5)
                else:
                    return None
    return None


# =============================
# 1. LẤY DANH SÁCH MÃ HOSE
# =============================
def get_hose_symbols():
    """Lấy danh sách mã cổ phiếu và tên công ty trên sàn HOSE."""
    print("📋 Đang lấy danh sách mã HOSE...")
    listing = Listing(source='VCI')
    df = listing.symbols_by_exchange(exchange='HOSE', to_df=True)

    print(f"   Columns: {df.columns.tolist()}")

    # Xác định cột symbol
    if 'symbol' in df.columns:
        sym_col = 'symbol'
    elif 'ticker' in df.columns:
        sym_col = 'ticker'
    else:
        sym_col = df.columns[0]

    # Xác định cột tên công ty
    name_col = None
    for candidate in ['organ_name', 'company_name', 'organ_short_name', 'en_organ_name']:
        if candidate in df.columns:
            name_col = candidate
            break

    # Lọc chỉ lấy stock thường (loại bỏ warrant, ETF...)
    if 'type' in df.columns:
        df = df[df['type'].str.upper().isin(['STOCK', 'ST'])]

    symbols = df[sym_col].dropna().unique().tolist()
    company_map = {}
    if name_col:
        company_map = dict(zip(df[sym_col], df[name_col]))

    print(f"✅ Tổng số mã HOSE: {len(symbols)}")
    return symbols, company_map


# =============================
# 2. CRAWL DỮ LIỆU GIÁ
# =============================
def get_done_symbols() -> set:
    """Đọc checkpoint để biết mã nào đã crawl xong, tránh crawl lại."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            df = pd.read_csv(CHECKPOINT_FILE, usecols=['symbol'])
            done = set(df['symbol'].dropna().unique())
            print(f"🔁 Resume: tìm thấy checkpoint với {len(done)} mã đã xong")
            return done
        except Exception:
            pass
    return set()


def crawl_stock_prices(symbols, start_date='2010-01-01'):
    """
    Crawl lịch sử giá OHLCV từ start_date đến hiện tại.
    - Tự động chờ khi bị rate limit và retry.
    - Lưu checkpoint sau mỗi mã (có thể resume nếu bị dừng giữa chừng).
    """
    end_date = date.today().strftime('%Y-%m-%d')
    failed   = []
    total    = len(symbols)

    # Resume: bỏ qua các mã đã crawl
    done_symbols = get_done_symbols()
    remaining    = [s for s in symbols if s not in done_symbols]
    print(f"\n📈 Cần crawl {len(remaining)}/{total} mã (đã xong: {len(done_symbols)})")
    print(f"   Thời gian: {start_date} → {end_date}")
    print(f"   Tốc độ  : ~{DELAY_PER_REQ}s/mã + chờ {RATE_LIMIT_WAIT}s khi bị rate limit\n")

    is_first_write = not os.path.exists(CHECKPOINT_FILE)

    for idx, symbol in enumerate(remaining, 1):
        print(f"[{idx:4d}/{len(remaining)}] {symbol}", end='  ')

        df = fetch_with_retry(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            print("⚠️  Không có dữ liệu")
            failed.append(symbol)
        else:
            df['symbol'] = symbol
            print(f"✅ {len(df)} ngày")

            # Lưu checkpoint ngay lập tức
            df.to_csv(
                CHECKPOINT_FILE,
                mode='w' if is_first_write else 'a',
                header=is_first_write,
                index=False,
                encoding='utf-8-sig'
            )
            is_first_write = False

        # Delay giữa các request để tránh vượt 20 req/phút
        time.sleep(DELAY_PER_REQ)

    print(f"\n📊 Hoàn thành: {len(remaining) - len(failed)}/{len(remaining)} mã thành công")
    if failed:
        print(f"⚠️  Các mã lỗi ({len(failed)}): {failed}")

    # Đọc toàn bộ checkpoint về
    if os.path.exists(CHECKPOINT_FILE):
        return pd.read_csv(CHECKPOINT_FILE)
    return pd.DataFrame()


# =============================
# 3. CHUẨN HÓA SCHEMA
# =============================
def build_companies_df(symbols, company_map):
    """Tạo DataFrame theo schema bảng companies."""
    rows = []
    for sym in symbols:
        rows.append({
            'symbol': sym,
            'company_name': company_map.get(sym, '')
        })
    return pd.DataFrame(rows)


def build_stock_prices_df(raw_df):
    """
    Chuẩn hóa DataFrame thô sang schema bảng stock_prices.
    vnstock trả về cột: time, open, high, low, close, volume (+ symbol đã gán)
    adj_close = close (vnstock chưa có cột adjusted riêng)
    """
    if raw_df.empty:
        return pd.DataFrame()

    # Xác định cột ngày
    if 'time' in raw_df.columns:
        raw_df['date'] = pd.to_datetime(raw_df['time']).dt.date
    elif 'date' in raw_df.columns:
        raw_df['date'] = pd.to_datetime(raw_df['date']).dt.date

    # Xây dựng df chuẩn
    df = pd.DataFrame()
    df['symbol']     = raw_df['symbol']
    df['date']       = raw_df['date']
    df['open']       = pd.to_numeric(raw_df.get('open'),   errors='coerce')
    df['high']       = pd.to_numeric(raw_df.get('high'),   errors='coerce')
    df['low']        = pd.to_numeric(raw_df.get('low'),    errors='coerce')
    df['close']      = pd.to_numeric(raw_df.get('close'),  errors='coerce')
    df['adj_close']  = df['close']   # vnstock chưa cung cấp adjusted close riêng
    df['volume']     = pd.to_numeric(raw_df.get('volume'), errors='coerce').astype('Int64')
    df['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Sắp xếp & đánh id
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)
    df.insert(0, 'id', df.index + 1)

    return df


# =============================
# 4. MAIN PIPELINE
# =============================
def main():
    START_DATE = '2010-01-01'

    # Bước 1: Lấy danh sách mã HOSE
    symbols, company_map = get_hose_symbols()

    # Bước 2: Tạo bảng companies
    companies_df = build_companies_df(symbols, company_map)
    companies_df.to_csv('companies.csv', index=False, encoding='utf-8-sig')
    print(f"\n💾 Đã lưu companies.csv ({len(companies_df)} công ty)")
    print(companies_df.head(3))

    # Bước 3: Crawl lịch sử giá
    raw_df = crawl_stock_prices(symbols, start_date=START_DATE)

    if raw_df.empty:
        print("\n❌ Không có dữ liệu giá nào được crawl!")
        return

    # Bước 4: Chuẩn hóa & lưu bảng stock_prices
    prices_df = build_stock_prices_df(raw_df)
    prices_df.to_csv('stock_prices.csv', index=False, encoding='utf-8-sig')

    print(f"\n💾 Đã lưu stock_prices.csv")
    print(f"   Tổng số bản ghi : {len(prices_df):,}")
    print(f"   Thời gian        : {prices_df['date'].min()} → {prices_df['date'].max()}")
    print(f"   Số mã cổ phiếu  : {prices_df['symbol'].nunique()}")
    print(f"\n📋 Mẫu dữ liệu (5 dòng đầu):")
    print(prices_df.head())


if __name__ == '__main__':
    main()