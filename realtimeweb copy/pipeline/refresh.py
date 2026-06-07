"""
refresh.py — Pipeline incremental "realtime" khi bật ứng dụng.

Mỗi lần chạy:
  1. Cập nhật danh sách VN30 hiện hành (vnstock Listing).
  2. Fetch giá OHLCV mới cho từng mã VN30 (từ max date trong DB → hôm nay).
  3. Tính KPI cho dữ liệu giá mới (return, MA, RSI, MACD, BB, drawdown, volatility, OBV).
  4. UPSERT lên Supabase.

KHÔNG làm: crawl tin mới + re-sentiment + re-CPD (slow, manual).
→ Để chạy thủ công khi cần:
    python ../../stocknewscrawl/main.py            # crawl tin
    python ../../test/news_sentiment/run_sentiment.py --hybrid
    python ../../analysis/detect_change_points.py
    python ../../analysis/evaluate_correlation.py
    python pipeline/upload_initial.py              # upload lại

Chạy:  python pipeline/refresh.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

THIS = Path(__file__).resolve()
DASH = THIS.parent.parent
ROOT = DASH.parent

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from supabase import create_client
SB = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

BATCH = 500


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── (1) VN30 list ─────────────────────────────────────────────────────────

def get_vn30_symbols() -> list[str]:
    """Lấy danh sách 30 mã VN30 hiện hành từ vnstock."""
    try:
        from vnstock import Listing
        syms = Listing().symbols_by_group("VN30")
        syms = list(syms) if syms is not None else []
        log(f"  VN30 hiện hành ({len(syms)} mã): {', '.join(syms[:10])}...")
        return syms
    except Exception as e:
        log(f"  ⚠️ KHÔNG lấy được VN30 từ vnstock: {type(e).__name__}: {str(e)[:120]}")
        # Fallback: lấy từ Supabase technical_indicators
        r = SB.table("technical_indicators").select("symbol").limit(2000).execute()
        syms = sorted({row["symbol"] for row in (r.data or [])})
        log(f"  Fallback từ DB: {len(syms)} mã")
        return syms


# ── (2) Fetch giá mới ─────────────────────────────────────────────────────

def get_last_date_per_symbol(symbols: list[str]) -> dict[str, str]:
    """Lấy ngày mới nhất có trong stock_prices cho mỗi mã."""
    out = {}
    for sym in symbols:
        r = (SB.table("stock_prices")
                .select("date")
                .eq("symbol", sym)
                .order("date", desc=True)
                .limit(1).execute())
        if r.data:
            out[sym] = r.data[0]["date"]
        else:
            out[sym] = "2022-01-01"
    return out


def fetch_new_prices(symbols: list[str], last_dates: dict[str, str]) -> pd.DataFrame:
    """Fetch giá từ vnstock cho mỗi mã, từ next-day(last_date) → hôm nay."""
    try:
        from vnstock import Quote
    except ImportError:
        log("  ❌ vnstock chưa cài. Bỏ qua fetch giá.")
        return pd.DataFrame()

    today = datetime.now().strftime("%Y-%m-%d")
    all_rows = []
    for i, sym in enumerate(symbols, 1):
        start = (datetime.strptime(last_dates.get(sym, "2022-01-01"), "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if start > today:
            continue
        try:
            df = Quote(symbol=sym, source="VCI").history(start=start, end=today, interval="1D")
        except Exception as e:
            log(f"  [{i}/{len(symbols)}] {sym}: lỗi {type(e).__name__}: {str(e)[:80]}")
            time.sleep(2)
            continue
        if df is None or df.empty:
            continue
        df = df.rename(columns={"time": "date"})
        df["symbol"] = sym
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        all_rows.append(df[["symbol", "date", "open", "high", "low", "close", "volume"]])
        log(f"  [{i}/{len(symbols)}] {sym}: +{len(df)} dòng ({df.date.min()} → {df.date.max()})")
        time.sleep(3.5)  # rate limit ~17 req/phút
    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


# ── (3) Tính KPI ──────────────────────────────────────────────────────────

def compute_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Tính bổ sung KPI từ giá đóng cửa. Áp dụng per-symbol."""
    out = []
    for sym, g in df.groupby("symbol", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        g["daily_return"] = g["close"].pct_change()
        g["log_return"] = np.log(g["close"] / g["close"].shift(1))
        g["ma_20"] = g["close"].rolling(20).mean()
        g["ma_50"] = g["close"].rolling(50).mean()
        g["volatility_20"] = g["log_return"].rolling(20).std()
        # RSI(14)
        delta = g["close"].diff()
        up = delta.where(delta > 0, 0.0)
        down = -delta.where(delta < 0, 0.0)
        avg_up = up.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_down = down.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_up / avg_down.replace(0, np.nan)
        g["rsi_14"] = 100 - (100 / (1 + rs))
        # MACD
        ema12 = g["close"].ewm(span=12, adjust=False).mean()
        ema26 = g["close"].ewm(span=26, adjust=False).mean()
        g["macd_line"] = ema12 - ema26
        g["macd_signal"] = g["macd_line"].ewm(span=9, adjust=False).mean()
        g["macd_hist"] = g["macd_line"] - g["macd_signal"]
        # Bollinger
        ma20 = g["ma_20"]
        sd20 = g["close"].rolling(20).std()
        g["bb_upper"] = ma20 + 2 * sd20
        g["bb_lower"] = ma20 - 2 * sd20
        g["bb_pctb"] = (g["close"] - g["bb_lower"]) / (g["bb_upper"] - g["bb_lower"]).replace(0, np.nan)
        # Drawdown
        cummax = g["close"].cummax()
        g["drawdown"] = (g["close"] - cummax) / cummax
        # OBV
        sign = np.sign(g["close"].diff()).fillna(0)
        g["obv"] = (sign * g["volume"].fillna(0)).cumsum()
        # Volume change
        g["volume_change"] = g["volume"].pct_change()
        g["timeframe"] = "1D"
        out.append(g)
    res = pd.concat(out, ignore_index=True)
    return res


# ── (4) Upload ────────────────────────────────────────────────────────────

def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert df to list of dicts, replacing NaN/Inf → None ở mức cell (JSON-safe)."""
    import math
    records = df.to_dict("records")
    for r in records:
        for k, v in list(r.items()):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = None
    return records


def upsert(table: str, rows: list[dict], on_conflict: str) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        SB.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    return total


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    log("=" * 64)
    log("PIPELINE REFRESH — incremental update")
    log("=" * 64)

    # (1) VN30
    log("\n[1/4] Lấy danh sách VN30 hiện hành")
    symbols = get_vn30_symbols()
    if not symbols:
        log("  ❌ Không có symbols để xử lý")
        return

    # (2) Fetch giá mới
    log("\n[2/4] Fetch giá mới từ vnstock (incremental)")
    last_dates = get_last_date_per_symbol(symbols)
    earliest = min(last_dates.values()) if last_dates else "—"
    log(f"  Ngày cuối tối thiểu trong DB: {earliest}")
    new_prices = fetch_new_prices(symbols, last_dates)
    if new_prices.empty:
        log("  ✓ Không có giá mới (DB đã cập nhật)")
        log("\n" + "=" * 64)
        log("✅ DONE (no new data)")
        return
    log(f"  Tổng giá mới: {len(new_prices):,} dòng")

    # Upload giá mới
    n = upsert("stock_prices", df_to_records(
        new_prices[["symbol", "date", "open", "high", "low", "close", "volume"]]
    ), on_conflict="symbol,date")
    log(f"  → stock_prices upserted {n:,}")

    # (3) Compute KPI cho dữ liệu MỚI + sát gần (cần history để tính MA/RSI)
    log("\n[3/4] Tính KPI cho dữ liệu mới")
    # Lấy 100 dòng cuối mỗi mã từ DB để có context, rồi tính KPI
    full_chunks = []
    for sym in symbols:
        r = (SB.table("stock_prices")
                .select("symbol, date, open, high, low, close, volume")
                .eq("symbol", sym).order("date", desc=False).limit(2000).execute())
        if r.data:
            full_chunks.append(pd.DataFrame(r.data))
    if full_chunks:
        full = pd.concat(full_chunks, ignore_index=True)
        kpi = compute_kpis(full)
        # Chỉ upload các dòng có ngày trong khoảng mới (last_date+1 → today)
        new_dates = set(new_prices.apply(lambda r: f"{r.symbol}|{r.date}", axis=1).tolist())
        kpi["key"] = kpi["symbol"] + "|" + kpi["date"]
        kpi_new = kpi[kpi["key"].isin(new_dates)].drop(columns="key")
        cols_keep = [
            "symbol", "date", "timeframe",
            "ma_20", "ma_50", "rsi_14",
            "macd_line", "macd_signal", "macd_hist",
            "bb_upper", "bb_lower", "bb_pctb",
            "daily_return", "log_return", "volatility_20",
            "drawdown", "volume_change", "obv",
        ]
        kpi_new = kpi_new[[c for c in cols_keep if c in kpi_new.columns]]
        n = upsert("technical_indicators", df_to_records(kpi_new), on_conflict="symbol,date,timeframe")
        log(f"  → technical_indicators upserted {n:,}")

    # (4) HOSE Index daily (VN-Index + foreign flow)
    log("\n[4/5] Fetch HOSE Index daily")
    try:
        import subprocess
        subprocess.run([sys.executable, str(THIS.parent / "fetch_hose_index.py"), "--days", "30"],
                       check=False)
    except Exception as e:
        log(f"  ⚠️ HOSE fetch lỗi: {e}")

    # (5) Note: sentiment/CPD/correlation không refresh tự động
    log("\n[5/5] Sentiment / CPD / Correlation — bỏ qua (cần chạy thủ công khi muốn cập nhật)")
    log("       Lệnh:")
    log("         python ../../test/news_sentiment/run_sentiment.py --hybrid")
    log("         python ../../analysis/detect_change_points.py")
    log("         python ../../analysis/evaluate_correlation.py")
    log("         python pipeline/upload_initial.py")

    log("\n" + "=" * 64)
    log("✅ DONE — dashboard sẽ hiển thị giá + KPI mới khi refresh")
    log("=" * 64)


if __name__ == "__main__":
    main()
