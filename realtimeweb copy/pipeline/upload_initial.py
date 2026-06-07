"""
upload_initial.py — Upload toàn bộ dữ liệu đồ án lên Supabase 1 lần.

Tables (theo thứ tự FK-safe):
  companies → dim_time → vn30_constituents
  → stock_prices → technical_indicators
  → news_links → news_content → news_stock_mapping → news_sentiment
  → daily_sentiment → change_points → correlation_summary → correlation_tests

Chiến lược:
  - News-related: DELETE all + INSERT ours với explicit ID (vì news_id phải match cross-tables).
  - Price/KPI:    UPSERT (insert nếu chưa có, update nếu trùng PK).
  - Dim:          UPSERT.

Chạy:  python pipeline/upload_initial.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────
THIS = Path(__file__).resolve()
DASH = THIS.parent.parent                  # realtimeweb copy/
ROOT = DASH.parent                          # crawler/
DATA = {
    "prices":      ROOT / "vnstockprice" / "supabase_ready" / "stock_prices.csv",
    "kpi":         ROOT / "vnstockprice" / "technical_indicators.csv",
    "vn30":        ROOT / "vnstockprice" / "vn30_constituents.csv",
    "news_links":  ROOT / "stocknewscrawl" / "vnstocknewsdata" / "news_links.csv",
    "news_content":ROOT / "stocknewscrawl" / "vnstocknewsdata" / "news_content.csv",
    "mapping":     ROOT / "test" / "news_sentiment" / "output" / "news_stock_mapping.csv",
    "sentiment":   ROOT / "test" / "news_sentiment" / "output" / "news_sentiment_hybrid.csv",
    "daily_sent":  ROOT / "analysis" / "output" / "daily_sentiment.csv",
    "change_pts":  ROOT / "analysis" / "output" / "change_points.csv",
    "corr_sum":    ROOT / "analysis" / "output" / "correlation_summary.csv",
    "corr_tests":  ROOT / "analysis" / "output" / "correlation_tests.json",
}

# ── Supabase client (service_role) ────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from supabase import create_client
SB = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

BATCH = 500


def log(msg: str) -> None:
    print(msg, flush=True)


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert df to list of dicts, replacing NaN/Inf → None ở mức cell (JSON-safe)."""
    import math
    records = df.to_dict("records")
    for r in records:
        for k, v in list(r.items()):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = None
    return records


def upsert(table: str, rows: list[dict], on_conflict: str | None = None) -> int:
    """Batched upsert. Returns # rows attempted."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        if on_conflict:
            SB.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        else:
            SB.table(table).upsert(chunk).execute()
        total += len(chunk)
        if (i // BATCH) % 10 == 0:
            log(f"    upserted {total:,}/{len(rows):,}")
    return total


def delete_all(table: str) -> None:
    """DELETE all rows from a table (PostgREST requires a filter)."""
    log(f"    DELETE {table}...")
    SB.table(table).delete().neq("news_id" if "news_id" in _table_pk(table) else "id", -999999).execute()


def _table_pk(table: str) -> str:
    """Hint for delete filter — table whose PK is news_id vs id."""
    if table in ("news_content", "news_sentiment"):
        return "news_id"
    return "id"


# ── Loaders ───────────────────────────────────────────────────────────────

def load_prices() -> pd.DataFrame:
    log("Loading stock_prices.csv ...")
    df = pd.read_csv(DATA["prices"], dtype={"symbol": str})
    df = df[["symbol", "date", "open", "high", "low", "close", "volume"]].dropna(subset=["symbol", "date"])
    # VN30 mã có technical_indicators
    kpi = pd.read_csv(DATA["kpi"], dtype={"symbol": str}, usecols=["symbol"])
    vn30 = set(kpi.symbol.unique())
    df = df[df.symbol.isin(vn30)].reset_index(drop=True)
    # Filter to thesis scope (2022+)
    df = df[df["date"] >= "2022-01-01"].reset_index(drop=True)
    log(f"  rows: {len(df):,} ({df.symbol.nunique()} mã, {df.date.min()} → {df.date.max()})")
    return df


def load_kpi() -> pd.DataFrame:
    log("Loading technical_indicators.csv ...")
    df = pd.read_csv(DATA["kpi"], dtype={"symbol": str})
    df = df.rename(columns={"macd": "macd_line"})
    # timeframe required by PK
    df["timeframe"] = "1D"
    cols_keep = [
        "symbol", "date", "timeframe",
        "ma_20", "ma_50", "rsi_14",
        "macd_line", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_pctb",
        "daily_return", "log_return", "volatility_20",
        "drawdown", "volume_change", "obv",
    ]
    df = df[[c for c in cols_keep if c in df.columns]]
    log(f"  rows: {len(df):,}")
    return df


def load_vn30() -> pd.DataFrame:
    if not DATA["vn30"].exists():
        return pd.DataFrame()
    df = pd.read_csv(DATA["vn30"])
    return df


def load_news_links() -> pd.DataFrame:
    log("Loading news_links.csv ...")
    df = pd.read_csv(DATA["news_links"], dtype=str)
    df = df.rename(columns={"id": "id"})  # already named id
    df["id"] = df["id"].astype(int)
    keep = ["id", "url", "title", "source", "published_at", "published_date", "status"]
    df = df[[c for c in keep if c in df.columns]]
    # Drop rows with no URL (PK indirect)
    df = df.dropna(subset=["url"]).drop_duplicates(subset=["id"]).reset_index(drop=True)
    log(f"  rows: {len(df):,}")
    return df


def load_news_content(valid_ids: set[int]) -> pd.DataFrame:
    log("Loading news_content.csv ...")
    df = pd.read_csv(DATA["news_content"], dtype={"news_id": int}, low_memory=False)
    keep = ["news_id", "content", "summary", "image_url"]
    df = df[[c for c in keep if c in df.columns]]
    df = df[df["news_id"].isin(valid_ids)].drop_duplicates(subset=["news_id"]).reset_index(drop=True)
    log(f"  rows: {len(df):,}")
    return df


def load_mapping(valid_ids: set[int]) -> pd.DataFrame:
    log("Loading news_stock_mapping.csv ...")
    df = pd.read_csv(DATA["mapping"], dtype={"news_id": int, "symbol": str})
    df = df[df["news_id"].isin(valid_ids)].drop_duplicates().reset_index(drop=True)
    log(f"  rows: {len(df):,}")
    return df


def load_sentiment(valid_ids: set[int]) -> pd.DataFrame:
    log("Loading news_sentiment_hybrid.csv ...")
    df = pd.read_csv(DATA["sentiment"], dtype={"news_id": int})
    df = df.drop_duplicates(subset=["news_id"])
    df = df[df["news_id"].isin(valid_ids)].reset_index(drop=True)
    log(f"  rows: {len(df):,}")
    return df


def load_daily_sentiment() -> pd.DataFrame:
    log("Loading daily_sentiment.csv ...")
    df = pd.read_csv(DATA["daily_sent"])
    log(f"  rows: {len(df):,}")
    return df


def load_change_points() -> pd.DataFrame:
    log("Loading change_points.csv ...")
    df = pd.read_csv(DATA["change_pts"])
    log(f"  rows: {len(df):,}")
    return df


def load_corr_summary() -> pd.DataFrame:
    log("Loading correlation_summary.csv ...")
    df = pd.read_csv(DATA["corr_sum"])
    log(f"  rows: {len(df):,}")
    return df


def load_corr_tests() -> dict:
    log("Loading correlation_tests.json ...")
    return json.loads(Path(DATA["corr_tests"]).read_text(encoding="utf-8"))


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    log("=" * 72)
    log("UPLOAD INITIAL DATA → SUPABASE")
    log("=" * 72)
    log(f"URL: {os.environ['SUPABASE_URL'][:45]}...")

    # ─── 1. Prices (UPSERT, on conflict (symbol, date)) ──────────────────
    log("\n[1/9] stock_prices")
    df = load_prices()
    upsert("stock_prices", df_to_records(df), on_conflict="symbol,date")

    # ─── 2. KPI/technical_indicators (UPSERT) ────────────────────────────
    log("\n[2/9] technical_indicators")
    df = load_kpi()
    upsert("technical_indicators", df_to_records(df), on_conflict="symbol,date,timeframe")

    # ─── 3. VN30 constituents (UPSERT) ───────────────────────────────────
    log("\n[3/9] vn30_constituents")
    vn30_df = load_vn30()
    if not vn30_df.empty:
        upsert("vn30_constituents", df_to_records(vn30_df))

    # ─── 4. News links (DELETE + INSERT — need explicit IDs cross-table) ─
    log("\n[4/9] news_links (clear + insert)")
    log("    DELETE news_sentiment ...")
    SB.table("news_sentiment").delete().neq("news_id", -1).execute()
    log("    DELETE news_stock_mapping ...")
    SB.table("news_stock_mapping").delete().neq("id", -1).execute()
    log("    DELETE news_content ...")
    SB.table("news_content").delete().neq("news_id", -1).execute()
    log("    DELETE news_links ...")
    SB.table("news_links").delete().neq("id", -1).execute()

    nl = load_news_links()
    valid_ids = set(nl["id"].tolist())
    upsert("news_links", df_to_records(nl))
    log("    Resetting sequence...")
    # supabase-py không có RPC để setval — bỏ qua, để Postgres tự dùng max(id)+1 trên insert tiếp theo (sẽ vẫn ok vì incremental dùng explicit id)

    # ─── 5. News content ─────────────────────────────────────────────────
    log("\n[5/9] news_content")
    nc = load_news_content(valid_ids)
    upsert("news_content", df_to_records(nc))

    # ─── 6. News stock mapping ───────────────────────────────────────────
    log("\n[6/9] news_stock_mapping")
    nm = load_mapping(valid_ids)
    # Drop id if present (let server auto-assign)
    if "id" in nm.columns:
        nm = nm.drop(columns="id")
    upsert("news_stock_mapping", df_to_records(nm), on_conflict="news_id,symbol")

    # ─── 7. News sentiment ───────────────────────────────────────────────
    log("\n[7/9] news_sentiment")
    ns = load_sentiment(valid_ids)
    upsert("news_sentiment", df_to_records(ns), on_conflict="news_id")

    # ─── 8. Daily sentiment ──────────────────────────────────────────────
    log("\n[8/9] daily_sentiment")
    ds = load_daily_sentiment()
    upsert("daily_sentiment", df_to_records(ds), on_conflict="symbol,date")

    # ─── 9. Change points + correlation ──────────────────────────────────
    log("\n[9/9] change_points + correlation_summary + correlation_tests")
    cp = load_change_points()
    if "id" in cp.columns:
        cp = cp.drop(columns="id")
    # add method column
    if "method" not in cp.columns:
        cp["method"] = "pelt_l2_c05"
    upsert("change_points", df_to_records(cp), on_conflict="symbol,change_point_date")

    cs = load_corr_summary()
    upsert("correlation_summary", df_to_records(cs), on_conflict="symbol")

    # correlation_tests: 1 row from JSON
    ct = load_corr_tests()
    obs = ct.get("observed", {})
    perm = ct.get("permutation_test", {})
    boot = ct.get("bootstrap_ci_95", {})
    scope = ct.get("scope", {})
    row = {
        "scope": "aggregate_vn30",
        "n_change_points": scope.get("n_change_points"),
        "window_before": scope.get("window_before_days"),
        "window_after": scope.get("window_after_days"),
        "coverage": obs.get("coverage"),
        "match_rate": obs.get("match_rate"),
        "permutation_n": scope.get("n_permutations"),
        "null_mean": perm.get("null_mean"),
        "null_std": perm.get("null_std"),
        "p_value_one_sided": perm.get("p_value_one_sided"),
        "p_value_two_sided": perm.get("p_value_two_sided"),
        "bootstrap_n": scope.get("n_bootstrap"),
        "bootstrap_ci_low": boot.get("lower"),
        "bootstrap_ci_high": boot.get("upper"),
        "reject_h0_at_005": perm.get("reject_H0_alpha_005"),
    }
    SB.table("correlation_tests").insert(row).execute()
    log("    correlation_tests: 1 row")

    log("\n" + "=" * 72)
    log("✅ DONE — verify trên Supabase Dashboard")
    log("=" * 72)


if __name__ == "__main__":
    main()
