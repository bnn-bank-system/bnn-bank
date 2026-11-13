"""Laporan lanjutan BNN: rasio keuangan, arus kas, perubahan ekuitas, jurnal penutup tahunan.

Rasio memakai saldo akhir periode (bukan rata-rata) dan disetahunkan dari awal tahun; acuan hanya patokan umum,
cocokkan dengan materi kuliah. CAR belum dihitung karena membutuhkan aset tertimbang menurut risiko.
"""
from datetime import date, timedelta

from akuntansi import buat_jurnal
from kredit import hitung_ckpn
from laporan import _saldo_per_akun, laba_rugi, posisi_keuangan

KAS = ("1.1.01", "1.1.02")


def _siap(conn):
    conn.execute("INSERT OR IGNORE INTO akun(kode, nama, kelompok, saldo_normal) "
                 "VALUES ('3.2.01','Laba ditahan','ekuitas','K')")
    conn.execute("""CREATE TABLE IF NOT EXISTS penutupan_tahun (
        tahun INTEGER PRIMARY KEY, no_jurnal TEXT NOT NULL, laba INTEGER NOT NULL)""")
    conn.commit()


def _persen(x):
    return f"{x:.2f}%".replace(".", ",")


# ---------- rasio ----------
def rasio(conn, sampai=None):
    sampai = sampai or date.today().isoformat()
    t = date.fromisoformat(sampai)
    awal_tahun = date(t.year, 1, 1).isoformat()
    s = {k: v for k, _, _, v in _saldo_per_akun(conn, None, sampai)}
    y = {k: v for k, _, _, v in _saldo_per_akun(conn, awal_tahun, sampai, False)}
    faktor = 365 / max((t - date(t.year, 1, 1)).days + 1, 1)

    kredit, dpk = s.get("1.2.01", 0), s.get("2.1.01", 0) + s.get("2.1.02", 0)
    h = hitung_ckpn(conn, sampai)
    tot_sisa = sum(r["sisa_pokok"] for r in h["rincian"])
    npl = sum(r["sisa_pokok"] for r in h["rincian"] if r["kolektibilitas"] >= 3)
    pend = sum(v for k, v in y.items() if k.startswith("4."))
    beban = sum(v for k, v in y.items() if k.startswith("5."))
    aset_produktif = s.get("1.1.02", 0) + kredit
    total_aset = posisi_keuangan(conn, sampai)["total_aset"]

    def bagi(a, b):
        return a / b * 100 if b else None

    ldr = bagi(kredit, dpk)
    npl_r = bagi(npl, tot_sisa)
    bopo = bagi(beban, pend)
    nim = bagi((y.get("4.1.01", 0) - y.get("5.1.01", 0)) * faktor, aset_produktif)
    roa = bagi((pend - beban) * faktor, total_aset)
    cover = bagi(-s.get("1.2.09", 0), kredit)

    def baris(nama, nilai, acuan, ok):
        return {"nama": nama, "nilai": nilai, "teks": _persen(nilai) if nilai is not None else "-",
                "acuan": acuan, "status": "-" if nilai is None or ok is None else ("baik" if ok(nilai) else "perhatian")}

    return {"baris": [
        baris("LDR (kredit / DPK)", ldr, "78% sampai 92%", lambda v: 78 <= v <= 92),
        baris("NPL gross (kol 3-5 / kredit)", npl_r, "di bawah 5%", lambda v: v < 5),
        baris("BOPO (beban / pendapatan)", bopo, "di bawah 94%", lambda v: v < 94),
        baris("ROA (disetahunkan)", roa, "di atas 1,5%", lambda v: v > 1.5),
        baris("NIM (disetahunkan)", nim, "semakin tinggi semakin baik", None),
        baris("Cadangan CKPN / kredit", cover, "semakin tinggi semakin aman", None),
    ]}


# ---------- arus kas ----------
def _kas_sampai(conn, tgl):
    return conn.execute("""SELECT COALESCE(SUM(d.debit - d.kredit),0) FROM jurnal_detail d
                           JOIN jurnal j ON j.id = d.jurnal_id
                           WHERE d.kode_akun IN ('1.1.01','1.1.02') AND j.tanggal <= ?""", (tgl,)).fetchone()[0]


def _kelas(kode):
    if kode.startswith("3."):
        return "pendanaan", "Setoran modal dan ekuitas"
    if kode.startswith("1.3."):
        return "investasi", "Aset tetap"
    if kode == "1.2.01":
        return "operasional", "Penyaluran dan pengembalian kredit"
    if kode in ("2.1.01", "2.1.02"):
        return "operasional", "Kenaikan (penurunan) dana pihak ketiga"
    if kode.startswith("4."):
        return "operasional", "Penerimaan pendapatan"
    if kode.startswith("5."):
        return "operasional", "Pembayaran beban"
    return "operasional", "Penerimaan (pembayaran) lainnya"


def _alokasi(total, bobot):
    jumlah = sum(bobot)
    if jumlah == 0:
        return None
    hasil, sisa = [], total
    for i, b in enumerate(bobot):
        a = sisa if i == len(bobot) - 1 else int(round(total * b / jumlah))
        hasil.append(a)
        sisa -= a
    return hasil


def arus_kas(conn, dari, sampai):
    """Metode langsung: arus kas diturunkan dari jurnal yang menyentuh Kas dan Giro pada BI."""
    awal = _kas_sampai(conn, (date.fromisoformat(dari) - timedelta(days=1)).isoformat())
    kelompok = {"operasional": {}, "investasi": {}, "pendanaan": {}}
    for j in conn.execute("SELECT id FROM jurnal WHERE tanggal BETWEEN ? AND ? ORDER BY id", (dari, sampai)).fetchall():
        det = conn.execute("SELECT kode_akun, debit, kredit FROM jurnal_detail WHERE jurnal_id=?", (j["id"],)).fetchall()
        kas = sum(d["debit"] - d["kredit"] for d in det if d["kode_akun"] in KAS)
        if kas == 0:
            continue
        lawan = [(d["kode_akun"], d["debit"] - d["kredit"]) for d in det if d["kode_akun"] not in KAS]
        bobot = [max(-n, 0) if kas > 0 else max(n, 0) for _, n in lawan]
        bagi = _alokasi(kas, bobot)
        pasang = [(_kelas(k[0]), a) for k, a in zip(lawan, bagi)] if bagi else [(("operasional", "Lainnya"), kas)]
        for (bagian, label), a in pasang:
            kelompok[bagian][label] = kelompok[bagian].get(label, 0) + a
    hasil = {k: sorted(v.items()) for k, v in kelompok.items()}
    tot = {k: sum(a for _, a in v) for k, v in hasil.items()}
    kenaikan = sum(tot.values())
    akhir = _kas_sampai(conn, sampai)
    return {"awal": awal, **{k: hasil[k] for k in hasil}, **{f"total_{k}": tot[k] for k in tot},
            "kenaikan": kenaikan, "akhir": awal + kenaikan, "akhir_buku": akhir, "cocok": awal + kenaikan == akhir}


# ---------- perubahan ekuitas ----------
def perubahan_ekuitas(conn, dari, sampai):
    sebelum = (date.fromisoformat(dari) - timedelta(days=1)).isoformat()
    awal = posisi_keuangan(conn, sebelum)["total_ekuitas"]
    akhir = posisi_keuangan(conn, sampai)["total_ekuitas"]
    modal = lambda tgl: {k: v for k, _, _, v in _saldo_per_akun(conn, None, tgl)}.get("3.1.01", 0)
    tambahan = modal(sampai) - modal(sebelum)
    laba = laba_rugi(conn, dari, sampai)["laba"]
    return {"awal": awal, "tambahan_modal": tambahan, "laba": laba,
            "lainnya": akhir - awal - tambahan - laba, "akhir": akhir}


# ---------- jurnal penutup tahunan ----------
def jurnal_penutup(conn, tahun, user_id=None):
    """Memindahkan saldo pendapatan dan beban setahun ke 3.2.01 Laba ditahan (dicatat 31 Desember)."""
    _siap(conn)
    if conn.execute("SELECT 1 FROM penutupan_tahun WHERE tahun=?", (tahun,)).fetchone():
        raise ValueError(f"Tahun {tahun} sudah ditutup")
    data = _saldo_per_akun(conn, f"{tahun}-01-01", f"{tahun}-12-31", termasuk_penutup=False)
    baris, laba = [], 0
    for kode, _, kel, v in data:
        if v == 0 or kel not in ("pendapatan", "beban"):
            continue
        if kel == "pendapatan":
            baris.append((kode, v, 0) if v > 0 else (kode, 0, -v)); laba += v
        else:
            baris.append((kode, 0, v) if v > 0 else (kode, -v, 0)); laba -= v
    if not baris:
        raise ValueError("Tidak ada saldo pendapatan atau beban untuk ditutup")
    if laba:
        baris.append(("3.2.01", 0, laba) if laba > 0 else ("3.2.01", -laba, 0))
    try:
        no = buat_jurnal(conn, f"{tahun}-12-31", f"Jurnal penutup tahun {tahun}", baris, user_id)
        jp = "JP-" + no[3:]
        conn.execute("UPDATE jurnal SET no_jurnal=? WHERE no_jurnal=?", (jp, no))
        conn.execute("INSERT INTO penutupan_tahun(tahun, no_jurnal, laba) VALUES (?,?,?)", (tahun, jp, laba))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"no_jurnal": jp, "laba": laba}
