"""Form input demo (B4) -> transaksi 90 hari mengikuti aturan A4."""
import numpy as np
import pandas as pd
from engine import ACUAN

KATEGORI_FORM = ["Makan", "Kopi", "Transportasi", "Belanja Online", "Hiburan", "Tagihan", "Investasi"]
FREK_BULANAN = {"Makan": 22, "Transportasi": 20, "Belanja Online": 3, "Hiburan": 2}
JAM = {"Kopi": (7, 10), "Makan": (11, 14), "Transportasi": (7, 20),
       "Belanja Online": (19, 23), "Hiburan": (17, 22)}
MERCHANT_DEFAULT = {"Makan": ("M004", "Nasi Bunda"), "Transportasi": ("M006", "JalanYuk"),
                    "Belanja Online": ("M007", "TokoRia"), "Hiburan": ("M008", "Bioskop Nusantara")}

BASE = {"nama": "Juri", "usia": 25, "jenis_kelamin": "pria", "kota": "Jakarta",
        "pendapatan": 7_000_000, "saldo": 3_000_000, "tujuan": "Beli rumah", "usia_target": 35,
        "frek_kopi": 20, "merchant_kopi": "Kopi Kawan", "porsi_ewallet": 30,
        "setoran": 0, "cicilan": 0, "lonjakan": True, "kategori_lonjakan": "Belanja Online"}

SKENARIO = {
    "Aman": {**BASE, "pendapatan": 9_000_000, "saldo": 20_000_000, "tujuan": "Dana pensiun nyaman",
             "usia_target": 60, "frek_kopi": 8, "porsi_ewallet": 10, "setoran": 1_800_000, "lonjakan": False,
             "Makan": 1_500_000, "Kopi": 300_000, "Transportasi": 600_000, "Belanja Online": 500_000,
             "Hiburan": 300_000, "Tagihan": 800_000, "Investasi": 500_000},
    "Numpang Lewat": {**BASE, "saldo": 8_000_000, "tujuan": "Beli motor", "usia_target": 28,
                      "frek_kopi": 8, "porsi_ewallet": 60,
                      "Makan": 600_000, "Kopi": 200_000, "Transportasi": 300_000, "Belanja Online": 300_000,
                      "Hiburan": 100_000, "Tagihan": 400_000, "Investasi": 0},
    "Konsumtif": {**BASE, "saldo": 9_000_000, "frek_kopi": 25, "porsi_ewallet": 10,
                  "Makan": 1_000_000, "Kopi": 950_000, "Transportasi": 400_000, "Belanja Online": 1_000_000,
                  "Hiburan": 400_000, "Tagihan": 600_000, "Investasi": 0},
    "Defisit": {**BASE, "pendapatan": 6_000_000, "usia": 29, "tujuan": "Lunas cicilan",
                "frek_kopi": 12, "porsi_ewallet": 15, "cicilan": 1_800_000, "lonjakan": False,
                "Makan": 1_500_000, "Kopi": 400_000, "Transportasi": 800_000, "Belanja Online": 800_000,
                "Hiburan": 400_000, "Tagihan": 900_000, "Investasi": 0},
}
DEFAULT = {**SKENARIO["Konsumtif"], "porsi_ewallet": 30}      # default B4


def validasi(v):
    """Kembalikan daftar pesan error sesuai kolom Validasi B4."""
    err = []
    if not str(v["nama"]).strip():
        err.append("Nama wajib diisi.")
    if len(str(v["nama"])) > 20:
        err.append("Nama maksimal 20 karakter.")
    if not 18 <= v["usia"] <= 45:
        err.append("Usia harus 18 sampai 45.")
    if v["pendapatan"] <= 0:
        err.append("Pendapatan harus lebih dari 0.")
    if v["usia_target"] <= v["usia"]:
        err.append("Usia target tujuan harus lebih besar dari usia.")
    if not 0 <= v["frek_kopi"] <= 60:
        err.append("Frekuensi kopi harus 0 sampai 60.")
    if min(v["saldo"], v["setoran"], v["cicilan"], *[v[k] for k in KATEGORI_FORM]) < 0:
        err.append("Nominal tidak boleh negatif.")
    return err


def _waktu(hari, kategori, rng):
    lo, hi = JAM.get(kategori, (8, 20))
    return hari + pd.Timedelta(hours=int(rng.integers(lo, hi)), minutes=int(rng.integers(0, 60)))


def buat_transaksi(v, merchant, seed=7):
    """Kembalikan (profil Series, DataFrame transaksi) dengan kolom sama seperti data master."""
    rng = np.random.default_rng(seed)
    hari_list = pd.date_range(end=ACUAN.normalize(), periods=90)
    kopi = merchant[merchant.merchant_nama == v["merchant_kopi"]]
    merchant_kopi = (kopi.merchant_id.iloc[0], v["merchant_kopi"]) if len(kopi) else ("M001", "Kopi Kawan")
    rows = []

    def tambah(waktu, arah, kat, nominal, metode, tujuan, merch=("", "")):
        rows.append([waktu, arah, kat, merch[0], merch[1], metode, tujuan, round(nominal)])

    acak = lambda x: x * rng.uniform(0.8, 1.2)                 # nominal +/- 20%
    for h in hari_list:
        if h.day == 25:
            gaji_t = h + pd.Timedelta(hours=8)
            tambah(gaji_t, "masuk", "Gaji", v["pendapatan"], "Transfer", "BNI")
            if v["porsi_ewallet"]:
                tambah(gaji_t + pd.Timedelta(days=1, hours=2), "keluar", "Top Up E-Wallet",
                       v["pendapatan"] * v["porsi_ewallet"] / 100, "Transfer", "E-Wallet")
            if v["setoran"]:
                tambah(gaji_t + pd.Timedelta(hours=3), "keluar", "Life Goals", v["setoran"], "Transfer", "BNI")
            if v["Investasi"]:
                tambah(gaji_t + pd.Timedelta(days=1, hours=5), "keluar", "Investasi", v["Investasi"], "Transfer", "BNI")
        if h.day == 2 and v["Tagihan"]:
            tambah(h + pd.Timedelta(hours=9), "keluar", "Tagihan", v["Tagihan"], "Autodebet", "BNI")
        if h.day == 3 and v["cicilan"]:
            tambah(h + pd.Timedelta(hours=9), "keluar", "Cicilan", v["cicilan"], "Autodebet", "BNI")

    # transaksi harian tersebar merata dalam 90 hari
    frek = {**FREK_BULANAN, "Kopi": v["frek_kopi"]}
    for kat, per_bulan in frek.items():
        total_bulan = v[kat]
        if total_bulan <= 0 or per_bulan <= 0:
            continue
        n = int(round(per_bulan * 3))
        posisi = np.linspace(0, len(hari_list) - 1, n) + rng.uniform(-1, 1, n)
        hari_pilih = hari_list[np.clip(posisi.round().astype(int), 0, len(hari_list) - 1)]
        merch = merchant_kopi if kat == "Kopi" else MERCHANT_DEFAULT[kat]
        metode = "Debit" if kat == "Belanja Online" else "QRIS"
        for h in hari_pilih:
            tambah(_waktu(pd.Timestamp(h), kat, rng), "keluar", kat, acak(total_bulan / per_bulan),
                   metode, "Merchant", merch)

    # lonjakan 7 hari terakhir (A4)
    if v["lonjakan"]:
        kat = v["kategori_lonjakan"]
        mingguan = max(v.get(kat, 0) / 4.3, 100_000)
        merch = merchant_kopi if kat == "Kopi" else MERCHANT_DEFAULT.get(kat, ("", ""))
        for h in hari_list[-5:]:
            tambah(_waktu(h, kat, rng), "keluar", kat, mingguan * 0.8, "QRIS", "Merchant", merch)

    tr = pd.DataFrame(rows, columns=["tanggal_waktu", "arah", "kategori", "merchant_id",
                                     "merchant_nama", "metode", "tujuan", "nominal"])
    tr = tr[tr.tanggal_waktu <= ACUAN].sort_values("tanggal_waktu").reset_index(drop=True)
    tr.insert(0, "user_id", "INPUT")
    tr.insert(0, "trx_id", [f"X{i + 1:06d}" for i in range(len(tr))])

    # saldo_setelah dihitung mundur dari saldo akhir, tidak boleh negatif (A4)
    arus = np.where(tr.arah == "masuk", tr.nominal, -tr.nominal)
    kumulatif = arus.cumsum()
    saldo_awal = max(v["saldo"] - kumulatif[-1], -kumulatif.min(), 0) if len(tr) else v["saldo"]
    tr["saldo_setelah"] = (saldo_awal + kumulatif).round()

    profil = pd.Series({
        "user_id": "INPUT", "nama": v["nama"].strip(), "gender": v["jenis_kelamin"],
        "usia": int(v["usia"]), "kota": v["kota"],
        "pekerjaan": "Input demo", "pendapatan_bulanan": v["pendapatan"],
        "saldo_saat_ini": float(tr.saldo_setelah.iloc[-1]) if len(tr) else v["saldo"],
        "tujuan": v["tujuan"] or "Belum diisi", "usia_target_tujuan": int(v["usia_target"]),
        "persona": "Input manual",
    })
    return profil, tr
