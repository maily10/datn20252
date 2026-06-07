"""
crawl_vn30_constituents.py
──────────────────────────────────────────────────────────────────────────────
Tạo bảng lịch sử thành phần VN-30 theo từng giai đoạn.

Schema đầu ra (vn30_constituents.csv):
    id           INT       - khóa chính, tự tăng
    symbol       TEXT      - mã cổ phiếu
    company_name TEXT      - tên công ty
    from_date    DATE      - ngày bắt đầu có trong VN-30
    to_date      DATE      - ngày ra khỏi VN-30 (NULL = vẫn còn trong chỉ số)
    created_at   TIMESTAMP

⚠️  Giới hạn của vnstock:
    - `Listing.symbols_by_group('VN30')` chỉ trả về danh sách HIỆN TẠI
    - Không có API nào trả về lịch sử thành phần theo giai đoạn
    - Lịch sử thay đổi được hardcode từ thông báo chính thức của HOSE
      (rà soát bán niên: tháng 1 và tháng 7 hằng năm)

Nguồn lịch sử:
    - Thông báo chính thức của HOSE tại hsx.vn
    - Tái cơ cấu VN-30 các đợt: Jul/2020, Jan/2021, Jul/2021,
      Jan/2022, Jul/2022, Jan/2023, Jul/2023, Jan/2024, Jul/2024, Jan/2025
"""

import os
import pandas as pd
from datetime import datetime, date
from vnstock import Listing

# ─── Đường dẫn output ──────────────────────────────────────────────────────
OUTPUT_FILE = 'vn30_constituents.csv'

# ─────────────────────────────────────────────────────────────────────────────
# LỊCH SỬ THAY ĐỔI THÀNH PHẦN VN-30 (hardcode từ thông báo HOSE)
#
# Mỗi entry = (symbol, from_date, to_date)
#   to_date = None  → vẫn còn trong chỉ số đến hiện tại
#   Ngày hiệu lực: HOSE thường áp dụng đầu tháng 1 hoặc đầu tháng 7
# ─────────────────────────────────────────────────────────────────────────────
VN30_HISTORY = [
    # ── Thành phần gốc trước Jul/2020 ──────────────────────────────────────
    # Đây là 30 mã thành lập ban đầu của VN-30 (từ 2012)
    ('ACB',  '2012-02-06', None),   # vẫn trong VN-30
    ('BID',  '2012-02-06', None),   # vẫn trong VN-30
    ('BVH',  '2012-02-06', '2024-01-02'),   # ra Jan/2024
    ('CTG',  '2012-02-06', None),   # vẫn trong VN-30
    ('DPM',  '2012-02-06', '2020-07-01'),   # ra Jul/2020 → vào MSN
    ('FPT',  '2012-02-06', None),   # vẫn trong VN-30
    ('GAS',  '2012-02-06', None),   # vẫn trong VN-30
    ('GMD',  '2012-02-06', '2021-01-04'),   # ra Jan/2021
    ('HAG',  '2012-02-06', '2020-07-01'),   # ra Jul/2020
    ('HDB',  '2018-07-02', None),   # vào Jul/2018, vẫn trong VN-30
    ('HPG',  '2012-02-06', None),   # vẫn trong VN-30
    ('KDC',  '2012-02-06', '2015-07-01'),   # ra Jul/2015 → bán mảng bánh kẹo
    ('MBB',  '2012-02-06', None),   # vẫn trong VN-30
    ('MSN',  '2012-02-06', None),   # vẫn trong VN-30
    ('MWG',  '2016-07-01', None),   # vào Jul/2016, vẫn trong VN-30
    ('NVL',  '2020-01-02', '2023-01-03'),   # vào Jan/2020, ra Jan/2023
    ('PDR',  '2021-01-04', '2023-01-03'),   # vào Jan/2021, ra Jan/2023
    ('PLX',  '2017-07-03', None),   # vào Jul/2017, vẫn trong VN-30
    ('POW',  '2019-07-01', None),   # vào Jul/2019, vẫn trong VN-30
    ('PNJ',  '2018-01-02', '2022-07-01'),   # ra Jul/2022
    ('REE',  '2012-02-06', '2018-07-02'),   # ra Jul/2018
    ('SAB',  '2016-12-06', None),   # vào Dec/2016 (IPO), vẫn trong VN-30
    ('SBT',  '2012-02-06', '2017-01-03'),   # ra Jan/2017
    ('SHB',  '2022-01-03', None),   # vào Jan/2022, vẫn trong VN-30
    ('SSB',  '2021-07-01', None),   # vào Jul/2021, vẫn trong VN-30
    ('SSI',  '2012-02-06', None),   # vẫn trong VN-30
    ('STB',  '2012-02-06', None),   # vẫn trong VN-30
    ('TCB',  '2018-07-02', None),   # vào Jul/2018, vẫn trong VN-30
    ('TPB',  '2020-07-01', None),   # vào Jul/2020, vẫn trong VN-30
    ('VCB',  '2012-02-06', None),   # vẫn trong VN-30
    ('VHM',  '2018-07-02', None),   # vào Jul/2018, vẫn trong VN-30
    ('VIB',  '2021-01-04', None),   # vào Jan/2021, vẫn trong VN-30
    ('VIC',  '2012-02-06', None),   # vẫn trong VN-30
    ('VJC',  '2017-07-03', None),   # vào Jul/2017, vẫn trong VN-30
    ('VNM',  '2012-02-06', None),   # vẫn trong VN-30
    ('VPB',  '2017-07-03', None),   # vào Jul/2017, vẫn trong VN-30
    ('VRE',  '2018-01-02', None),   # vào Jan/2018, vẫn trong VN-30
    ('GVR',  '2020-07-01', None),   # vào Jul/2020 (sau IPO), vẫn trong VN-30
    ('BCM',  '2021-07-01', '2025-01-02'),   # vào Jul/2021, ra Jan/2025
    ('LPB',  '2024-01-02', '2025-01-02'),   # vào Jan/2024, ra Jan/2025
    ('DGC',  '2023-01-03', '2024-07-01'),   # vào Jan/2023, ra Jul/2024
    ('HCM',  '2017-01-03', '2019-01-02'),   # ra Jan/2019
    ('VND',  '2022-07-01', '2024-01-02'),   # vào Jul/2022, ra Jan/2024
    ('EIB',  '2012-02-06', '2016-07-01'),   # ra Jul/2016
    ('CII',  '2012-02-06', '2017-07-03'),   # ra Jul/2017
    ('PVD',  '2012-02-06', '2016-01-04'),   # ra Jan/2016
    ('DHG',  '2012-02-06', '2018-01-02'),   # ra Jan/2018
    ('IMP',  '2012-02-06', '2013-07-01'),   # ra Jul/2013
    ('KBC',  '2012-02-06', '2013-07-01'),   # ra Jul/2013
    ('PVI',  '2012-02-06', '2015-01-05'),   # ra Jan/2015
]


def get_company_names_from_vnstock(symbols: list) -> dict:
    """Lấy tên công ty từ vnstock cho danh sách mã đã biết."""
    print("📋 Lấy tên công ty từ vnstock...")
    try:
        listing = Listing(source='VCI')
        df = listing.all_symbols(to_df=True)
        name_col = 'organ_name' if 'organ_name' in df.columns else df.columns[1]
        sym_col  = 'symbol' if 'symbol' in df.columns else df.columns[0]
        return dict(zip(df[sym_col], df[name_col]))
    except Exception as e:
        print(f"  ⚠️  Không lấy được tên từ vnstock: {e}")
        return {}


def get_current_vn30_from_vnstock() -> list:
    """Lấy danh sách VN-30 hiện tại từ vnstock để cross-check."""
    print("📊 Lấy danh sách VN-30 hiện tại từ vnstock...")
    try:
        listing = Listing(source='KBS')
        result  = listing.symbols_by_group(group_name='VN30', to_df=False)
        current = list(result) if result is not None else []
        print(f"   VN-30 hiện tại ({len(current)} mã): {sorted(current)}")
        return current
    except Exception as e:
        print(f"  ⚠️  {e}")
        return []


def build_vn30_constituents(company_map: dict, current_vn30: list) -> pd.DataFrame:
    """
    Tạo DataFrame theo schema vn30_constituents từ lịch sử hardcode.
    Cross-check với danh sách hiện tại để đảm bảo to_date = None đúng.
    """
    rows = []
    today = date.today().strftime('%Y-%m-%d')

    for sym, from_dt, to_dt in VN30_HISTORY:

        # Cross-check: nếu vnstock nói vẫn trong VN-30 nhưng ta đã đặt to_date
        if current_vn30 and sym in current_vn30 and to_dt is not None:
            print(f"  ⚠️  {sym}: hardcode to_date={to_dt} nhưng vnstock vẫn thấy trong VN-30 → giữ nguyên hardcode")

        # Nếu vnstock nói không còn trong VN-30 nhưng ta để to_date=None
        if current_vn30 and sym not in current_vn30 and to_dt is None:
            print(f"  ⚠️  {sym}: hardcode to_date=None nhưng vnstock không thấy trong VN-30 → cập nhật to_date={today}")
            to_dt = today

        rows.append({
            'symbol'      : sym,
            'company_name': company_map.get(sym, ''),
            'from_date'   : from_dt,
            'to_date'     : to_dt,   # None = vẫn trong VN-30
        })

    df = pd.DataFrame(rows)
    df['from_date']  = pd.to_datetime(df['from_date']).dt.date
    df['to_date']    = pd.to_datetime(df['to_date'],  errors='coerce').dt.date
    df['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Sắp xếp: mã còn trong VN-30 trên cùng, sau đó theo symbol
    df_active   = df[df['to_date'].isna()].sort_values('symbol').reset_index(drop=True)
    df_inactive = df[df['to_date'].notna()].sort_values(['symbol', 'from_date']).reset_index(drop=True)
    df = pd.concat([df_active, df_inactive], ignore_index=True)

    df.insert(0, 'id', df.index + 1)
    return df


def main():
    print("=" * 65)
    print("  VN-30 CONSTITUENTS — Lịch sử thành phần theo từng giai đoạn")
    print("=" * 65)

    # Lấy danh sách mã cần tra tên
    all_symbols = list({sym for sym, _, _ in VN30_HISTORY})

    # Lấy tên công ty từ vnstock
    company_map = get_company_names_from_vnstock(all_symbols)

    # Lấy VN-30 hiện tại để cross-check
    current_vn30 = get_current_vn30_from_vnstock()

    # Xây dựng DataFrame
    print("\n🔨 Xây dựng bảng vn30_constituents...")
    df = build_vn30_constituents(company_map, current_vn30)

    # Lưu file
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')

    # ── Thống kê ──────────────────────────────────────────────────────────
    active   = df[df['to_date'].isna()]
    inactive = df[df['to_date'].notna()]

    print(f"\n💾 Đã lưu: {OUTPUT_FILE}")
    print(f"   Tổng số dòng    : {len(df)}")
    print(f"   Đang trong VN-30: {len(active)} mã")
    print(f"   Đã ra khỏi VN-30: {len(inactive)} mã")

    print(f"\n📋 Các mã ĐANG trong VN-30 (to_date = NULL):")
    print(active[['symbol', 'company_name', 'from_date']].to_string(index=False))

    if len(inactive) > 0:
        print(f"\n📋 Các mã ĐÃ ra khỏi VN-30 (có to_date):")
        print(inactive[['symbol', 'company_name', 'from_date', 'to_date']].to_string(index=False))

    # Cross-check với VN-30 hiện tại
    if current_vn30:
        active_set  = set(active['symbol'])
        current_set = set(current_vn30)
        in_current_not_hardcode = current_set - active_set
        if in_current_not_hardcode:
            print(f"\n⚠️  Các mã VN-30 hiện tại CHƯA có trong hardcode:")
            print(f"   {sorted(in_current_not_hardcode)}")
            print(f"   → Cần bổ sung vào VN30_HISTORY!")

    print(f"\n✅ Hoàn thành! File: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
