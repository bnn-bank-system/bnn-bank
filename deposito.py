"""Modul deposito BNN: penempatan, bunga akrual, jatuh tempo, perpanjangan otomatis (ARO).

Jurnal:
  Penempatan : D 2.1.01 Tabungan                 K 2.1.02 Deposito
  Akrual     : D 5.1.01 Beban bunga              K 2.2.01 Bunga yang masih harus dibayar
  Jatuh tempo: D 2.1.02 Deposito (bila dicairkan) D 2.2.01 bunga terakrual  D 5.1.01 sisa bunga
               K 2.3.01 Utang pajak               K 2.1.01 Tabungan (pokok + bunga - pajak)
  ARO        : bunga dibayar ke tabungan, pokok diperpanjang untuk satu periode lagi.

Tarif pajak dan ambang diambil dari akhir_bulan.py. Pencairan sebelum jatuh tempo belum didukung.
"""
import math
from datetime import date

from akhir_bulan import AMBANG_PAJAK, TARIF_PAJAK
from akuntansi import buat_jurnal
from kredit import tambah_bulan
from transaksi import _ambil_rek

MIN_NOMINAL = 1_000_000


def _siap(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS deposito (
        id INTEGER PRIMARY KEY AUTOINCREMENT, no_bilyet TEXT UNIQUE NOT NULL,
        no_rek TEXT NOT NULL REFERENCES rekening(no_rek), nominal INTEGER NOT NULL,
        bunga_tahunan REAL NOT NULL, tenor INTEGER NOT NULL, tgl_mulai TEXT NOT NULL,
        jatuh_tempo TEXT NOT NULL, aro INTEGER NOT NULL DEFAULT 0, bunga_diakui INTEGER NOT NULL DEFAULT 0,
        perpanjangan INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'aktif')""")
    conn.executemany("INSERT OR IGNORE INTO akun(kode, nama, kelompok, saldo_normal) VALUES (?,?,?,?)",
                     [("2.2.01", "Bunga yang masih harus dibayar", "liabilitas", "K"),
                      ("2.3.01", "Utang pajak", "liabilitas", "K")])
    conn.commit()


def _bulat(x):
    return int(math.floor(x + 0.5))


def _bunga_periode(d):
    return _bulat(d["nominal"] * d["bunga_tahunan"] / 100 * d["tenor"] / 12)


def _pajak(nominal, bunga):
    return _bulat(bunga * TARIF_PAJAK) if nominal > AMBANG_PAJAK else 0


def tempatkan_deposito(conn, no_rek, nominal, bunga_tahunan, tenor, aro=False, tanggal=None, user_id=None):
    _siap(conn)
    if not isinstance(nominal, int) or nominal < MIN_NOMINAL:
        raise ValueError(f"Nominal minimal Rp{MIN_NOMINAL:,}".replace(",", "."))
    if tenor not in (1, 3, 6, 12, 24):
        raise ValueError("Tenor deposito: 1, 3, 6, 12, atau 24 bulan")
    if bunga_tahunan <= 0:
        raise ValueError("Suku bunga harus lebih dari 0")
    tgl = date.fromisoformat(tanggal) if tanggal else date.today()
    try:
        rek = _ambil_rek(conn, no_rek)
        if rek["saldo"] < nominal:
            raise ValueError(f"Saldo tidak cukup (saldo {rek['saldo']:,}, nominal {nominal:,})")
        no = f"DEP-{conn.execute('SELECT COUNT(*) FROM deposito').fetchone()[0] + 1:04d}"
        conn.execute("""INSERT INTO deposito(no_bilyet, no_rek, nominal, bunga_tahunan, tenor, tgl_mulai,
                        jatuh_tempo, aro) VALUES (?,?,?,?,?,?,?,?)""",
                     (no, no_rek, nominal, bunga_tahunan, tenor, tgl.isoformat(),
                      tambah_bulan(tgl, tenor).isoformat(), 1 if aro else 0))
        conn.execute("UPDATE rekening SET saldo = saldo - ? WHERE no_rek=?", (nominal, no_rek))
        buat_jurnal(conn, tgl.isoformat(), f"Penempatan deposito {no} dari rek {no_rek}",
                    [("2.1.01", nominal, 0), ("2.1.02", 0, nominal)], user_id)
    except Exception:
        conn.rollback()
        raise
    return no


def akrual_deposito(conn, tanggal, user_id=None):
    """Mengakui beban bunga deposito yang sudah berjalan sampai tanggal. Mengembalikan (jumlah, no_jurnal)."""
    _siap(conn)
    t = date.fromisoformat(tanggal)
    total = 0
    try:
        for d in conn.execute("SELECT * FROM deposito WHERE status='aktif' AND tgl_mulai < ?", (tanggal,)).fetchall():
            awal, akhir = date.fromisoformat(d["tgl_mulai"]), date.fromisoformat(d["jatuh_tempo"])
            hari = (akhir - awal).days
            target = _bulat(_bunga_periode(d) * min((t - awal).days, hari) / hari)
            delta = target - d["bunga_diakui"]
            if delta > 0:
                conn.execute("UPDATE deposito SET bunga_diakui = bunga_diakui + ? WHERE id=?", (delta, d["id"]))
                total += delta
        if total == 0:
            conn.rollback()
            return 0, None
        no = buat_jurnal(conn, tanggal, f"Akrual beban bunga deposito s.d. {tanggal}",
                         [("5.1.01", total, 0), ("2.2.01", 0, total)], user_id)
        return total, no
    except Exception:
        conn.rollback()
        raise


def proses_jatuh_tempo(conn, tanggal, user_id=None):
    """Mencairkan deposito yang jatuh tempo, atau memperpanjangnya bila ARO. Mengembalikan daftar hasil."""
    _siap(conn)
    hasil = []
    while True:
        d = conn.execute("SELECT * FROM deposito WHERE status='aktif' AND jatuh_tempo <= ? ORDER BY jatuh_tempo, id LIMIT 1",
                         (tanggal,)).fetchone()
        if not d:
            return hasil
        bunga = _bunga_periode(d)
        pajak = _pajak(d["nominal"], bunga)
        diakui, sisa = d["bunga_diakui"], bunga - d["bunga_diakui"]
        net = bunga - pajak
        baris = []
        if d["aro"]:
            tujuan_saldo = net
        else:
            baris.append(("2.1.02", d["nominal"], 0))
            tujuan_saldo = d["nominal"] + net
        if diakui > 0:
            baris.append(("2.2.01", diakui, 0))
        if sisa > 0:
            baris.append(("5.1.01", sisa, 0))
        if pajak > 0:
            baris.append(("2.3.01", 0, pajak))
        baris.append(("2.1.01", 0, tujuan_saldo))
        try:
            conn.execute("UPDATE rekening SET saldo = saldo + ? WHERE no_rek=?", (tujuan_saldo, d["no_rek"]))
            if d["aro"]:
                baru = tambah_bulan(date.fromisoformat(d["jatuh_tempo"]), d["tenor"]).isoformat()
                conn.execute("""UPDATE deposito SET tgl_mulai=?, jatuh_tempo=?, bunga_diakui=0,
                                perpanjangan = perpanjangan + 1 WHERE id=?""", (d["jatuh_tempo"], baru, d["id"]))
            else:
                conn.execute("UPDATE deposito SET status='cair', bunga_diakui=? WHERE id=?", (bunga, d["id"]))
            no = buat_jurnal(conn, d["jatuh_tempo"],
                             f"{'Bunga ARO' if d['aro'] else 'Pencairan'} deposito {d['no_bilyet']}", baris, user_id)
        except Exception:
            conn.rollback()
            raise
        hasil.append({"no_bilyet": d["no_bilyet"], "aksi": "diperpanjang" if d["aro"] else "dicairkan",
                      "bunga": bunga, "pajak": pajak, "no_jurnal": no})


def daftar_deposito(conn):
    _siap(conn)
    return conn.execute("""SELECT d.*, n.nama FROM deposito d JOIN rekening r ON r.no_rek = d.no_rek
                           JOIN nasabah n ON n.cif = r.cif ORDER BY d.id""").fetchall()


def rekonsiliasi_deposito(conn):
    """Total nominal deposito aktif harus sama dengan saldo buku besar 2.1.02."""
    _siap(conn)
    sub = conn.execute("SELECT COALESCE(SUM(nominal),0) FROM deposito WHERE status='aktif'").fetchone()[0]
    gl = conn.execute("SELECT COALESCE(SUM(kredit-debit),0) FROM jurnal_detail WHERE kode_akun='2.1.02'").fetchone()[0]
    return sub, gl, sub == gl
