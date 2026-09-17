"""Engine perhitungan WondrCast & WondrSaver.
Semua angka dihitung di sini. LLM hanya menjelaskan hasilnya (prinsip NFR-01)."""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"
ACUAN = pd.Timestamp("2026-09-27 23:59:59")          # tanggal acuan data dummy

KAT_KONSUMTIF = ["Kopi", "Hiburan", "Belanja Online"]
KAT_NABUNG = ["Life Goals", "Investasi"]
KAT_MERCHANT = ["Makan", "Kopi", "Transportasi", "Belanja Online", "Hiburan"]
KAT_DOMINAN = KAT_MERCHANT + ["Tagihan"]
FITUR_WONDR = ["Life Goals", "Tabungan Berjangka", "Deposito", "Bayar Tagihan", "QRIS"]

AMBANG = {
    "menabung_rendah": 0.10,   # B5.1
    "defisit": 1.00,
    "konsumtif": 0.30,
    "numpang": 0.50,
    "tren_naik": 1.20,
    "disiplin": 0.15,          # B5.2
    "dominan_frek": 8,         # C7 langkah 1 (kali per bulan)
    "dominan_porsi": 0.15,
    "lonjakan": 0.50,          # R3
    "lonjakan_min": 200_000,   # asumsi tambahan: kenaikan minimal agar transaksi jarang tidak memicu R3
    "cicilan": 0.30,           # R6
    "gaji_baru_hari": 7,       # R7
}

ASUMSI = {"r": 0.04, "g": 0.05, "inflasi": 0.03, "hemat": 0.20, "tahun_proyeksi": 10,
          "rasio_target": 1.00, "bulan_target": 12,   # target dana umum: 1x pendapatan/pengeluaran bulanan
          # dasar target dana. Dokumen B5.3 memakai "pengeluaran"; default "pendapatan"
          # karena pengeluaran yang tercatat bisa sangat kecil (nasabah jarang transaksi).
          "basis_kebutuhan": "pendapatan"}
URUTAN_ATURAN = {f"R{i}": i for i in range(1, 8)}
BATAS_DATA_TERBATAS = 0.20   # pengeluaran tercatat < 20% pemasukan = data transaksi belum lengkap

PRIORITAS = {"Kritis": 1, "Waktu": 2, "Peringatan": 3, "Peluang": 4}
METODE_PROMO = {"QRIS wondr": "QRIS", "Debit BNI": "Debit"}


def rupiah(x):
    tanda = "-" if x < 0 else ""
    return f"{tanda}Rp{abs(x):,.0f}".replace(",", ".")


def persen(x):
    return f"{x:.0%}"


def persen_bawah(x):
    """Dibulatkan ke bawah agar 99,7% tidak tampil 100% saat status masih Waspada."""
    return f"{int(x * 100)}%"


# ---------------------------------------------------------------- data
def load_data():
    nasabah = pd.read_csv(DATA / "nasabah.csv")
    merchant = pd.read_csv(DATA / "merchant.csv")
    promo = pd.read_csv(DATA / "promo.csv", parse_dates=["mulai", "berakhir"])
    promo["merchant_id"] = promo["merchant_id"].fillna("")
    promo["syarat"] = promo["syarat"].fillna("")
    transaksi = pd.read_csv(DATA / "transaksi.csv", parse_dates=["tanggal_waktu"])
    for k in ["merchant_id", "merchant_nama"]:
        transaksi[k] = transaksi[k].fillna("")
    return nasabah, transaksi, merchant, promo


# ---------------------------------------------------------------- B5.1 metrik
def _jumlah(df, kategori=None):
    if kategori is not None:
        df = df[df.kategori.isin(kategori)]
    return float(df.nominal.sum())


def lonjakan_kategori(tr):
    """R3: kategori yang naik > 50% dalam 7 hari terakhir dibanding rata-rata mingguan sebelumnya."""
    batas = ACUAN - pd.Timedelta(days=7)
    keluar = tr[(tr.arah == "keluar") & tr.kategori.isin(KAT_MERCHANT)]
    ini, lalu = keluar[keluar.tanggal_waktu > batas], keluar[keluar.tanggal_waktu <= batas]
    if lalu.empty:
        return []
    minggu = max((batas - lalu.tanggal_waktu.min()).days / 7, 1)
    rata = lalu.groupby("kategori").nominal.sum() / minggu
    hasil = []
    for kat, nilai in ini.groupby("kategori").nominal.sum().items():
        dasar = rata.get(kat, 0)
        if dasar > 0 and nilai > dasar * (1 + AMBANG["lonjakan"]) and nilai - dasar >= AMBANG["lonjakan_min"]:
            hasil.append({"kategori": kat, "minggu_ini": nilai, "rata_mingguan": dasar,
                          "kenaikan": nilai / dasar - 1, "selisih": nilai - dasar})
    return sorted(hasil, key=lambda x: -x["selisih"])


def hitung_metrik(tr, profil):
    tr = tr.sort_values("tanggal_waktu")
    hari = (ACUAN.normalize() - tr.tanggal_waktu.min().normalize()).days + 1
    bulan = max(hari / 30, 1)
    keluar = tr[tr.arah == "keluar"]
    belanja = keluar[~keluar.kategori.isin(KAT_NABUNG)]

    pemasukan = _jumlah(tr[tr.arah == "masuk"]) / bulan
    pengeluaran = _jumlah(belanja) / bulan
    nabung = _jumlah(keluar, KAT_NABUNG) / bulan
    konsumtif = _jumlah(keluar, KAT_KONSUMTIF) / bulan
    cicilan = _jumlah(keluar, ["Cicilan"]) / bulan

    # dana numpang lewat: transfer keluar ke e-wallet/bank lain dalam 3 hari setelah gajian
    gaji = tr[tr.kategori == "Gaji"]
    pindah = keluar[keluar.tujuan.isin(["E-Wallet", "Bank Lain"])]
    total_pindah = 0.0
    for _, g in gaji.iterrows():
        jendela = pindah[(pindah.tanggal_waktu >= g.tanggal_waktu) &
                         (pindah.tanggal_waktu <= g.tanggal_waktu + pd.Timedelta(days=3))]
        total_pindah += jendela.nominal.sum()
    numpang = total_pindah / gaji.nominal.sum() if len(gaji) else 0.0

    # 30 hari terakhir
    t30 = tr[tr.tanggal_waktu > ACUAN - pd.Timedelta(days=30)]
    k30 = t30[(t30.arah == "keluar") & ~t30.kategori.isin(KAT_NABUNG)]
    masuk_30, keluar_30 = _jumlah(t30[t30.arah == "masuk"]), _jumlah(k30)

    # profil per kategori (30 hari terakhir)
    kat = []
    for nama, d in k30.groupby("kategori"):
        merch = d[d.merchant_id != ""].groupby(["merchant_id", "merchant_nama"]).size().sort_values(ascending=False)
        kat.append({
            "kategori": nama, "frekuensi": len(d), "nominal": float(d.nominal.sum()),
            "porsi": d.nominal.sum() / keluar_30 if keluar_30 else 0,
            "rata_trx": float(d.nominal.mean()),
            "merchant_favorit": merch.index[0][1] if len(merch) else "",
            "merchant_id_favorit": merch.index[0][0] if len(merch) else "",
            "frek_merchant_favorit": int(merch.iloc[0]) if len(merch) else 0,
            "metode_favorit": d.metode.mode().iloc[0],
        })
    kat = pd.DataFrame(kat)
    if kat.empty:
        dominan = kat
    else:
        kat = kat.sort_values(["frekuensi", "nominal"], ascending=False)
        syarat = (kat.frekuensi >= AMBANG["dominan_frek"]) | (kat.porsi >= AMBANG["dominan_porsi"])
        dominan = kat[syarat & kat.kategori.isin(KAT_DOMINAN)]

    frek_merchant = (t30[(t30.arah == "keluar") & (t30.merchant_id != "")]
                     .groupby("merchant_id").size())
    merchant_dominan = frek_merchant[frek_merchant >= AMBANG["dominan_frek"]].index.tolist()

    return {
        "bulan_data": round(bulan, 1),
        "pemasukan": pemasukan, "pengeluaran": pengeluaran, "nabung": nabung,
        "konsumtif": konsumtif, "cicilan": cicilan,
        "rasio_menabung": nabung / pemasukan if pemasukan else 0,
        "rasio_pengeluaran": pengeluaran / pemasukan if pemasukan else 9.99,
        "porsi_konsumtif": konsumtif / pengeluaran if pengeluaran else 0,
        "numpang_lewat": numpang,
        "rasio_cicilan": cicilan / pemasukan if pemasukan else 0,
        "tren_pengeluaran": keluar_30 / pengeluaran if pengeluaran else 0,
        "masuk_30": masuk_30, "keluar_30": keluar_30,
        "saldo": float(profil["saldo_saat_ini"]),
        "kategori": kat, "dominan": dominan, "merchant_dominan": merchant_dominan,
        "lonjakan": lonjakan_kategori(tr),
        "gaji_terakhir": gaji.iloc[-1] if len(gaji) else None,
    }


def tabel_metrik(m):
    """Tabel B5.1 untuk ditampilkan."""
    dom = ", ".join(m["dominan"].kategori.head(3)) if len(m["dominan"]) else "-"
    baris = [
        ["Rasio menabung", persen(m["rasio_menabung"]), "< 10% = rendah",
         "Rendah" if m["rasio_menabung"] < AMBANG["menabung_rendah"] else "Baik"],
        ["Rasio pengeluaran", persen(m["rasio_pengeluaran"]), "> 100% = defisit",
         "Defisit" if m["rasio_pengeluaran"] > AMBANG["defisit"] else "Aman"],
        ["Porsi konsumtif", persen(m["porsi_konsumtif"]), "> 30% = tinggi",
         "Tinggi" if m["porsi_konsumtif"] > AMBANG["konsumtif"] else "Wajar"],
        ["Dana numpang lewat", persen(m["numpang_lewat"]), "> 50% = tinggi",
         "Tinggi" if m["numpang_lewat"] > AMBANG["numpang"] else "Wajar"],
        ["Kategori dominan", dom, "frek >= 8 atau porsi >= 15%", "-"],
        ["Tren pengeluaran", f"{m['tren_pengeluaran']:.2f}x", "> 1,2 = naik",
         "Naik" if m["tren_pengeluaran"] > AMBANG["tren_naik"] else "Stabil"],
    ]
    return pd.DataFrame(baris, columns=["Metrik", "Nilai", "Ambang", "Status"])


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _posisi(nilai, rendah, tinggi):
    if nilai <= 33:
        return f"Dominan di area {rendah} (sangat rendah menuju {tinggi})"
    if nilai >= 67:
        return f"Berada tinggi di area {tinggi} (jauh dari {rendah})"
    return f"Berada di posisi tengah, antara {rendah} dan {tinggi}"


def indikator_risiko(m):
    """Indikator & Metrik Risiko (WondrCast): 4 posisi 0-100 dihitung dari data
    nasabah asli, bukan angka tetap. Ambang skala memakai AMBANG yang sudah
    dipakai metrik B5.1/B5.2 lain agar konsisten satu aplikasi.
    Konvensi arah: nilai TINGGI = baik (Discipline/Frugal/Good) di keempatnya,
    nilai RENDAH = perlu perbaikan (Indulgent/Impulsive/Bad), kecuali Risk
    Tolerance yang murni netral (tinggi = agresif, bukan "lebih baik")."""
    bulan_buffer = m["saldo"] / m["pengeluaran"] if m["pengeluaran"] else 99

    saving = _clamp01(m["rasio_menabung"] / (2 * AMBANG["disiplin"])) * 100
    boros = (_clamp01(m["porsi_konsumtif"] / (2 * AMBANG["konsumtif"]))
             + _clamp01(m["rasio_cicilan"] / (2 * AMBANG["cicilan"]))) / 2 * 100
    spending = 100 - boros                                   # tinggi = Frugal (baik)
    # 0.30 = pengeluaran sangat rendah (median nasabah nyata ~0,65), 100% tepat
    # di ambang label Defisit (AMBANG["defisit"]) supaya konsisten satu aplikasi.
    rentan = _clamp01((m["rasio_pengeluaran"] - 0.30) / (AMBANG["defisit"] - 0.30)) * 100
    kesehatan = 100 - rentan                                 # tinggi = Good (baik)
    risiko = (_clamp01(bulan_buffer / 6)
              + (1 - _clamp01(m["rasio_cicilan"] / AMBANG["cicilan"]))) / 2 * 100

    return [
        {"kode": "saving_priority", "judul": "Saving Priority",
         "sub": "Sets and meets savings goals", "nilai": round(saving),
         "label_rendah": "Indulgent", "label_tinggi": "Discipline",
         "posisi": _posisi(saving, "Indulgent", "Discipline"),
         "keterangan": (f"Alokasi tabungan {persen(m['rasio_menabung'])} dari pemasukan, "
                        + ("tergerus pengeluaran bulanan." if saving < 50 else "cukup disiplin menuju tujuan finansial."))},
        {"kode": "spending_style", "judul": "Spending Style",
         "sub": "Avoids excessive spending", "nilai": round(spending),
         "label_rendah": "Impulsive", "label_tinggi": "Frugal",
         "posisi": _posisi(spending, "Impulsive", "Frugal"),
         "keterangan": (f"Gaya hidup {persen(m['porsi_konsumtif'])} dari pengeluaran, cicilan {persen(m['rasio_cicilan'])} dari pemasukan"
                        + (", dipicu gaya hidup serta beban cicilan." if spending < 50 else ", masih terkendali."))},
        {"kode": "financial_health", "judul": "Financial Health",
         "sub": "Scenario projection", "nilai": round(kesehatan),
         "label_rendah": "Bad", "label_tinggi": "Good",
         "posisi": _posisi(kesehatan, "Bad", "Good"),
         "keterangan": (f"Pengeluaran {persen(m['rasio_pengeluaran'])} dari pemasukan"
                        + (", ketahanan finansial melemah." if kesehatan < 50 else ", ketahanan finansial masih terjaga."))},
        {"kode": "risk_tolerance", "judul": "Risk Tolerance",
         "sub": "Prudent investment choices", "nilai": round(risiko),
         "label_rendah": "Conservative", "label_tinggi": "Aggressive",
         "posisi": _posisi(risiko, "Conservative", "Aggressive"),
         "keterangan": (f"Saldo setara {bulan_buffer:.1f} bulan pengeluaran dengan cicilan {persen(m['rasio_cicilan'])} dari pemasukan"
                        + (", kapasitas ambil risiko investasi rendah akibat keterbatasan likuiditas."
                           if risiko < 50 else ", kapasitas ambil risiko investasi cukup baik."))},
    ]


def _label_fase(a, b):
    return f"Tahun {a}" if a == b else f"Tahun {a}–{b}"


def _fase_tahun(tahun_proyeksi):
    """Bagi horizon proyeksi jadi sampai 4 fase (~10/20/30/40%), minimal 1 tahun
    per fase. Untuk tahun_proyeksi=10 (default) hasilnya persis Tahun 1,
    Tahun 2-3, Tahun 4-6, Tahun 7-10."""
    batas, mulai = [], 1
    for porsi in (0.1, 0.2, 0.3, 0.4):
        if mulai > tahun_proyeksi:
            break
        panjang = max(1, round(tahun_proyeksi * porsi))
        akhir = min(tahun_proyeksi, mulai + panjang - 1)
        batas.append((mulai, akhir))
        mulai = akhir + 1
    return batas


def roadmap_finansial(m, profil, tahun_proyeksi):
    """Insight WondrCast: peta jalan per fase tahun (bukan LLM, dihitung
    langsung dari data supaya angkanya selalu akurat -- lihat ATURAN_UMUM
    di llm.py yang melarang LLM membuat angka baru)."""
    fase = _fase_tahun(tahun_proyeksi)
    minus = m["pengeluaran"] - m["pemasukan"]

    aksi_stabilisasi = []
    if minus > 0:
        aksi_stabilisasi.append(f"tutup defisit {rupiah(minus)}/bulan")
    if m["rasio_cicilan"] > AMBANG["cicilan"]:
        aksi_stabilisasi.append(f"lunasi atau kurangi cicilan berbunga tinggi "
                                 f"(sekarang {persen(m['rasio_cicilan'])} dari pemasukan)")
    aksi_stabilisasi.append(f"bangun dana darurat setara {rupiah(m['pengeluaran'] * 3)} (3x pengeluaran bulanan)")

    urutan = [
        aksi_stabilisasi,
        ["mulai sisihkan dana investasi secara rutin tiap bulan"],
        ["perbesar portofolio investasimu -- gaji naik = investasi naik, bukan gaya hidup"],
        [f"wujudkan tujuan hidupmu ({profil['tujuan']}) lewat Life Goals, tambah proteksi jiwa & kesehatan"],
    ]
    nama_depan = str(profil["nama"]).split()[0]
    return {
        "judul": f"Hi, {nama_depan}! Mau {tahun_proyeksi} tahunmu lebih aman? Yuk intip caranya!",
        "fase": [{"label": _label_fase(a, b), "aksi": urutan[i]} for i, (a, b) in enumerate(fase)],
    }


# ---------------------------------------------------------------- B5.2 label
def label_perilaku(m):
    if m["rasio_pengeluaran"] > AMBANG["defisit"]:
        return "Defisit"
    if m["numpang_lewat"] > AMBANG["numpang"]:
        return "Numpang Lewat"
    if m["porsi_konsumtif"] > AMBANG["konsumtif"]:
        return "Konsumtif"
    if m["rasio_menabung"] >= AMBANG["disiplin"]:
        return "Penabung Disiplin"
    return "Berkembang"


# ---------------------------------------------------------------- B5.3 proyeksi
def _status(kecukupan, setoran_awal):
    if setoran_awal < 0 or kecukupan < 0.5:
        return "Berisiko"
    return "Aman" if kecukupan >= 1 else "Waspada"


def proyeksi(m, usia, asumsi=None):
    a = {**ASUMSI, **(asumsi or {})}
    bulan = int(a["tahun_proyeksi"] * 12)  # horizon bisa diatur, sama untuk semua usia
    setoran_a = m["pemasukan"] - m["pengeluaran"]
    setoran_b = setoran_a + a["hemat"] * m["konsumtif"]
    saldo_a = saldo_b = m["saldo"]
    s_a, s_b = setoran_a, setoran_b
    seri = [[int(usia), saldo_a, saldo_b]]
    for i in range(1, bulan + 1):
        saldo_a = max(0.0, saldo_a * (1 + a["r"] / 12) + s_a)
        saldo_b = max(0.0, saldo_b * (1 + a["r"] / 12) + s_b)
        if i % 12 == 0:
            s_a *= 1 + a["g"]
            s_b *= 1 + a["g"]
            seri.append([int(usia) + i // 12, saldo_a, saldo_b])

    tahun = bulan / 12
    dasar = m["pemasukan"] if a["basis_kebutuhan"] == "pendapatan" else m["pengeluaran"]
    kebutuhan = dasar * a["rasio_target"] * a["bulan_target"]
    hasil = {"asumsi": a, "tahun": tahun, "kebutuhan": kebutuhan,
             "data_terbatas": m["pengeluaran"] < BATAS_DATA_TERBATAS * m["pemasukan"],
             "setoran_a": setoran_a, "setoran_b": setoran_b,
             "seri": pd.DataFrame(seri, columns=["usia", "Kebiasaan tetap (A)", "Kebiasaan diperbaiki (B)"]).set_index("usia")}
    for k, saldo, setor in [("a", saldo_a, setoran_a), ("b", saldo_b, setoran_b)]:
        riil = saldo / (1 + a["inflasi"]) ** tahun
        cukup = riil / kebutuhan if kebutuhan else 0
        hasil[k] = {"nominal": saldo, "riil": riil, "kecukupan": cukup,
                    "status": _status(cukup, setor),
                    "catatan": "Berpotensi berutang" if setor < 0 else ""}
    return hasil


def tabel_asumsi(a):
    return pd.DataFrame([
        ["Proyeksi", f"{a['tahun_proyeksi']} tahun ke depan", "Ya"],
        ["Imbal hasil tabungan", persen(a["r"]) + " per tahun", "Ya"],
        ["Kenaikan pendapatan", persen(a["g"]) + " per tahun", "Ya"],
        ["Inflasi", persen(a["inflasi"]) + " per tahun", "Ya"],
        ["Porsi hemat skenario B", persen(a["hemat"]) + " dari pengeluaran konsumtif", "Ya"],
        ["Rasio target dana", persen(a["rasio_target"]) + " dari " + a["basis_kebutuhan"] + " bulanan", "Tidak"],
        ["Lama target dana", f"{a['bulan_target']} bulan", "Tidak"],
    ], columns=["Asumsi", "Nilai", "Dapat diubah"])


# ---------------------------------------------------------------- C5 advice
def daftar_advice(m):
    adv = []

    def tambah(id_, level, judul, pesan, tombol, halaman, dampak, angka):
        adv.append({"id": id_, "jenis": "advice", "level": level, "prioritas": PRIORITAS[level],
                    "judul": judul, "pesan": pesan, "label_tombol": tombol, "halaman": halaman,
                    "dampak": float(dampak), "angka": angka})

    if m["keluar_30"] > m["masuk_30"]:
        minus = m["keluar_30"] - m["masuk_30"]
        tambah("R1", "Kritis", "Pengeluaranmu melebihi pemasukan",
               f"Dalam 30 hari terakhir kamu minus {rupiah(minus)}. Yuk cek rincian dan pasang batas belanja.",
               "Lihat rincian", "WondrCast", minus,
               {"pemasukan_30_hari": rupiah(m["masuk_30"]), "pengeluaran_30_hari": rupiah(m["keluar_30"]),
                "minus": rupiah(minus)})
    if m["saldo"] < m["pengeluaran"]:
        minggu = m["saldo"] / m["pengeluaran"] * 4.3 if m["pengeluaran"] else 0
        tambah("R2", "Kritis", "Saldomu belum cukup sebulan",
               f"Saldo {rupiah(m['saldo'])} hanya cukup sekitar {minggu:.0f} minggu. Mulai sisihkan dana darurat.",
               "Mulai dana darurat", "Life Goals", m["pengeluaran"] - m["saldo"],
               {"saldo": rupiah(m["saldo"]), "pengeluaran_bulanan": rupiah(m["pengeluaran"]),
                "cukup_minggu": f"{minggu:.0f}"})
    for l in m["lonjakan"]:
        tambah("R3", "Peringatan", f"Pengeluaran {l['kategori']} naik tajam",
               f"Pengeluaran {l['kategori']} minggu ini {rupiah(l['minggu_ini'])}, naik {persen(l['kenaikan'])} "
               f"dari rata-rata {rupiah(l['rata_mingguan'])}. Pasang batas mingguan?",
               "Pasang batas", "WondrSaver", l["selisih"],
               {"kategori": l["kategori"], "minggu_ini": rupiah(l["minggu_ini"]),
                "rata_mingguan": rupiah(l["rata_mingguan"]), "kenaikan": persen(l["kenaikan"])})
        break  # satu advice R3 untuk kategori dengan lonjakan terbesar
    if m["porsi_konsumtif"] > AMBANG["konsumtif"]:
        tambah("R4", "Peringatan", "Pengeluaran gaya hidup cukup besar",
               f"{persen(m['porsi_konsumtif'])} pengeluaranmu untuk kopi, hiburan, dan belanja online. "
               "Lihat simulasi kalau sebagian dihemat.",
               "Lihat simulasi hemat", "WondrCast", m["konsumtif"],
               {"porsi_konsumtif": persen(m["porsi_konsumtif"]), "konsumtif_bulanan": rupiah(m["konsumtif"])})
    if m["numpang_lewat"] > AMBANG["numpang"]:
        nominal = m["numpang_lewat"] * (m["gaji_terakhir"].nominal if m["gaji_terakhir"] is not None else 0)
        tambah("R5", "Peringatan", "Gajimu cepat pindah ke e-wallet",
               f"{persen(m['numpang_lewat'])} gajimu pindah ke e-wallet dalam 3 hari. Sisihkan dulu ke Life Goals.",
               "Sisihkan ke Life Goals", "Life Goals", nominal,
               {"numpang_lewat": persen(m["numpang_lewat"]), "nominal_pindah": rupiah(nominal)})
    if m["rasio_cicilan"] > AMBANG["cicilan"]:
        tambah("R6", "Peringatan", "Cicilanmu cukup berat",
               f"Cicilanmu {persen(m['rasio_cicilan'])} dari pemasukan. Cek simulasi sebelum menambah cicilan baru.",
               "Lihat simulasi", "WondrCast", m["cicilan"],
               {"rasio_cicilan": persen(m["rasio_cicilan"]), "cicilan_bulanan": rupiah(m["cicilan"])})
    g = m["gaji_terakhir"]
    ada_r1 = any(x["id"] == "R1" for x in adv)       # hindari saran menabung saat sedang defisit
    if not ada_r1 and g is not None and (ACUAN - g.tanggal_waktu).days <= AMBANG["gaji_baru_hari"] \
            and m["rasio_menabung"] < AMBANG["menabung_rendah"]:
        sisih = 0.10 * g.nominal
        tambah("R7", "Waktu", "Gaji baru masuk",
               f"Gaji {rupiah(g.nominal)} sudah masuk. Sisihkan {rupiah(sisih)} (10%) sekarang sebelum terpakai.",
               "Setor ke Life Goals", "Life Goals", sisih,
               {"gaji": rupiah(g.nominal), "saran_setoran": rupiah(sisih)})
    return adv


# ---------------------------------------------------------------- C6-C7 promo
def _manfaat(p, rata):
    if p.satuan == "persen":
        return min(rata * p.nilai / 100, p.maks_manfaat)
    if p.nilai == 0:                      # bebas admin
        return float(p.maks_manfaat)
    return float(min(p.nilai, p.maks_manfaat))


def cocokkan_promo(tr, m, label, profil, promo, merchant, klaim=None, ada_kritis=False):
    """Kembalikan (lolos, ditahan, tidak_aktif) sesuai C7."""
    klaim = klaim or {}
    t30 = tr[(tr.tanggal_waktu > ACUAN - pd.Timedelta(days=30)) & (tr.arah == "keluar")]
    info_merchant = merchant.set_index("merchant_id")
    kat_dominan = set(m["dominan"].kategori) if len(m["dominan"]) else set()
    kat_lonjak = {l["kategori"] for l in m["lonjakan"]}
    kat_info = m["kategori"].set_index("kategori") if len(m["kategori"]) else pd.DataFrame()

    lolos, ditahan, tidak_aktif = [], [], []
    for _, p in promo.iterrows():
        target = [x.strip() for x in str(p.target_label).split(";")]
        mid = p.merchant_id

        # langkah 2: promo aktif
        alasan = ""
        if ACUAN < p.mulai:
            alasan = "Belum mulai"
        elif ACUAN.normalize() > p.berakhir:
            alasan = "Kedaluwarsa"
        elif mid and info_merchant.loc[mid, "status_mitra"] != "Aktif":
            alasan = "Merchant tidak aktif"
        elif klaim.get(p.promo_id, 0) >= p.kuota_per_user:
            alasan = "Kuota habis"
        elif "Semua" not in target and label not in target:
            alasan = f"Hanya untuk label {', '.join(target)}"
        if alasan:
            tidak_aktif.append({"promo_id": p.promo_id, "judul": p.judul, "alasan": alasan})
            continue

        # relevansi dan dasar estimasi
        dasar = t30[t30.merchant_id == mid] if mid else t30[t30.kategori == p.kategori]
        catatan = ""
        if mid and dasar.empty:
            if p.kategori not in kat_info.index or info_merchant.loc[mid, "kota"] != profil["kota"]:
                continue
            dasar = t30[t30.kategori == p.kategori]
            catatan = f"jika pindah ke {info_merchant.loc[mid, 'merchant_nama']}"
        elig = dasar[dasar.nominal >= p.min_transaksi]
        frek, rata = len(elig), float(elig.nominal.mean()) if len(elig) else 0.0
        if frek == 0:
            if not p.bantu_nabung:
                continue
            rata = max(0.10 * m["pemasukan"], p.min_transaksi) if p.kategori == "Life Goals" else p.min_transaksi
            frek, catatan = 1, "jika mulai sekarang"
        manfaat = _manfaat(p, rata)
        hemat = min(frek, p.kuota_per_user) * manfaat

        # langkah 3: penahan
        if ada_kritis and not p.bantu_nabung:
            ditahan.append({"promo_id": p.promo_id, "judul": p.judul,
                            "alasan": "Ada kondisi keuangan kritis, hanya promo bantu nabung yang tampil"})
            continue
        if p.kategori in kat_lonjak:
            ditahan.append({"promo_id": p.promo_id, "judul": p.judul,
                            "alasan": f"Pengeluaran {p.kategori} sedang melonjak"})
            continue

        # langkah 4: skor C7.1
        s_merchant = 1.0 if mid and mid in m["merchant_dominan"] else 0.0
        s_kategori = 0.6 if p.kategori in kat_dominan else 0.0
        s_umum = 0.2 if not mid else 0.0
        metode_user = kat_info.loc[p.kategori, "metode_favorit"] if p.kategori in kat_info.index else ""
        s_metode = 0.1 if METODE_PROMO.get(p.metode_bayar) == metode_user else 0.0
        s_nabung = 0.3 if p.bantu_nabung and label in ("Defisit", "Numpang Lewat") else 0.0
        skor = s_merchant + s_kategori + s_umum + s_metode + s_nabung

        if mid:
            nama_m = info_merchant.loc[mid, "merchant_nama"]
            alasan_tampil = f"Kamu {len(dasar)} kali belanja {p.kategori.lower()} {catatan or 'di ' + nama_m} dalam 30 hari"
        elif p.bantu_nabung:
            alasan_tampil = f"Membantu kebiasaan menabung ({catatan})" if catatan else f"Kamu {frek} kali transaksi {p.kategori.lower()} dalam 30 hari"
        else:
            alasan_tampil = f"Kamu {len(dasar)} kali belanja {p.kategori.lower()} dalam 30 hari"

        lolos.append({
            "promo_id": p.promo_id, "judul": p.judul, "kategori": p.kategori,
            "merchant": info_merchant.loc[mid, "merchant_nama"] if mid else "Semua merchant",
            "mekanisme": p.mekanisme, "metode_bayar": p.metode_bayar, "syarat": p.syarat,
            "bantu_nabung": bool(p.bantu_nabung), "kuota": int(p.kuota_per_user),
            "frekuensi": frek, "frek_dasar": len(dasar), "manfaat_per_trx": manfaat, "estimasi_hemat": hemat,
            "alasan": alasan_tampil,
            "skor_merchant": s_merchant, "skor_kategori": s_kategori, "skor_umum": s_umum,
            "skor_metode": s_metode, "skor_nabung": s_nabung, "skor": round(skor, 2),
        })

    # seri skor: merchant/kategori yang paling sering dikunjungi, lalu estimasi hemat
    lolos = sorted(lolos, key=lambda x: (-x["skor"], -x["frek_dasar"], -x["estimasi_hemat"]))
    return lolos, ditahan, tidak_aktif


def momen_promo(p):
    return {"id": p["promo_id"], "jenis": "promo", "level": "Peluang", "prioritas": PRIORITAS["Peluang"],
            "judul": p["judul"],
            "pesan": f"{p['alasan']}. Bayar pakai {p['metode_bayar']}, hemat sampai {rupiah(p['estimasi_hemat'])} per bulan.",
            "label_tombol": "Lihat promo", "halaman": "WondrSaver", "dampak": p["estimasi_hemat"],
            "angka": {"estimasi_hemat": rupiah(p["estimasi_hemat"]), "merchant": p["merchant"]}}


def urutkan_momen(advice, promo_lolos):
    """C4: prioritas, lalu urutan aturan (R1 sebelum R2), lalu nominal dampak."""
    semua = list(advice) + ([momen_promo(promo_lolos[0])] if promo_lolos else [])
    return sorted(semua, key=lambda x: (x["prioritas"], URUTAN_ATURAN.get(x["id"], 9), -x["dampak"]))


def pilih_popup(momen, maks=3):
    """MK-03: maksimal 3 momen. Satu slot disediakan untuk promo teratas jika ada."""
    advice = [x for x in momen if x["jenis"] == "advice"]
    promo = [x for x in momen if x["jenis"] == "promo"]
    if not promo:
        return advice[:maks]
    return advice[:maks - 1] + promo[:1]


# ---------------------------------------------------------------- analisis lengkap
def analisis(tr, profil, promo, merchant, asumsi=None, klaim=None):
    m = hitung_metrik(tr, profil)
    label = label_perilaku(m)
    adv = daftar_advice(m)
    kritis = any(a["level"] == "Kritis" for a in adv)
    lolos, ditahan, tidak_aktif = cocokkan_promo(tr, m, label, profil, promo, merchant, klaim, kritis)
    indikator = indikator_risiko(m)
    pr = proyeksi(m, profil["usia"], asumsi)
    return {"metrik": m, "label": label, "proyeksi": pr,
            "advice": adv, "kritis": kritis, "promo": lolos, "promo_ditahan": ditahan,
            "promo_tidak_aktif": tidak_aktif, "momen": urutkan_momen(adv, lolos),
            "indikator": indikator, "roadmap": roadmap_finansial(m, profil, int(pr["tahun"]))}



def payload_llm(profil, hasil):
    """Input JSON ke LLM (B6.1). Hanya nama depan dan angka agregat (NFR-04)."""
    m, pr = hasil["metrik"], hasil["proyeksi"]
    dom = [{"kategori": r.kategori, "frekuensi": int(r.frekuensi), "nominal": round(r.nominal),
            "nominal_teks": rupiah(r.nominal), "merchant_favorit": r.merchant_favorit}
           for r in m["dominan"].head(3).itertuples()]
    return {
        "nama": str(profil["nama"]).split()[0],
        "usia": int(profil["usia"]),
        "tujuan": f"{profil['tujuan']} di usia {int(profil['usia_target_tujuan'])}",
        "label_perilaku": hasil["label"],
        "metrik": {
            "pemasukan_bulanan": rupiah(m["pemasukan"]),
            "pengeluaran_bulanan": rupiah(m["pengeluaran"]),
            "rasio_menabung": round(m["rasio_menabung"], 2),
            "rasio_pengeluaran": round(m["rasio_pengeluaran"], 2),
            "porsi_konsumtif": round(m["porsi_konsumtif"], 2),
            "numpang_lewat": round(m["numpang_lewat"], 2),
            "tren_pengeluaran": round(m["tren_pengeluaran"], 2),
        },
        "kategori_dominan": dom,
        "proyeksi": {
            "tahun_ke_depan": int(pr["tahun"]),
            "skenario_a": rupiah(pr["a"]["nominal"]),
            "skenario_b": rupiah(pr["b"]["nominal"]),
            "nilai_riil_a": rupiah(pr["a"]["riil"]),
            "nilai_riil_b": rupiah(pr["b"]["riil"]),
            "kecukupan_a": persen_bawah(pr["a"]["kecukupan"]),
            "kecukupan_b": persen_bawah(pr["b"]["kecukupan"]),
            "status_a": pr["a"]["status"],
            "status_b": pr["b"]["status"],
            "selisih_b_a": rupiah(pr["b"]["nominal"] - pr["a"]["nominal"]),
        },
        "fitur_wondr": FITUR_WONDR,
    }
