"""Ubah file Excel di folder data/ menjadi CSV yang dibaca aplikasi.
Jalankan setiap kali tim mengubah nasabah.xlsx, transaksi.xlsx, merchant.xlsx, atau promo.xlsx."""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"
KOLOM = {
    "nasabah": ["user_id", "nama", "gender", "usia", "kota", "pekerjaan", "pendapatan_bulanan",
                "saldo_saat_ini", "tujuan", "usia_target_tujuan", "persona"],
    "transaksi": ["trx_id", "user_id", "tanggal_waktu", "arah", "kategori", "merchant_id",
                  "merchant_nama", "metode", "tujuan", "nominal", "saldo_setelah"],
    "merchant": ["merchant_id", "merchant_nama", "kategori", "kota", "status_mitra"],
    "promo": ["promo_id", "merchant_id", "kategori", "judul", "mekanisme", "nilai", "satuan",
              "min_transaksi", "maks_manfaat", "kuota_per_user", "metode_bayar", "mulai",
              "berakhir", "target_label", "bantu_nabung", "syarat"],
}

for nama, kolom in KOLOM.items():
    xlsx = DATA / f"{nama}.xlsx"
    if not xlsx.exists():
        print(f"Lewati {nama}: {xlsx.name} tidak ditemukan, CSV lama tetap dipakai.")
        continue
    df = pd.read_excel(xlsx)
    hilang = [k for k in kolom if k not in df.columns]
    if hilang:
        raise SystemExit(f"{xlsx.name} tidak memiliki kolom: {', '.join(hilang)}")
    df[kolom].to_csv(DATA / f"{nama}.csv", index=False)
    print(f"{nama}.csv diperbarui ({len(df)} baris)")
print("Selesai. Jalankan ulang aplikasi agar data baru terbaca.")
