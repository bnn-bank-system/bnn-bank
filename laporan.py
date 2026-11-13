"""Laporan keuangan BNN: posisi keuangan, laba rugi, ringkasan dashboard.

Jurnal penutup tahunan bernomor 'JP-' dikecualikan dari laporan laba rugi agar laba setahun tetap terlihat.
"""


def _saldo_per_akun(conn, dari=None, sampai=None, termasuk_penutup=True):
    """Mengembalikan daftar (kode, nama, kelompok, nilai).
    nilai = debit - kredit untuk aset dan beban; kredit - debit untuk lainnya."""
    sql = """SELECT a.kode, a.nama, a.kelompok,
                    COALESCE(SUM(x.debit),0) AS d, COALESCE(SUM(x.kredit),0) AS k
             FROM akun a LEFT JOIN (
                 SELECT d.kode_akun, d.debit, d.kredit FROM jurnal_detail d
                 JOIN jurnal j ON j.id = d.jurnal_id WHERE 1=1"""
    par = []
    if dari:
        sql += " AND j.tanggal >= ?"; par.append(dari)
    if sampai:
        sql += " AND j.tanggal <= ?"; par.append(sampai)
    if not termasuk_penutup:
        sql += " AND j.no_jurnal NOT LIKE 'JP-%'"
    sql += ") x ON x.kode_akun = a.kode GROUP BY a.kode, a.nama, a.kelompok ORDER BY a.kode"

    hasil = []
    for r in conn.execute(sql, par):
        nilai = r["d"] - r["k"] if r["kelompok"] in ("aset", "beban") else r["k"] - r["d"]
        hasil.append((r["kode"], r["nama"], r["kelompok"], nilai))
    return hasil


def laba_rugi(conn, dari=None, sampai=None, termasuk_penutup=False):
    data = _saldo_per_akun(conn, dari, sampai, termasuk_penutup)
    pendapatan = [(k, n, v) for k, n, g, v in data if g == "pendapatan" and v != 0]
    beban = [(k, n, v) for k, n, g, v in data if g == "beban" and v != 0]
    tp = sum(v for _, _, v in pendapatan)
    tb = sum(v for _, _, v in beban)
    return {"pendapatan": pendapatan, "beban": beban,
            "total_pendapatan": tp, "total_beban": tb, "laba": tp - tb}


def posisi_keuangan(conn, sampai=None):
    data = _saldo_per_akun(conn, None, sampai)
    aset = [(k, n, v) for k, n, g, v in data if g == "aset" and v != 0]
    liab = [(k, n, v) for k, n, g, v in data if g == "liabilitas" and v != 0]
    ekuitas = [(k, n, v) for k, n, g, v in data if g == "ekuitas" and v != 0]
    laba = laba_rugi(conn, None, sampai, termasuk_penutup=True)["laba"]
    ta = sum(v for _, _, v in aset)
    tl = sum(v for _, _, v in liab)
    te = sum(v for _, _, v in ekuitas) + laba
    return {"aset": aset, "liabilitas": liab, "ekuitas": ekuitas,
            "laba_berjalan": laba, "total_aset": ta, "total_liabilitas": tl,
            "total_ekuitas": te, "seimbang": ta == tl + te}


def ringkasan(conn):
    p = posisi_keuangan(conn)
    kredit_neto = sum(v for k, _, v in p["aset"] if k in ("1.2.01", "1.2.09"))
    dpk = sum(v for k, _, v in p["liabilitas"] if k.startswith("2.1."))
    return {"total_aset": p["total_aset"], "dpk": dpk,
            "kredit_neto": kredit_neto, "laba": p["laba_berjalan"]}
