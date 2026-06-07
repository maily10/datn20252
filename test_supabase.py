from supabase import create_client

SUPABASE_URL = "https://ojbafsimgwzoemzsqdbe.supabase.co"
SUPABASE_KEY = "sb_publishable_DHA55mg2S7TPRFR960Lg7Q_QkHa0EXO"  # sb_publishable_...

client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    # Lấy 1 dòng với tất cả cột để xem cấu trúc bảng
    res = client.table("news_content").select("*").limit(1).execute()
    print(f"✅ Kết nối thành công! Đọc được {len(res.data)} dòng.")
    if res.data:
        print("\nCác cột trong bảng news_content:")
        for col in res.data[0].keys():
            print(f"  - {col}: {str(res.data[0][col])[:80]}")
    else:
        print("Bảng đang trống (0 rows).")
except Exception as e:
    print(f"❌ Lỗi: {e}")
