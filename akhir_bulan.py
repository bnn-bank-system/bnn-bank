"""Proses akhir bulan BNN: bunga tabungan, pajak bunga, biaya administrasi,
tutup buku (kunci periode), dan jurnal pembalik.

PARAMETER DI BAWAH ADALAH ASUMSI untuk tugas. Cocokkan dengan materi kuliah / ketentuan yang berlaku
(terutama tarif dan ambang pajak bunga) sebelum dikumpulkan.

Penyederhanaan: bunga tabungan dihitung dari saldo pada saat proses dijalankan (bukan saldo harian
rata-rata). Proses dijalankan satu kali per rekening per bulan.
"""
import calendar
import math
from datetime import date

from akuntansi import buat_jurnal, neraca_saldo
from transaksi import rekonsiliasi_tabungan

TARIF_BUNGA = 0.025        # bunga tabungan per tahun
SALDO_MIN_BUNGA = 1_000_000  # saldo minimum agar mendapat bunga
TARIF_PAJAK = 0.20         # pajak final atas bunga
AMBANG_PAJAK = 7_500_000   # saldo sampai nilai ini tidak dikenai pajak bunga
BIAYA_ADMIN = 5_000        # biaya administrasi bulanan per rekening

AKUN_BARU = [
    ("2.3.01", "Utang pajak", "liabilitas", "K"),
    ("4.2.01", "Pendapatan administrasi", "pendapatan", "K"),
]
# Akun yang saldonya dikendalikan buku pembantu: tidak boleh dibalik dengan jurnal manual
AKUN_TERKENDALI = {"2.1.01", "1.2.01", "1.2.02"}


def _bulat(x):
    return int(math.floor(x + 0.5))


def _siap(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS proses_bulanan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, periode TEXT NOT NULL, no_rek TEXT NOT NULL,
        saldo INTEGER NOT NULL, bunga INTEGER NOT NULL, pajak INTEGER NOT NULL, admin INTEGER NOT NULL,
        no_jurnal TEXT, UNIQUE (periode, no_rek))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pembalikan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, no_jurnal_asal TEXT UNIQUE NOT NULL,
        no_jurnal_balik TEXT NOT NULL, alasan TEXT NOT NULL, tanggal TEXT NOT NULL, user_id INTEGER)""")
    conn.executemany("INSERT OR IGNORE INTO akun(kode, nama, kelompok, saldo_normal) VALUES (?,?,?,?)",
                     AKUN_BARU)
    conn.commit()


# ---------- bunga, pajak, administrasi ----------
def proses_bulanan(conn, periode, tanggal, user_id=None):
    """periode 'YYYY-MM'. Mengembalikan ringkasan, atau None bila semua rekening sudah diproses."""
    _siap(conn)
    if not tanggal.startswith(periode):
        raise ValueError("Tanggal proses harus berada di dalam periode")
    try:
        rows = conn.execute(
            """SELECT * FROM rekening WHERE jenis='tabungan' AND status='aktif' AND no_rek NOT IN
               (SELECT no_rek FROM proses_bulanan WHERE periode=?) ORDER BY no_rek""", (periode,)).fetchall()
        if not rows:
            return None
        tb = tp = ta = 0
        for r in rows:
            saldo = r["saldo"]
            bunga = _bulat(saldo * TARIF_BUNGA / 12) if saldo >= SALDO_MIN_BUNGA else 0
            pajak = _bulat(bunga * TARIF_PAJAK) if saldo > AMBANG_PAJAK else 0
            admin = BIAYA_ADMIN if saldo + bunga - pajak >= BIAYA_ADMIN else 0
            conn.execute("UPDATE rekening SET saldo = saldo + ? WHERE no_rek=?",
                         (bunga - pajak - admin, r["no_rek"]))
            conn.execute("INSERT INTO proses_bulanan(periode, no_rek, saldo, bunga, pajak, admin) "
                         "VALUES (?,?,?,?,?,?)", (periode, r["no_rek"], saldo, bunga, pajak, admin))
            tb += bunga; tp += pajak; ta += admin

        baris = []
        if tb:
            baris += [("5.1.01", tb, 0), ("2.1.01", 0, tb)]
        if tp:
            baris += [("2.1.01", tp, 0), ("2.3.01", 0, tp)]
        if ta:
            baris += [("2.1.01", ta, 0), ("4.2.01", 0, ta)]
        no = None
        if baris:
            no = buat_jurnal(conn, tanggal, f"Bunga, pajak, dan administrasi tabungan {periode}", baris, user_id)
            conn.execute("UPDATE proses_bulanan SET no_jurnal=? WHERE periode=?", (no, periode))
        conn.commit()
        return {"rekening": len(rows), "bunga": tb, "pajak": tp, "admin": ta, "no_jurnal": no}
    except Exception:
        conn.rollback()
        raise


# ---------- tutup buku ----------
def _akhir_bulan(bulan, tahun):
    return date(tahun, bulan, calendar.monthrange(tahun, bulan)[1]).isoformat()


def status_periode(conn):
    """Daftar periode yang punya jurnal beserta statusnya."""
    _siap(conn)
    hasil = []
    for r in conn.execute("SELECT strftime('%Y-%m', tanggal) AS ym, COUNT(*) AS n FROM jurnal "
                          "GROUP BY ym ORDER BY ym").fetchall():
        th, bl = int(r["ym"][:4]), int(r["ym"][5:])
        p = conn.execute("SELECT status FROM periode WHERE tahun=? AND bulan=?", (th, bl)).fetchone()
        hasil.append({"periode": r["ym"], "bulan": bl, "tahun": th, "jurnal": r["n"],
                      "status": p["status"] if p else "terbuka"})
    return hasil


def tutup_buku(conn, bulan, tahun, user_id=None):
    """Mengunci periode setelah kontrol lolos. Jurnal baru pada periode terkunci akan ditolak."""
    _siap(conn)
    p = conn.execute("SELECT status FROM periode WHERE tahun=? AND bulan=?", (tahun, bulan)).fetchone()
    if p and p["status"] == "ditutup":
        raise ValueError(f"Periode {bulan:02d}/{tahun} sudah ditutup")
    awal = date(tahun, bulan, 1).isoformat()
    for s in status_periode(conn):
        if f"{s['tahun']}-{s['bulan']:02d}" < awal[:7] and s["status"] != "ditutup":
            raise ValueError(f"Tutup buku periode {s['bulan']:02d}/{s['tahun']} terlebih dulu")
    _, td, tk = neraca_saldo(conn, _akhir_bulan(bulan, tahun))
    if td != tk:
        raise ValueError(f"Neraca saldo tidak seimbang (debit {td:,}, kredit {tk:,})")
    sub, gl, ok = rekonsiliasi_tabungan(conn)
    if not ok:
        raise ValueError(f"Rekonsiliasi tabungan tidak sesuai (rekening {sub:,}, buku besar {gl:,})")
    conn.execute("""INSERT INTO periode(bulan, tahun, status) VALUES (?,?, 'ditutup')
                    ON CONFLICT(bulan, tahun) DO UPDATE SET status='ditutup'""", (bulan, tahun))
    conn.commit()
    return {"periode": f"{bulan:02d}/{tahun}", "total_debit": td, "total_kredit": tk}


def buka_kembali(conn, bulan, tahun):
    """Membuka periode yang terkunci. Hanya boleh bila tidak ada periode sesudahnya yang sudah ditutup."""
    _siap(conn)
    lebih_baru = conn.execute("SELECT 1 FROM periode WHERE status='ditutup' AND (tahun*100+bulan) > ?",
                              (tahun * 100 + bulan,)).fetchone()
    if lebih_baru:
        raise ValueError("Buka kembali periode yang lebih baru terlebih dulu")
    conn.execute("UPDATE periode SET status='terbuka' WHERE tahun=? AND bulan=?", (tahun, bulan))
    conn.commit()


# ---------- jurnal pembalik ----------
def balik_jurnal(conn, no_jurnal, alasan, tanggal=None, user_id=None):
    """Mengoreksi jurnal dengan jurnal lawan (jurnal tidak pernah dihapus)."""
    _siap(conn)
    tanggal = tanggal or date.today().isoformat()
    if not alasan.strip():
        raise ValueError("Alasan pembalikan wajib diisi")
    j = conn.execute("SELECT * FROM jurnal WHERE no_jurnal=?", (no_jurnal,)).fetchone()
    if not j:
        raise ValueError(f"Jurnal {no_jurnal} tidak ditemukan")
    if conn.execute("SELECT 1 FROM pembalikan WHERE no_jurnal_asal=?", (no_jurnal,)).fetchone():
        raise ValueError(f"Jurnal {no_jurnal} sudah pernah dibalik")
    if conn.execute("SELECT 1 FROM pembalikan WHERE no_jurnal_balik=?", (no_jurnal,)).fetchone():
        raise ValueError("Jurnal pembalik tidak boleh dibalik lagi")
    det = conn.execute("SELECT kode_akun, debit, kredit FROM jurnal_detail WHERE jurnal_id=? ORDER BY id",
                       (j["id"],)).fetchall()
    terkendali = sorted({d["kode_akun"] for d in det} & AKUN_TERKENDALI)
    if terkendali:
        raise ValueError("Jurnal memakai akun yang dikendalikan buku pembantu (" + ", ".join(terkendali) +
                         "), tidak bisa dibalik dengan jurnal manual")
    try:
        no = buat_jurnal(conn, tanggal, f"Pembalik {no_jurnal}: {alasan.strip()}",
                         [(d["kode_akun"], d["kredit"], d["debit"]) for d in det], user_id)
        conn.execute("INSERT INTO pembalikan(no_jurnal_asal, no_jurnal_balik, alasan, tanggal, user_id) "
                     "VALUES (?,?,?,?,?)", (no_jurnal, no, alasan.strip(), tanggal, user_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return no
