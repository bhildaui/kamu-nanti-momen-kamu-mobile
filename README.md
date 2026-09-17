# wondr: WondrCast & WondrSaver (MVP Hackathon)

## Jalankan
    pip install -r requirements.txt
    streamlit run app.py

## Uji requirement
    python uji_requirement.py

## Ubah data dari Excel
Taruh file .xlsx di folder data/, lalu:
    python siapkan_data.py

## Struktur
- app.py              tampilan (Beranda + pop-up, WondrCast, WondrSaver, Data Nasabah)
- engine.py           semua perhitungan: metrik, label, proyeksi, advice R1-R7, promo, indikator risiko
- llm.py              integrasi Gemini: insight JSON, teks advice, chat, template cadangan
- data_input.py       form input demo dan 4 skenario cepat
- uji_requirement.py  uji otomatis acceptance criteria
- siapkan_data.py     konversi Excel ke CSV
- data/               nasabah, transaksi, merchant, promo (dummy)
- assets/             avatar pria/wanita, senang/sedih
