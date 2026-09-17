"""Integrasi LLM (B6 dan C5). LLM hanya menulis narasi dari angka engine.
Setiap fungsi punya template cadangan agar demo tetap berjalan tanpa API key (NFR-03)."""
import json
import os
import re
import time

MODEL = "gemini-flash-latest"
TIMEOUT = 20

ATURAN_UMUM = """Aturan wajib:
- Pakai HANYA angka yang ada di data. Jangan menghitung, membulatkan ulang, atau membuat angka baru.
- Jangan merekomendasikan produk investasi spesifik (saham, reksa dana tertentu, kripto).
- Nada suportif dan tidak menghakimi. Untuk label Defisit, nada lebih tegas namun tetap empatik.
- Bahasa Indonesia santai, sapa dengan "kamu".
- Balas HANYA dengan JSON valid, tanpa teks lain dan tanpa blok kode."""


# ---------------------------------------------------------------- dasar
def _kunci(api_key=None):
    return api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def panggil(system, messages, api_key=None, max_tokens=1200):
    """Kembalikan teks jawaban, atau None jika gagal/tanpa key.
    messages pakai format role Anthropic ("user"/"assistant"); dipetakan
    ke role Gemini ("user"/"model") di sini."""
    key = _kunci(api_key)
    if not key:
        return None
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        http_options=types.HttpOptions(timeout=TIMEOUT * 1000),
    )
    for percobaan in range(3):                       # server Gemini kadang 503/504 sesaat
        try:
            res = client.models.generate_content(model=MODEL, contents=contents, config=config)
            return res.text
        except Exception as e:  # jaringan, key salah, kuota habis, server sibuk
            print("LLM error:", e)
            kode = getattr(e, "code", None) or getattr(e, "status_code", None)
            if percobaan < 2 and kode in (503, 504):
                time.sleep(1.5 * (percobaan + 1))
                continue
            return None


def ambil_json(teks):
    if not teks:
        return None
    teks = re.sub(r"```(?:json)?", "", teks).strip()
    awal, akhir = teks.find("{"), teks.rfind("}")
    if awal < 0 or akhir < 0:
        return None
    try:
        return json.loads(teks[awal:akhir + 1])
    except json.JSONDecodeError:
        return None


def _jumlah_kata(teks):
    return len(str(teks).split())


# ---------------------------------------------------------------- B6 insight
FITUR_PER_LABEL = {
    "Defisit": ["Bayar Tagihan", "Life Goals", "QRIS"],
    "Numpang Lewat": ["Life Goals", "Tabungan Berjangka", "QRIS"],
    "Konsumtif": ["QRIS", "Life Goals", "Tabungan Berjangka"],
    "Penabung Disiplin": ["Deposito", "Tabungan Berjangka", "Life Goals"],
    "Berkembang": ["Life Goals", "QRIS", "Tabungan Berjangka"],
}


def validasi_insight(hasil, fitur):
    """B6.4: cek struktur, jumlah item, dan fitur_wondr."""
    if not isinstance(hasil, dict):
        return False
    if not all(k in hasil for k in ["ringkasan", "insight", "saran", "pesan_diri_depan"]):
        return False
    if not (isinstance(hasil["insight"], list) and len(hasil["insight"]) == 3):
        return False
    if not (isinstance(hasil["saran"], list) and len(hasil["saran"]) == 3):
        return False
    for i in hasil["insight"]:
        if not isinstance(i, dict) or not {"judul", "penjelasan", "data"} <= i.keys():
            return False
    for s in hasil["saran"]:
        if not isinstance(s, dict) or not {"aksi", "fitur_wondr", "alasan"} <= s.keys():
            return False
        if s["fitur_wondr"] not in fitur:
            return False
    return True


def template_insight(p):
    m, pr, label = p["metrik"], p["proyeksi"], p["label_perilaku"]
    tahun = pr["tahun_ke_depan"]
    dom = p["kategori_dominan"][0] if p["kategori_dominan"] else None
    fitur = FITUR_PER_LABEL.get(label, FITUR_PER_LABEL["Berkembang"])
    insight = [
        {"judul": "Kebiasaan menabung",
         "penjelasan": f"Porsi pemasukan yang kamu tabung saat ini {int(m['rasio_menabung'] * 100)}%.",
         "data": f"Rasio menabung {int(m['rasio_menabung'] * 100)}%"},
        {"judul": "Pengeluaran utama",
         "penjelasan": (f"Transaksi paling sering ada di {dom['kategori']}, {dom['frekuensi']} kali dalam 30 hari."
                        if dom else f"Pengeluaran bulananmu {m['pengeluaran_bulanan']}."),
         "data": dom["nominal_teks"] if dom else m["pengeluaran_bulanan"]},
        {"judul": f"Proyeksi {tahun} tahun ke depan",
         "penjelasan": f"Dengan kebiasaan sekarang, statusmu {pr['status_a']} dengan kecukupan {pr['kecukupan_a']}.",
         "data": f"Skenario A {pr['skenario_a']}"},
    ]
    saran_teks = {
        "Life Goals": "Sisihkan dana di awal bulan begitu gaji masuk",
        "Tabungan Berjangka": "Kunci sebagian dana agar tidak ikut terpakai",
        "Deposito": "Tempatkan dana yang belum dipakai dalam jangka menengah",
        "Bayar Tagihan": "Bayar tagihan tepat waktu agar tidak ada biaya tambahan",
        "QRIS": "Pantau belanja harian lewat pembayaran QRIS wondr",
    }
    saran = [{"aksi": saran_teks[f], "fitur_wondr": f, "alasan": f"Sesuai pola {label} kamu"} for f in fitur]
    pesan = {
        "Defisit": f"Aku kamu {tahun} tahun dari sekarang. Dulu pengeluaran kita sempat lebih besar dari pemasukan. "
                   f"Begitu kita mulai mengatur ulang, jalan ke depan jadi lebih ringan. Mulai dari satu langkah kecil hari ini.",
        "Aman": f"Aku kamu {tahun} tahun dari sekarang. Kebiasaan baikmu sekarang membuatku tenang. Pertahankan, ya.",
    }
    teks = pesan["Defisit"] if label == "Defisit" else (
        pesan["Aman"] if pr["status_a"] == "Aman" else
        f"Aku kamu {tahun} tahun dari sekarang. Kalau kebiasaan diperbaiki sedikit, proyeksi kita bisa naik ke {pr['skenario_b']}. "
        f"Itu kemungkinan, bukan ramalan. Keputusannya ada di tanganmu hari ini.")
    return {"ringkasan": f"Kamu termasuk pola {label}. Proyeksi {tahun} tahun ke depan berstatus {pr['status_a']}.",
            "insight": insight, "saran": saran, "pesan_diri_depan": teks}


def buat_insight(payload, api_key=None):
    """Kembalikan (hasil, sumber). sumber = 'AI' atau 'Template'."""
    system = f"""Kamu adalah asisten keuangan wondr by BNI yang menjelaskan hasil perhitungan.
{ATURAN_UMUM}
- Tepat 3 insight dan tepat 3 saran.
- fitur_wondr hanya boleh salah satu dari: {", ".join(payload["fitur_wondr"])}.
- ringkasan maksimal 30 kata. pesan_diri_depan maksimal 60 kata, sudut pandang orang pertama sebagai \
{payload["nama"]} {payload["proyeksi"]["tahun_ke_depan"]} tahun dari sekarang.
Format:
{{"ringkasan": "", "insight": [{{"judul": "", "penjelasan": "", "data": ""}}],
 "saran": [{{"aksi": "", "fitur_wondr": "", "alasan": ""}}], "pesan_diri_depan": ""}}"""
    pesan = [{"role": "user", "content": "Data nasabah:\n" + json.dumps(payload, ensure_ascii=False)}]
    for _ in range(2):                       # percobaan awal + 1 kali ulang
        hasil = ambil_json(panggil(system, pesan, api_key))
        if validasi_insight(hasil, payload["fitur_wondr"]):
            return hasil, "AI"
        if not _kunci(api_key):
            break
    return template_insight(payload), "Template"


# ---------------------------------------------------------------- C5 teks advice
def validasi_advice(item):
    return (isinstance(item, dict) and {"judul", "pesan", "label_tombol"} <= item.keys()
            and _jumlah_kata(item["judul"]) <= 8 and _jumlah_kata(item["pesan"]) <= 40)


def teks_advice(advice, label, nama, tahun=10, api_key=None):
    """Kembalikan (dict id -> teks, sumber). Item yang tidak valid memakai template."""
    hasil = {a["id"]: {k: a[k] for k in ["judul", "pesan", "label_tombol"]} for a in advice}
    if not advice or not _kunci(api_key):
        return hasil, "Template"
    data = [{"id": a["id"], "level": a["level"], "angka": a["angka"],
             "aksi_default": a["label_tombol"]} for a in advice]
    system = f"""Kamu menulis pesan pop-up singkat untuk aplikasi wondr by BNI atas nama {nama}, membayangkan dirinya {tahun} tahun ke depan.
{ATURAN_UMUM}
- judul maksimal 8 kata, pesan maksimal 40 kata, label_tombol maksimal 3 kata.
- Pola nasabah: {label}.
Format: {{"R1": {{"judul": "", "pesan": "", "label_tombol": ""}}, ...}} memakai id dari data."""
    jawab = ambil_json(panggil(system, [{"role": "user", "content": json.dumps(data, ensure_ascii=False)}], api_key))
    sumber = "Template"
    if isinstance(jawab, dict):
        for k, v in jawab.items():
            if k in hasil and validasi_advice(v):
                hasil[k] = {x: v[x] for x in ["judul", "pesan", "label_tombol"]}
                sumber = "AI"
    return hasil, sumber


# ---------------------------------------------------------------- B6 chat lanjutan
def chat(payload, riwayat, api_key=None):
    tahun = payload["proyeksi"]["tahun_ke_depan"]
    system = f"""Kamu berperan sebagai {payload["nama"]} versi {tahun} tahun dari sekarang (usia {payload["usia"] + tahun} tahun), \
mengobrol santai dengan dirinya yang saat ini berusia {payload["usia"]} tahun.
Data yang boleh dipakai (satu-satunya sumber angka, jangan menghitung atau membulatkan angka baru):
{json.dumps(payload, ensure_ascii=False)}
Aturan:
- Jawab pertanyaan yang ditanyakan secara langsung dan spesifik. Jangan mengulang kalimat pembuka atau \
frasa yang sama di setiap balasan -- variasikan cara bicara seperti obrolan sungguhan, bukan template.
- Hangat, suportif, bahasa Indonesia santai, maksimal 5 kalimat.
- Kalau pertanyaannya soal keuangan/proyeksi, boleh sebut angka dari data. Kalau pertanyaannya hal umum \
(kabar, sapaan, dll), jawab natural saja tanpa memaksakan angka atau proyeksi.
- Beri satu saran konkret yang terhubung ke fitur wondr dalam data, hanya kalau relevan dengan pertanyaan.
- Jangan merekomendasikan produk investasi spesifik.
- Sebut bahwa ini kemungkinan bukan ramalan HANYA saat membahas angka proyeksi, tidak perlu diulang tiap balasan."""
    teks = panggil(system, riwayat[-12:], api_key, max_tokens=500)
    if teks:
        return teks, "AI"
    pr = payload["proyeksi"]
    return (f"Aku kamu {tahun} tahun dari sekarang. Dengan kebiasaan sekarang, proyeksi kita {pr['skenario_a']} "
            f"dengan status {pr['status_a']}. Kalau kebiasaan diperbaiki, bisa menjadi {pr['skenario_b']}. "
            "Ini kemungkinan, bukan ramalan. Aktifkan AI untuk ngobrol lebih jauh."), "Template"
