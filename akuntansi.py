"""Mesin akuntansi BNN: jurnal, buku besar, neraca saldo.

Aturan utama: setiap transaksi harus lewat buat_jurnal(), yang menolak
jurnal tidak seimbang, akun tidak dikenal, dan periode yang sudah ditutup.
Nominal disimpan sebagai bilangan bulat rupiah.
"""
from database import get_conn


def periode_ditutup(conn, tanggal):
    """tanggal format 'YYYY-MM-DD'."""
    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    row = conn.execute(
        "SELECT status FROM periode WHERE tahun=? AND bulan=?", (tahun, bulan)
    ).fetchone()
    return bool(row and row["status"] == "ditutup")


def buat_jurnal(conn, tanggal, keterangan, baris, user_id=None):
    """baris = [(kode_akun, debit, kredit), ...]. Mengembalikan no_jurnal."""
    if not baris or len(baris) < 2:
        raise ValueError("Jurnal minimal terdiri dari dua baris")

    total_d = total_k = 0
    for kode, d, k in baris:
        if d < 0 or k < 0:
            raise ValueError("Nominal tidak boleh negatif")
        if (d > 0) == (k > 0):
            raise ValueError(f"Akun {kode}: isi salah satu saja, debit atau kredit")
        ada = conn.execute("SELECT 1 FROM akun WHERE kode=?", (kode,)).fetchone()
        if not ada:
            raise ValueError(f"Akun {kode} tidak ada di bagan akun")
        total_d += d
        total_k += k

    if total_d != total_k:
        raise ValueError(f"Jurnal tidak seimbang (debit {total_d:,} vs kredit {total_k:,})")
    if periode_ditutup(conn, tanggal):
        raise ValueError("Periode sudah ditutup")

    try:
        cur = conn.execute(
            "INSERT INTO jurnal(tanggal, keterangan, user_id) VALUES (?,?,?)",
            (tanggal, keterangan, user_id),
        )
        jid = cur.lastrowid
        no_jurnal = f"JU-{jid:04d}"
        conn.execute("UPDATE jurnal SET no_jurnal=? WHERE id=?", (no_jurnal, jid))
        for kode, d, k in baris:
            conn.execute(
                "INSERT INTO jurnal_detail(jurnal_id, kode_akun, debit, kredit) VALUES (?,?,?,?)",
                (jid, kode, d, k),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return no_jurnal


def buku_besar(conn, kode, dari=None, sampai=None):
    """Daftar mutasi satu akun beserta saldo berjalan."""
    akun = conn.execute("SELECT * FROM akun WHERE kode=?", (kode,)).fetchone()
    if not akun:
        raise ValueError(f"Akun {kode} tidak ada")
    sql = """SELECT j.tanggal, j.no_jurnal, j.keterangan, d.debit, d.kredit
             FROM jurnal_detail d JOIN jurnal j ON j.id = d.jurnal_id
             WHERE d.kode_akun = ?"""
    par = [kode]
    if dari:
        sql += " AND j.tanggal >= ?"; par.append(dari)
    if sampai:
        sql += " AND j.tanggal <= ?"; par.append(sampai)
    sql += " ORDER BY j.tanggal, j.id"

    hasil, saldo = [], 0
    for r in conn.execute(sql, par):
        mutasi = r["debit"] - r["kredit"]
        saldo += mutasi if akun["saldo_normal"] == "D" else -mutasi
        hasil.append({**dict(r), "saldo": saldo})
    return hasil


def neraca_saldo(conn, sampai=None):
    """Mengembalikan (baris, total_debit, total_kredit)."""
    sql = """SELECT a.kode, a.nama,
                    COALESCE(SUM(x.debit),0) AS d, COALESCE(SUM(x.kredit),0) AS k
             FROM akun a LEFT JOIN (
                 SELECT d.kode_akun, d.debit, d.kredit FROM jurnal_detail d
                 JOIN jurnal j ON j.id = d.jurnal_id WHERE 1=1"""
    par = []
    if sampai:
        sql += " AND j.tanggal <= ?"; par.append(sampai)
    sql += """) x ON x.kode_akun = a.kode GROUP BY a.kode, a.nama ORDER BY a.kode"""

    baris, td, tk = [], 0, 0
    for r in conn.execute(sql, par):
        net = r["d"] - r["k"]
        if net == 0:
            continue
        deb, kre = (net, 0) if net > 0 else (0, -net)
        baris.append((r["kode"], r["nama"], deb, kre))
        td += deb
        tk += kre
    return baris, td, tk


def rupiah(n):
    return ("-" if n < 0 else "") + "Rp" + f"{abs(n):,}".replace(",", ".")
