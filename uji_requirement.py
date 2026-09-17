"""Uji otomatis acceptance criteria. Jalankan: python uji_requirement.py"""
import json
import engine as E
import llm as L
import data_input as D

nas, tr, mer, pro = E.load_data()
hasil_uji = []


def cek(kode, kondisi, keterangan):
    hasil_uji.append((kode, "LULUS" if kondisi else "GAGAL", keterangan))


def nasabah(uid, **kw):
    prof = nas[nas.user_id == uid].iloc[0]
    return prof, E.analisis(tr[tr.user_id == uid], prof, pro, mer, **kw)


# AC-KN1
_, h = nasabah("U004")
cek("AC-KN1", h["proyeksi"]["a"]["status"] == "Berisiko" and h["proyeksi"]["seri"].min().min() >= 0,
    "Dodi berstatus Berisiko, saldo proyeksi tidak minus")

# AC-KN2
prof, t = D.buat_transaksi(D.SKENARIO["Konsumtif"], mer)
h = E.analisis(t, prof, pro, mer)
cek("AC-KN2", h["label"] == "Konsumtif" and h["metrik"]["dominan"].kategori.iloc[0] == "Kopi",
    f"Skenario Konsumtif -> label {h['label']}, dominan {h['metrik']['dominan'].kategori.iloc[0]}")

# AC-KN3: LLM mengembalikan teks bukan JSON
asli = L.panggil
L.panggil = lambda *a, **k: "Maaf, saya tidak bisa menjawab dalam JSON."
payload = E.payload_llm(prof, h)
isi, sumber = L.buat_insight(payload, api_key="palsu")
cek("AC-KN3", sumber == "Template" and L.validasi_insight(isi, payload["fitur_wondr"]),
    "Output non-JSON diganti template tanpa error")

# jalur AI valid (mock) dan percobaan ulang
jawaban = [None, json.dumps({"ringkasan": "ok",
                             "insight": [{"judul": "a", "penjelasan": "b", "data": "c"}] * 3,
                             "saran": [{"aksi": "a", "fitur_wondr": "Life Goals", "alasan": "c"}] * 3,
                             "pesan_diri_depan": "halo"})]
L.panggil = lambda *a, **k: jawaban.pop(0)
isi, sumber = L.buat_insight(payload, api_key="palsu")
cek("B6.4", sumber == "AI", "Percobaan pertama gagal, percobaan ulang valid dipakai")
L.panggil = asli

# AC-KN4
_, h1 = nasabah("U003", asumsi={"hemat": 0.20})
_, h2 = nasabah("U003", asumsi={"hemat": 0.40})
p1, p2 = h1["proyeksi"], h2["proyeksi"]
cek("AC-KN4", p1["a"]["nominal"] == p2["a"]["nominal"] and p2["b"]["nominal"] > p1["b"]["nominal"],
    "Porsi hemat hanya mengubah skenario B")

# AC-KN5
isi, sumber = L.buat_insight(E.payload_llm(*nasabah("U003")), api_key=None)
cek("AC-KN5", sumber == "Template", "Tanpa API key, insight dari template")

# AC-MK1
_, h = nasabah("U004")
popup = E.pilih_popup(h["momen"])
tanpa_belanja = all(x["jenis"] == "advice" or x["id"] in {p["promo_id"] for p in h["promo"] if p["bantu_nabung"]}
                    for x in popup)
cek("AC-MK1", popup[0]["id"] == "R1" and tanpa_belanja, f"Pop-up Dodi: {[x['id'] for x in popup]}")

# AC-MK2
_, h = nasabah("U003")
popup = E.pilih_popup(h["momen"])
cek("AC-MK2", "PR001" in [x["id"] for x in popup] and h["promo"][0]["estimasi_hemat"] > 0,
    f"Pop-up Citra: {[x['id'] for x in popup]}, hemat {E.rupiah(h['promo'][0]['estimasi_hemat'])}")

# AC-MK5
prof, t = D.buat_transaksi({**D.SKENARIO["Konsumtif"], "kategori_lonjakan": "Kopi"}, mer)
h = E.analisis(t, prof, pro, mer)
ditahan = {x["promo_id"] for x in h["promo_ditahan"]}
cek("AC-MK5", {"PR001", "PR003"} <= ditahan, f"Promo kopi ditahan: {sorted(ditahan)}")

# AC-MK6
_, h = nasabah("U001")
cek("AC-MK6", "PR009" not in [p["promo_id"] for p in h["promo"]]
    and any(x["promo_id"] == "PR009" and x["alasan"] == "Kedaluwarsa" for x in h["promo_tidak_aktif"]),
    "PR009 kedaluwarsa tidak tampil")

# kuota habis
_, h = nasabah("U003", klaim={"PR001": 4})
cek("C7 kuota", any(x["promo_id"] == "PR001" and x["alasan"] == "Kuota habis" for x in h["promo_tidak_aktif"]),
    "PR001 kuota habis setelah 4 klaim")

# AC-MK7
L.panggil = lambda *a, **k: None
_, h = nasabah("U003")
teks, sumber = L.teks_advice(h["advice"], h["label"], "Citra", api_key="palsu")
cek("AC-MK7", sumber == "Template" and set(teks) == {a["id"] for a in h["advice"]}, "LLM gagal, teks advice dari template")
L.panggil = asli

for kode, status, ket in hasil_uji:
    print(f"{status:6s} {kode:9s} {ket}")
print(f"\n{sum(s == 'LULUS' for _, s, _ in hasil_uji)}/{len(hasil_uji)} lulus")
