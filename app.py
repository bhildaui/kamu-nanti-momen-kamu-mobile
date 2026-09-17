"""Demo MVP wondr: WondrCast & WondrSaver -- versi mobile (satu kolom).
Logic backend (engine.py, llm.py, data_input.py) identik dengan versi desktop;
yang beda cuma tata letak: semua kolom ditumpuk vertikal, lebar dibatasi
~430px supaya terasa seperti aplikasi ponsel. Jalankan: streamlit run app.py"""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import data_input as D
import engine as E
import llm as L

ASSETS = Path(__file__).parent / "assets"
HALAMAN = ["Beranda", "WondrCast", "WondrSaver", "Data Nasabah"]
WARNA_LEVEL = {"Kritis": "red", "Waktu": "blue", "Peringatan": "orange", "Peluang": "green"}
WARNA_STATUS = {"Aman": "green", "Waspada": "orange", "Berisiko": "red"}

st.set_page_config(page_title="wondr | WondrCast (Mobile)", layout="centered")
st.logo(str(ASSETS / "logo_wondr.png"), size="large")
st.markdown("""<style>
.block-container {padding-top: 1.5rem; max-width: 430px;}
.kecil {font-size: 0.85rem; color: #6b7280;}
.angka {font-size: 1.6rem; font-weight: 700; margin: 0;}
section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div {
    border-right: 3px solid #FF8500 !important;
    background-color: #FFFFFF !important;
}
section[data-testid="stSidebar"] hr {border-color: #E0EE59 !important;}
[data-testid="stLogo"] {height: 9rem !important; width: auto !important;}
/* backdrop pop-up: elemen fixed fullscreen ini adalah lapisan DI BELAKANG
   kotak dialog (kotak dialog putih ada di elemen anak terpisah, sudah
   solid & tajam secara native -- jadi cukup blur di sini saja).
   Konsep Wondr: gelap transparan + blur, kotak dialog rounded-3xl dengan
   shadow yang sangat halus. */
[data-testid="stDialog"] {
    background-color: rgba(0,0,0,0.45) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
}
[data-testid="stDialog"] > div {
    border-radius: 24px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.12) !important;
}
[data-testid="stChatMessage"], [data-testid="stChatInput"] {
    background-color: #FFFFFF !important;
    border: 1px solid rgba(255,133,0,0.5) !important;
}
/* div pembungkus tanpa testid di dalam stChatInput -- bawaan Streamlit
   masih pakai secondaryBackgroundColor (tosca), dipaksa putih juga */
[data-testid="stChatInput"] > div {background-color: #FFFFFF !important;}
[data-testid="stChatInputSubmitButton"] {background-color: rgba(255,133,0,0.15) !important;}
[data-testid="stChatInput"] textarea {
    background-color: #FFFFFF !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"] textarea:focus {
    outline: none !important;
    box-shadow: none !important;
    border: none !important;
}

/* Tipografi konten chat, gaya bersih & minimalis (setara Tailwind --
   CDN Tailwind tidak jalan di sandbox markdown Streamlit, jadi ditulis
   sebagai CSS biasa dengan hasil visual yang sama). */
[data-testid="stChatMessageContent"] p {
    font-size: 0.95rem;
    line-height: 1.75;
    letter-spacing: 0.01em;
    color: #3f3f46;
    margin: 0 0 1em;
}
[data-testid="stChatMessageContent"] p:last-child {margin-bottom: 0;}
[data-testid="stChatMessageContent"] h1,
[data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3 {
    color: #18181b;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 1.25em 0 0.5em;
}
[data-testid="stChatMessageContent"] ul,
[data-testid="stChatMessageContent"] ol {
    margin: 0.75em 0 1em;
    padding-left: 1.4em;
}
[data-testid="stChatMessageContent"] li {
    margin-bottom: 0.5em;
    line-height: 1.7;
    color: #3f3f46;
}
[data-testid="stChatMessageContent"] blockquote {
    border-left: 3px solid #FF8500;
    padding-left: 1em;
    margin: 1em 0;
    color: #52525b;
    font-style: italic;
}
[data-testid="stChatMessageContent"] code {
    background-color: #f4f4f5;
    color: #3f3f46;
    padding: 0.15em 0.4em;
    border-radius: 4px;
    font-size: 0.85em;
}
[data-testid="stChatMessageContent"] pre {
    background-color: #f4f4f5;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    padding: 1em;
    overflow-x: auto;
    margin: 1em 0;
}
[data-testid="stChatMessageContent"] pre code {background: none; padding: 0;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data dan state
@st.cache_data(show_spinner="Memuat data nasabah...")
def muat():
    nas, tr, mer, pro = E.load_data()
    return nas, dict(tuple(tr.groupby("user_id"))), mer, pro


nasabah, trx_per_user, merchant, promo = muat()

DEFAULT_STATE = {
    "page": "Beranda", "sumber": "Nasabah dummy", "klaim": {}, "events": [],
    "popup_shown": set(), "hide_until": {}, "popup_idx": 0, "popup_aktif": None, "chat": {}, "insight": {},
    "advice_teks": {}, "as_r": 4, "as_g": 5, "as_inf": 3, "as_hemat": 20, "as_tahun": 10,
    "as_basis": "pendapatan", "input_disubmit": False,
}
for k, v in DEFAULT_STATE.items():
    st.session_state.setdefault(k, v)
for k, v in D.DEFAULT.items():
    st.session_state.setdefault(f"f_{k}", v)

# navigasi dari tombol (harus diproses sebelum widget menu dibuat)
if "nav_to" in st.session_state:
    st.session_state.page = st.session_state.pop("nav_to")
if "toast" in st.session_state:
    st.toast(st.session_state.pop("toast"))
if "sumber_to" in st.session_state:
    st.session_state.sumber = st.session_state.pop("sumber_to")


def pindah(halaman):
    if halaman not in HALAMAN:            # fitur wondr di luar prototipe
        st.session_state.toast = f"Membuka {halaman} di wondr (simulasi)."
        halaman = "WondrSaver"
    st.session_state.nav_to = halaman
    st.session_state.popup_aktif = None
    st.rerun()


def jaga_state(*kunci_state):
    """Tulis ulang nilai state tepat sebelum widget dibuat.
    Tanpa ini, widget yang baru pertama muncul menampilkan nilai minimum (perilaku Streamlit)."""
    for k in kunci_state:
        st.session_state[k] = st.session_state[k]


def catat(momen_id, kejadian):
    st.session_state.events.append({
        "waktu": datetime.now().strftime("%H:%M:%S"), "nasabah": st.session_state.get("kunci", ""),
        "momen": momen_id, "event": kejadian})


def avatar(gender, senang):
    return str(ASSETS / f"{gender}_{'senang' if senang else 'sedih'}.png")


def bar_gauge(nilai):
    """Bar gaya wondr: pill oranye, badge bulat berisi persen di ujung isian,
    bulatan tosca tetap di kedua ujung (awal dan batas maksimum)."""
    nilai = max(0, min(100, nilai))
    return f"""
    <div style="position:relative;height:30px;margin:6px 0 2px;
                background:#FBEBD3;border-radius:15px;">
      <div style="position:absolute;left:0;top:0;height:30px;width:{nilai}%;
                  background:linear-gradient(90deg,#F2994A,#F7C08A);border-radius:15px;"></div>
      <div style="position:absolute;left:2px;top:50%;transform:translate(0,-50%);
                  width:20px;height:20px;border-radius:50%;background:#4FD1C5;
                  box-shadow:0 1px 3px rgba(0,0,0,.18);"></div>
      <div style="position:absolute;left:{nilai}%;top:50%;transform:translate(-50%,-50%);
                  width:36px;height:36px;border-radius:50%;background:#E8763C;color:white;
                  display:flex;align-items:center;justify-content:center;font-weight:700;
                  font-size:11px;box-shadow:0 2px 4px rgba(0,0,0,.18);z-index:2;">{nilai}%</div>
      <div style="position:absolute;right:2px;top:50%;transform:translate(0,-50%);
                  width:20px;height:20px;border-radius:50%;background:#4FD1C5;
                  box-shadow:0 1px 3px rgba(0,0,0,.18);"></div>
    </div>"""


def grafik_proyeksi(seri, tahun_proyeksi):
    """Line chart proyeksi. Dibuat pakai Altair (bukan st.line_chart) supaya garis
    Skenario A dan B tetap terlihat dua-duanya walau nilainya persis sama
    (garis putus-putus vs garis penuh) -- sebelumnya salah satu bisa 'hilang'
    tertutup garis lain saat nasabah tidak punya pengeluaran konsumtif."""
    panjang = seri.reset_index().melt("usia", var_name="Skenario", value_name="Saldo")
    return alt.Chart(panjang).mark_line(strokeWidth=3).encode(
        x=alt.X("usia:Q", title=f"Usia ({tahun_proyeksi} tahun ke depan)"),
        y=alt.Y("Saldo:Q", title="Saldo (Rp)"),
        color=alt.Color("Skenario:N", scale=alt.Scale(range=["#FF8500", "#2E7D32"]),
                        legend=alt.Legend(title=None, orient="top")),
        strokeDash=alt.StrokeDash("Skenario:N", legend=None),
    ).properties(height=280)


# ---------------------------------------------------------------- form input manual (halaman Data Nasabah)
def isi_skenario(nama_skenario):
    for k, v in D.SKENARIO[nama_skenario].items():
        st.session_state[f"f_{k}"] = v


def form_input():
    """Form input manual, satu kolom + dikelompokkan lewat expander
    (versi mobile -- layar sempit, tidak ada tempat untuk 3 kolom)."""
    st.caption("Pilih skenario cepat untuk isi otomatis, atau isi sendiri di bawah.")
    kol = st.columns(2)
    for i, nama_s in enumerate(D.SKENARIO):
        kol[i % 2].button(nama_s, on_click=isi_skenario, args=(nama_s,), width="stretch")

    jaga_state(*[f"f_{k}" for k in D.DEFAULT])
    with st.form("form_input"):
        with st.expander("Profil dasar", expanded=True):
            st.text_input("Nama", key="f_nama", max_chars=20)
            st.number_input("Usia", 18, 45, key="f_usia")
            st.selectbox("Jenis kelamin avatar", ["pria", "wanita"], key="f_jenis_kelamin")
            st.number_input("Pendapatan bulanan (Rp)", 0, 200_000_000, step=500_000, key="f_pendapatan")
            st.number_input("Saldo saat ini (Rp)", 0, 2_000_000_000, step=500_000, key="f_saldo")
            st.text_input("Tujuan hidup", key="f_tujuan")
            st.number_input("Usia target tujuan", 19, 80, key="f_usia_target")

        with st.expander("Pengeluaran per bulan (Rp)"):
            for kat in D.KATEGORI_FORM:
                st.number_input(kat, 0, 100_000_000, step=50_000, key=f"f_{kat}")

        with st.expander("Kebiasaan lainnya"):
            st.number_input("Frekuensi kopi per bulan", 0, 60, key="f_frek_kopi")
            st.selectbox("Merchant kopi favorit",
                        merchant[merchant.kategori == "Kopi"].merchant_nama.tolist(), key="f_merchant_kopi")
            st.slider("Porsi gaji ke e-wallet (%)", 0, 100, key="f_porsi_ewallet")
            st.number_input("Setoran tabungan per bulan (Rp)", 0, 100_000_000, step=100_000, key="f_setoran")
            st.number_input("Cicilan per bulan (Rp)", 0, 100_000_000, step=100_000, key="f_cicilan")
            st.toggle("Lonjakan minggu ini", key="f_lonjakan")
            st.selectbox("Kategori lonjakan", E.KAT_MERCHANT, key="f_kategori_lonjakan")

        kirim = st.form_submit_button("Proses data", type="primary", width="stretch")

    if kirim:
        nilai = {k: st.session_state[f"f_{k}"] for k in D.DEFAULT}
        error = D.validasi(nilai)
        if error:
            for e in error:
                st.error(e)
            return
        st.session_state.input_data = D.buat_transaksi(nilai, merchant)
        st.session_state.input_disubmit = True
        st.session_state.sumber_to = "Input manual"
        st.session_state.nav_to = "Beranda"
        st.rerun()


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.caption("Prototipe WondrCast & WondrSaver (Mobile)")
    st.radio("Menu", HALAMAN, key="page")
    st.divider()
    st.radio("Sumber data", ["Nasabah dummy", "Input manual"], key="sumber")

    if st.session_state.sumber == "Nasabah dummy":
        utama = nasabah.head(5)
        opsi = [f"{r.user_id} · {r.nama} ({r.persona})" for r in utama.itertuples()]
        opsi += [f"{r.user_id} · {r.nama} ({r.persona})" for r in nasabah.iloc[5:].itertuples()]
        pilihan = st.selectbox("Pilih nasabah", opsi, key="pilih_nasabah")
        uid = pilihan.split(" · ")[0]
    else:
        uid = "INPUT"
        if not st.session_state.input_disubmit and st.session_state.page != "Data Nasabah":
            st.session_state.nav_to = "Data Nasabah"
            st.rerun()

    st.divider()
    st.caption("Semua nasabah, transaksi, merchant, dan promo adalah data dummy. "
               "Hasil adalah simulasi, bukan nasihat keuangan profesional.")

try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    api_key = None

# ---------------------------------------------------------------- nasabah aktif
if uid == "INPUT":
    if "input_data" not in st.session_state:
        st.session_state.input_data = D.buat_transaksi(D.DEFAULT, merchant)
    profil, transaksi = st.session_state.input_data
    kunci = "INPUT-" + hashlib.md5(transaksi.to_csv().encode()).hexdigest()[:8]
else:
    profil = nasabah[nasabah.user_id == uid].iloc[0]
    transaksi = trx_per_user[uid]
    kunci = uid
st.session_state.kunci = kunci
gender = profil["gender"]

asumsi = {"r": st.session_state.as_r / 100, "g": st.session_state.as_g / 100,
          "inflasi": st.session_state.as_inf / 100, "hemat": st.session_state.as_hemat / 100,
          "tahun_proyeksi": st.session_state.as_tahun, "basis_kebutuhan": st.session_state.as_basis}
hasil = E.analisis(transaksi, profil, promo, merchant, asumsi, st.session_state.klaim)
m, pr, label = hasil["metrik"], hasil["proyeksi"], hasil["label"]
payload = E.payload_llm(profil, hasil)
nama = payload["nama"]


def teks_momen(momen):
    """Teks advice dari LLM (C5) dengan cache per nasabah; promo memakai teks engine."""
    advice = [x for x in hasil["advice"]]
    sidik = kunci + json.dumps([a["angka"] for a in advice], ensure_ascii=False)
    if sidik not in st.session_state.advice_teks:
        with st.spinner("Menyiapkan pesan..."):
            st.session_state.advice_teks[sidik] = L.teks_advice(advice, label, nama, int(pr["tahun"]), api_key)
    teks, sumber = st.session_state.advice_teks[sidik]
    if momen["jenis"] == "advice" and momen["id"] in teks:
        return {**momen, **teks[momen["id"]]}, sumber
    return momen, "Engine"


# ---------------------------------------------------------------- pop-up WondrSaver
def tutup_x():
    st.session_state.popup_aktif = None
    daftar = E.pilih_popup(hasil["momen"])
    if daftar:
        catat(daftar[min(st.session_state.popup_idx, len(daftar) - 1)]["id"], "tutup")


@st.dialog("WondrSaver", width="medium", on_dismiss=tutup_x)
def popup():
    daftar = E.pilih_popup(hasil["momen"])
    i = min(st.session_state.popup_idx, len(daftar) - 1)
    momen, sumber = teks_momen(daftar[i])
    senang = momen["level"] in ("Waktu", "Peluang")

    st.image(avatar(gender, senang), width=110)
    st.badge(momen["level"], color=WARNA_LEVEL[momen["level"]])
    st.subheader(momen["judul"])
    st.write(momen["pesan"])

    if st.button(momen["label_tombol"], type="primary", width="stretch"):
        catat(momen["id"], "klik")
        pindah(momen["halaman"])

    if len(daftar) > 1:
        nav_kiri, dots, nav_kanan = st.columns([1, 6, 1])
        if nav_kiri.button("‹", key="carousel_prev", width="stretch", disabled=(i == 0)):
            st.session_state.popup_idx = i - 1
            catat(daftar[i - 1]["id"], "tampil")
            st.rerun()
        titik = "".join(
            f"<span style='display:inline-block;width:{9 if j == i else 7}px;"
            f"height:{9 if j == i else 7}px;border-radius:50%;margin:0 4px;"
            f"background:{'#FF8500' if j == i else '#e4e4e7'};'></span>"
            for j in range(len(daftar))
        )
        dots.markdown(f"<div style='text-align:center;padding-top:9px;'>{titik}</div>",
                      unsafe_allow_html=True)
        if nav_kanan.button("›", key="carousel_next", width="stretch", disabled=(i == len(daftar) - 1)):
            st.session_state.popup_idx = i + 1
            catat(daftar[i + 1]["id"], "tampil")
            st.rerun()

    if st.button("Tutup", width="stretch"):
        st.session_state.popup_aktif = None
        catat(momen["id"], "tutup")
        st.rerun()
    if st.button("Jangan tampilkan hari ini", width="stretch"):
        st.session_state.popup_aktif = None
        st.session_state.hide_until[kunci] = datetime.now() + timedelta(hours=24)
        catat(momen["id"], "sembunyikan 24 jam")
        st.rerun()


def reset_momen():
    st.session_state.popup_shown = set()
    st.session_state.hide_until = {}
    st.session_state.popup_idx = 0
    st.session_state.popup_aktif = None
    st.session_state.klaim = {}
    catat("-", "reset momen")


def buka_popup_jika_perlu():
    """MK-01: tampil sekali per sesi. Dialog dibuka ulang selama masih aktif."""
    daftar = E.pilih_popup(hasil["momen"])
    if daftar and st.session_state.popup_aktif == kunci:
        popup()
        return
    tersembunyi = st.session_state.hide_until.get(kunci, datetime.min) > datetime.now()
    if daftar and kunci not in st.session_state.popup_shown and not tersembunyi:
        st.session_state.popup_shown.add(kunci)
        st.session_state.popup_aktif = kunci
        st.session_state.popup_idx = 0
        catat(daftar[0]["id"], "tampil")
        popup()


# ---------------------------------------------------------------- halaman: Beranda
def halaman_beranda():
    st.title(f"Hai, {nama}")

    st.metric("Saldo", E.rupiah(m["saldo"]))
    st.metric("Pemasukan 30 hari", E.rupiah(m["masuk_30"]))
    st.metric("Pengeluaran 30 hari", E.rupiah(m["keluar_30"]),
              delta=E.rupiah(m["masuk_30"] - m["keluar_30"]), delta_color="normal")

    baris1 = st.columns(2)
    baris1[0].button("Transfer", width="stretch", disabled=True)
    baris1[1].button("QRIS", width="stretch", disabled=True)
    baris2 = st.columns(2)
    baris2[0].button("Life Goals", width="stretch", disabled=True)
    baris2[1].button("Bayar Tagihan", width="stretch", disabled=True)

    with st.container(border=True):
        st.markdown("#### WondrCast")
        st.image(avatar(gender, pr["a"]["status"] == "Aman"), width=100)
        st.badge(f"Status {int(pr['tahun'])} tahun ke depan: {pr['a']['status']}", color=WARNA_STATUS[pr["a"]["status"]])
        st.write(f"Pola keuanganmu: **{label}**")
        st.write(f"Proyeksi kebiasaan sekarang: **{E.rupiah(pr['a']['nominal'])}**")
        if st.button("Lihat WondrCast", width="stretch"):
            pindah("WondrCast")

    with st.container(border=True):
        st.markdown("#### WondrSaver")
        if not hasil["momen"]:
            st.write("Belum ada momen penting.")
        for momen in hasil["momen"][:4]:
            st.markdown(f":{WARNA_LEVEL[momen['level']]}-badge[{momen['level']}] {momen['judul']}")
        if st.button("Lihat semua", width="stretch"):
            pindah("WondrSaver")

    st.divider()
    if st.button("Tampilkan pop-up lagi (demo)", width="stretch"):
        st.session_state.popup_shown.discard(kunci)
        st.session_state.hide_until.pop(kunci, None)
        st.rerun()
    if st.button("Reset momen (demo)", width="stretch"):
        reset_momen()
        st.rerun()
    if st.session_state.hide_until.get(kunci, datetime.min) > datetime.now():
        st.caption("Pop-up disembunyikan sampai besok untuk nasabah ini.")

    buka_popup_jika_perlu()


# ---------------------------------------------------------------- halaman: WondrCast
def kartu_skenario(kolom, judul, s, setoran):
    with kolom.container(border=True):
        st.markdown(f"**{judul}**")
        st.image(avatar(gender, s["status"] == "Aman"), width=130)
        st.badge(s["status"], color=WARNA_STATUS[s["status"]])
        st.markdown(f"<p class='angka'>{E.rupiah(s['nominal'])}</p>", unsafe_allow_html=True)
        st.markdown(f"<span class='kecil'>Nilai riil hari ini {E.rupiah(s['riil'])} · "
                    f"kecukupan {E.persen_bawah(s['kecukupan'])}</span>", unsafe_allow_html=True)
        st.caption(f"Setoran awal {E.rupiah(setoran)} per bulan")
        if s["catatan"]:
            st.error(s["catatan"])


def halaman_wondrcast():
    tahun = int(pr["tahun"])
    st.title("WondrCast")
    st.write(f"Gambaran keuangan **{nama}** {tahun} tahun ke depan berdasarkan transaksi 90 hari terakhir.")
    st.badge(f"Pola: {label}", color="violet")
    if pr["data_terbatas"]:
        st.warning("Pengeluaran yang tercatat kurang dari 20% pemasukan. Kemungkinan sebagian transaksi "
                   "terjadi di luar wondr, sehingga proyeksi bisa terlalu optimistis.")

    kartu_skenario(st, "A. Kebiasaan tetap", pr["a"], pr["setoran_a"])
    kartu_skenario(st, "B. Kebiasaan diperbaiki", pr["b"], pr["setoran_b"])
    with st.container(border=True):
        st.markdown("**Atur asumsi**")
        jaga_state("as_hemat", "as_tahun", "as_r", "as_g", "as_inf", "as_basis")
        st.slider("Proyeksi (tahun ke depan)", 1, 30, key="as_tahun",
                 help="Sampai berapa tahun ke depan saldo ini diproyeksikan, dihitung mulai dari sekarang.")
        st.slider("Porsi hemat pengeluaran konsumtif (%)", 0, 50, key="as_hemat",
                 help="Untuk Skenario B (Kebiasaan diperbaiki): berapa persen dari pengeluaran kopi, "
                      "hiburan, dan belanja online yang dialihkan jadi tabungan tiap bulan.")
        with st.expander("Pengaturan lanjutan"):
            st.slider("Imbal hasil tabungan per tahun (%)", 0, 10, key="as_r",
                     help="Perkiraan bunga/imbal hasil dari uang yang ditabung, per tahun.")
            st.slider("Kenaikan pendapatan per tahun (%)", 0, 10, key="as_g",
                     help="Perkiraan kenaikan gaji/pendapatan tiap tahun.")
            st.slider("Inflasi per tahun (%)", 0, 10, key="as_inf",
                     help="Perkiraan kenaikan harga barang/jasa tiap tahun, dipakai untuk menghitung "
                          "nilai riil uang di masa depan (uang segitu setara berapa kalau dibelanjakan hari ini).")
            st.selectbox("Dasar target dana", ["pendapatan", "pengeluaran"], key="as_basis",
                         help="Target dana dihitung sebagai kelipatan dari pendapatan ATAU pengeluaran "
                              "bulanan nasabah ini.")

    st.altair_chart(grafik_proyeksi(pr["seri"], tahun), use_container_width=True)
    st.caption(f"Target dana: {E.rupiah(pr['kebutuhan'])} (nilai hari ini). "
               "Simulasi, bukan nasihat keuangan profesional. Asumsi adalah angka ilustratif tim, bukan angka resmi BNI.")

    with st.expander("Asumsi dan metrik perilaku"):
        st.dataframe(E.tabel_asumsi(pr["asumsi"]), hide_index=True, width="stretch")
        st.dataframe(E.tabel_metrik(m), hide_index=True, width="stretch")

    # indikator & metrik risiko
    st.subheader("Indikator & Metrik Risiko")
    for ind in hasil["indikator"]:
        with st.container(border=True):
            st.markdown(f"**{ind['judul']}**")
            st.caption(ind["sub"])
            st.markdown(f"<div style='display:flex;justify-content:space-between;"
                        f"font-size:0.8rem;color:#6b7280;'><span>{ind['label_rendah']}</span>"
                        f"<span>{ind['label_tinggi']}</span></div>", unsafe_allow_html=True)
            st.markdown(bar_gauge(ind["nilai"]), unsafe_allow_html=True)
            st.caption(ind["posisi"])
            st.write(ind["keterangan"])

    rm = hasil["roadmap"]
    st.markdown(
        f"""<div style="background:#FBEFD2;border-radius:14px;padding:18px 22px;margin-top:6px;">
<p style="font-weight:700;font-size:1.05rem;margin:0 0 10px;">{rm['judul']}</p>
<ul style="margin:0;padding-left:20px;">
{''.join(f"<li style='margin-bottom:8px;'><b>{f['label']}</b> : {', '.join(f['aksi'])}</li>" for f in rm['fase'])}
</ul>
</div>""",
        unsafe_allow_html=True,
    )

    # insight LLM (B6)
    st.subheader("Insight keuangan")
    teks_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    simpan = st.session_state.insight.get(kunci)
    perlu_baru = simpan is None
    if simpan and simpan[0] != teks_payload:
        st.info("Asumsi berubah. Klik Perbarui insight untuk menyesuaikan penjelasan.")
    if st.button("Perbarui insight", width="stretch"):
        perlu_baru = True
    if perlu_baru:
        with st.spinner("AI sedang menyusun insight..."):
            isi, sumber = L.buat_insight(payload, api_key)
        st.session_state.insight[kunci] = (teks_payload, isi, sumber)
    _, isi, sumber = st.session_state.insight[kunci]

    st.caption(f"Sumber teks: {'AI (Gemini)' if sumber == 'AI' else 'Template (AI tidak aktif atau gagal)'}")
    st.markdown(f"### Kamu termasuk pola :orange[{label}]")
    st.write(f"Proyeksi {tahun} tahun ke depan berstatus "
             f":{WARNA_STATUS[pr['a']['status']]}[**{pr['a']['status']}**].")
    for item in isi["insight"]:
        with st.container(border=True):
            st.markdown(f"**{item['judul']}**")
            st.write(item["penjelasan"])
            st.caption(item["data"])
    for item in isi["saran"]:
        with st.container(border=True):
            st.badge(item["fitur_wondr"], color="blue")
            st.markdown(f"**{item['aksi']}**")
            st.caption(item["alasan"])
    st.image(avatar(gender, pr["b"]["status"] == "Aman"), width=80)
    st.info(f"**Pesan dari {nama} {tahun} tahun ke depan:** {isi['pesan_diri_depan']}")

    # chat lanjutan (KN-10)
    st.subheader(f"Ngobrol dengan {nama} {tahun} tahun ke depan")
    riwayat = st.session_state.chat.setdefault(kunci, [])
    ava_depan = avatar(gender, pr["a"]["status"] == "Aman")
    for pesan in riwayat:
        with st.chat_message(pesan["role"], avatar=ava_depan if pesan["role"] == "assistant" else None):
            st.write(pesan["content"])
    tanya = st.chat_input(f"Tanya dirimu {tahun} tahun ke depan...")
    if tanya:
        riwayat.append({"role": "user", "content": tanya})
        with st.spinner("Mengetik..."):
            jawab, _ = L.chat(payload, riwayat, api_key)
        riwayat.append({"role": "assistant", "content": jawab})
        st.rerun()


# ---------------------------------------------------------------- halaman: WondrSaver
def halaman_momen():
    st.title("WondrSaver")
    st.caption("Semua momen dan promo untuk nasabah ini, termasuk yang tidak masuk pop-up.")

    st.subheader("Momen dan saran")
    if not hasil["momen"]:
        st.write("Belum ada momen penting.")
    for momen in hasil["momen"]:
        momen, _ = teks_momen(momen)
        with st.container(border=True):
            st.markdown(f":{WARNA_LEVEL[momen['level']]}-badge[{momen['level']}] "
                        f":gray-badge[{momen['id']}] **{momen['judul']}**")
            st.write(momen["pesan"])
            if st.button(momen["label_tombol"], key=f"aksi_{momen['id']}", width="stretch"):
                catat(momen["id"], "klik")
                st.toast(f"Aksi '{momen['label_tombol']}' dicatat (simulasi).")

    st.subheader("Promo untukmu")
    if hasil["kritis"]:
        st.warning("Ada kondisi keuangan kritis. Hanya promo yang membantu menabung yang ditampilkan.")
    if not hasil["promo"]:
        st.write("Belum ada promo yang relevan.")
    for p in hasil["promo"]:
        with st.container(border=True):
            st.markdown(f"**{p['judul']}** · {p['merchant']}")
            st.write(p["alasan"])
            st.caption(f"{p['mekanisme']} · {p['metode_bayar']} · kuota {p['kuota']}x per bulan"
                       + (f" · {p['syarat']}" if p["syarat"] else ""))
            st.metric("Estimasi hemat/bulan", E.rupiah(p["estimasi_hemat"]))
            dipakai = st.session_state.klaim.get(p["promo_id"], 0)
            if st.button("Claim Code", key=f"klaim_{p['promo_id']}", width="stretch"):
                st.session_state.klaim[p["promo_id"]] = dipakai + 1
                catat(p["promo_id"], "claim code")
                st.rerun()

    with st.expander("Perhitungan skor promo (C7.1)"):
        if hasil["promo"]:
            kolom = ["promo_id", "judul", "skor_merchant", "skor_kategori", "skor_umum",
                     "skor_metode", "skor_nabung", "skor", "frekuensi", "estimasi_hemat"]
            st.dataframe(pd.DataFrame(hasil["promo"])[kolom], hide_index=True, width="stretch")
    with st.expander(f"Promo ditahan ({len(hasil['promo_ditahan'])})"):
        st.dataframe(pd.DataFrame(hasil["promo_ditahan"], columns=["promo_id", "judul", "alasan"]),
                     hide_index=True, width="stretch")
    with st.expander(f"Promo tidak aktif ({len(hasil['promo_tidak_aktif'])})"):
        st.dataframe(pd.DataFrame(hasil["promo_tidak_aktif"], columns=["promo_id", "judul", "alasan"]),
                     hide_index=True, width="stretch")

    st.subheader("Riwayat event (MK-10)")
    ev = pd.DataFrame(st.session_state.events, columns=["waktu", "nasabah", "momen", "event"])
    st.dataframe(ev.iloc[::-1], hide_index=True, width="stretch", height=220)
    st.download_button("Unduh riwayat event", ev.to_csv(index=False), "event_momen.csv",
                       width="stretch")
    if st.button("Reset momen (demo)", width="stretch"):
        reset_momen()
        st.rerun()


def halaman_data():
    st.title("Data Nasabah")
    if st.session_state.sumber == "Input manual":
        with st.expander("Input data nasabah", expanded=not st.session_state.input_disubmit):
            form_input()
        st.divider()
    tab1, tab2 = st.tabs(["Profil dan transaksi", "Daftar nasabah"])
    with tab1:
        st.caption(f"Nasabah aktif: {kunci}")
        tampil = profil.rename({"persona": "persona (data)"}).to_frame("nilai").astype(str)
        tampil.loc["label hasil hitung"] = label
        st.dataframe(tampil, width="stretch")
        if len(m["kategori"]):
            kat = m["kategori"][["kategori", "frekuensi", "nominal", "porsi", "merchant_favorit"]].copy()
            kat["nominal"] = kat.nominal.map(E.rupiah)
            kat["porsi"] = kat.porsi.map(E.persen)
            st.markdown("**Ringkasan 30 hari terakhir**")
            st.dataframe(kat, hide_index=True, width="stretch")
        st.markdown("**Transaksi 90 hari**")
        st.dataframe(transaksi.sort_values("tanggal_waktu", ascending=False),
                     hide_index=True, width="stretch", height=320)
        st.download_button("Unduh transaksi (CSV)", transaksi.to_csv(index=False),
                           f"transaksi_{kunci}.csv")
    with tab2:
        persona = st.multiselect("Filter persona (kolom data)", sorted(nasabah.persona.unique()))
        daftar = nasabah[nasabah.persona.isin(persona)] if persona else nasabah
        st.dataframe(daftar, hide_index=True, width="stretch", height=420)
        st.caption("Pilih nasabah lewat panel kiri. Label di aplikasi dihitung ulang dari transaksi.")


{"Beranda": halaman_beranda, "WondrCast": halaman_wondrcast,
 "WondrSaver": halaman_momen, "Data Nasabah": halaman_data}[st.session_state.page]()
