"""
Script chuyển đổi format CSV cho việc import vào Supabase.

Đọc 3 file CSV gốc từ processed_output_v2/ và xuất ra thư mục 
supabase_ready/ với format khớp chính xác schema Supabase.

Schema Supabase:
  - companies:          symbol (text), company_name (text)
  - stock_prices:       symbol (text), date (date), open (numeric), high (numeric), 
                        low (numeric), close (numeric), volume (int8), created_at (timestamp)
  - vn30_constituents:  id (int4), symbol (text), from_date (date), to_date (date)
"""

import pandas as pd
import os
from datetime import datetime

# ─── Paths ───
INPUT_DIR = os.path.join(os.path.dirname(__file__), "processed_output_v2")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "supabase_ready")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def format_companies():
    """
    Bảng companies: symbol (text), company_name (text)
    CSV gốc đã khớp format => chỉ cần đọc và ghi lại (loại bỏ dòng trống nếu có).
    """
    print("=" * 60)
    print("📋 Xử lý bảng COMPANIES...")
    
    input_path = os.path.join(INPUT_DIR, "companies.csv")
    output_path = os.path.join(OUTPUT_DIR, "companies.csv")
    
    df = pd.read_csv(input_path)
    
    # Đảm bảo chỉ có 2 cột theo đúng schema
    df = df[["symbol", "company_name"]].copy()
    
    # Loại bỏ dòng trống
    df.dropna(subset=["symbol"], inplace=True)
    df["symbol"] = df["symbol"].str.strip()
    df["company_name"] = df["company_name"].str.strip()
    
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    
    print(f"  ✅ Đã xuất {len(df)} dòng → {output_path}")
    print(f"  📊 Columns: {list(df.columns)}")
    print(f"  🔍 Sample:\n{df.head(3).to_string(index=False)}")
    print()


def format_stock_prices():
    """
    Bảng stock_prices: symbol (text), date (date), open (numeric), high (numeric),
                       low (numeric), close (numeric), volume (int8), created_at (timestamp)
    
    CSV gốc có thêm cột 'id' => cần bỏ cột id.
    Đảm bảo:
      - date format: YYYY-MM-DD
      - open/high/low/close: numeric (giữ nguyên)
      - volume: integer
      - created_at: timestamp format
    """
    print("=" * 60)
    print("📋 Xử lý bảng STOCK_PRICES... (file lớn, có thể mất vài phút)")
    
    input_path = os.path.join(INPUT_DIR, "stock_prices.csv")
    output_path = os.path.join(OUTPUT_DIR, "stock_prices.csv")
    
    # Đọc theo chunks vì file rất lớn (~350MB, 4.6M rows)
    chunk_size = 500_000
    chunks_processed = 0
    total_rows = 0
    first_chunk = True
    
    for chunk in pd.read_csv(input_path, chunksize=chunk_size):
        # Bỏ cột 'id' — Supabase tự sinh khóa chính
        columns_to_keep = ["symbol", "date", "open", "high", "low", "close", "volume", "created_at"]
        existing_cols = [c for c in columns_to_keep if c in chunk.columns]
        chunk = chunk[existing_cols].copy()
        
        # Đảm bảo date format YYYY-MM-DD
        chunk["date"] = pd.to_datetime(chunk["date"]).dt.strftime("%Y-%m-%d")
        
        # Đảm bảo volume là integer
        chunk["volume"] = chunk["volume"].fillna(0).astype(int)
        
        # Đảm bảo open/high/low/close là numeric
        for col in ["open", "high", "low", "close"]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        
        # Ghi file — header chỉ ở chunk đầu tiên
        chunk.to_csv(
            output_path,
            mode="w" if first_chunk else "a",
            header=first_chunk,
            index=False,
            encoding="utf-8"
        )
        
        first_chunk = False
        chunks_processed += 1
        total_rows += len(chunk)
        print(f"  ⏳ Đã xử lý chunk {chunks_processed} ({total_rows:,} dòng)...")
    
    print(f"  ✅ Đã xuất {total_rows:,} dòng → {output_path}")
    
    # Hiển thị sample từ file đã ghi
    sample = pd.read_csv(output_path, nrows=3)
    print(f"  📊 Columns: {list(sample.columns)}")
    print(f"  🔍 Sample:\n{sample.to_string(index=False)}")
    print()


def format_vn30_constituents():
    """
    Bảng vn30_constituents: id (int4), symbol (text), from_date (date), to_date (date)
    
    CSV gốc có thêm: company_name, created_at => cần bỏ.
    Đảm bảo:
      - id: integer
      - from_date: YYYY-MM-DD
      - to_date: YYYY-MM-DD hoặc NULL (để trống = đang trong rổ VN30)
    """
    print("=" * 60)
    print("📋 Xử lý bảng VN30_CONSTITUENTS...")
    
    input_path = os.path.join(INPUT_DIR, "vn30_constituents.csv")
    output_path = os.path.join(OUTPUT_DIR, "vn30_constituents.csv")
    
    df = pd.read_csv(input_path)
    
    # Chỉ giữ 4 cột theo schema Supabase
    df = df[["id", "symbol", "from_date", "to_date"]].copy()
    
    # Đảm bảo id là integer
    df["id"] = df["id"].astype(int)
    
    # Đảm bảo symbol là text, strip whitespace
    df["symbol"] = df["symbol"].str.strip()
    
    # Format date — giữ NaN/null cho to_date (nếu cổ phiếu đang trong rổ VN30)
    df["from_date"] = pd.to_datetime(df["from_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    
    # to_date: có thể rỗng (đang trong rổ), giữ nguyên null
    mask_has_to_date = df["to_date"].notna() & (df["to_date"].astype(str).str.strip() != "")
    df.loc[mask_has_to_date, "to_date"] = pd.to_datetime(
        df.loc[mask_has_to_date, "to_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    df.loc[~mask_has_to_date, "to_date"] = ""  # Để trống cho Supabase tự hiểu NULL
    
    # Loại bỏ dòng trống
    df.dropna(subset=["symbol"], inplace=True)
    
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    print(f"  ✅ Đã xuất {len(df)} dòng → {output_path}")
    print(f"  📊 Columns: {list(df.columns)}")
    print(f"  🔍 Sample:\n{df.to_string(index=False)}")
    print()


def main():
    print()
    print("🚀 BẮT ĐẦU CHUYỂN ĐỔI CSV → FORMAT SUPABASE")
    print(f"📂 Input:  {INPUT_DIR}")
    print(f"📂 Output: {OUTPUT_DIR}")
    print(f"🕐 Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    format_companies()
    format_vn30_constituents()
    format_stock_prices()
    
    print("=" * 60)
    print("🎉 HOÀN THÀNH! Các file đã sẵn sàng để import vào Supabase:")
    print(f"  📄 {os.path.join(OUTPUT_DIR, 'companies.csv')}")
    print(f"  📄 {os.path.join(OUTPUT_DIR, 'stock_prices.csv')}")
    print(f"  📄 {os.path.join(OUTPUT_DIR, 'vn30_constituents.csv')}")
    print()
    print("💡 Hướng dẫn import vào Supabase:")
    print("  1. Vào Supabase Dashboard → Table Editor")
    print("  2. Chọn bảng → Import data from CSV")
    print("  3. Upload file CSV tương ứng")
    print("  Hoặc dùng Supabase CLI: supabase db import ...")


if __name__ == "__main__":
    main()
