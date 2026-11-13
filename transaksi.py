"""Modul transaksi teller BNN: nasabah, rekening tabungan, setor, tarik, transfer.

Setiap transaksi memperbarui saldo rekening DAN membuat jurnal dalam satu
transaksi database: kalau salah satu gagal, semuanya dibatalkan.
Saat ini jenis rekening yang didukung: tabungan (akun 2.1.01).
"""
from datetime import date

from akuntansi import buat_jurnal

AKUN_KAS = "1.1.01"
AKUN_TABUNGAN = "2.1.01"


def _hari_ini():
    return date.today().isoformat()


def _cek_jumlah(jumlah):
    if not isinstance(jumlah, int) or jumlah <= 0:
        raise ValueError("Jumlah harus bilangan bulat rupiah lebih dari 0")


def _ambil_rek(conn, no_rek):
    rek = conn.execute("SELECT * FROM rekening WHERE no_rek=?", (no_rek,)).fetchone()
    if not rek:
        raise ValueError(f"Rekening {no_rek} tidak ditemukan")
    if rek["status"] != "aktif":
        raise ValueError(f"Rekening {no_rek} tidak aktif")
    if rek["jenis"] != "tabungan":
        raise ValueError("Saat ini hanya rekening tabungan yang didukung")
    return rek


def buat_nasabah(conn, nama, nik="", alamat="", tanggal=None):
    if not nama.strip():
        raise ValueError("Nama nasabah wajib diisi")
    n = conn.execute("SELECT COUNT(*) FROM nasabah").fetchone()[0] + 1
    cif = f"CIF-{n:05d}"
    conn.execute(
        "INSERT INTO nasabah(cif, nama, nik, alamat, tgl_daftar) VALUES (?,?,?,?,?)",
        (cif, nama.strip(), nik, alamat, tanggal or _hari_ini()),
    )
    conn.commit()
    return cif


def buka_rekening(conn, cif, setoran_awal=0, tanggal=None, user_id=None):
    if not conn.execute("SELECT 1 FROM nasabah WHERE cif=?", (cif,)).fetchone():
        raise ValueError(f"Nasabah {cif} tidak ditemukan")
    try:
        n = conn.execute("SELECT COUNT(*) FROM rekening").fetchone()[0] + 1
        no_rek = str(1_000_000_000 + n)
        conn.execute(
            "INSERT INTO rekening(no_rek, cif, jenis, saldo) VALUES (?,?, 'tabungan', 0)",
            (no_rek, cif),
        )
        if setoran_awal > 0:
            setor_tunai(conn, no_rek, setoran_awal, tanggal, user_id, "Setoran awal")
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return no_rek


def setor_tunai(conn, no_rek, jumlah, tanggal=None, user_id=None, ket="Setor tunai"):
    """Debit Kas, Kredit Tabungan."""
    _cek_jumlah(jumlah)
    try:
        _ambil_rek(conn, no_rek)
        conn.execute("UPDATE rekening SET saldo = saldo + ? WHERE no_rek=?", (jumlah, no_rek))
        return buat_jurnal(
            conn, tanggal or _hari_ini(), f"{ket} rek {no_rek}",
            [(AKUN_KAS, jumlah, 0), (AKUN_TABUNGAN, 0, jumlah)], user_id,
        )
    except Exception:
        conn.rollback()
        raise


def tarik_tunai(conn, no_rek, jumlah, tanggal=None, user_id=None):
    """Debit Tabungan, Kredit Kas."""
    _cek_jumlah(jumlah)
    try:
        rek = _ambil_rek(conn, no_rek)
        if rek["saldo"] < jumlah:
            raise ValueError(f"Saldo tidak cukup (saldo {rek['saldo']:,}, tarik {jumlah:,})")
        conn.execute("UPDATE rekening SET saldo = saldo - ? WHERE no_rek=?", (jumlah, no_rek))
        return buat_jurnal(
            conn, tanggal or _hari_ini(), f"Tarik tunai rek {no_rek}",
            [(AKUN_TABUNGAN, jumlah, 0), (AKUN_KAS, 0, jumlah)], user_id,
        )
    except Exception:
        conn.rollback()
        raise


def transfer(conn, rek_asal, rek_tujuan, jumlah, tanggal=None, user_id=None):
    """Antar rekening tabungan BNN. Akun buku besar sama, jadi tidak mengubah total 2.1.01."""
    _cek_jumlah(jumlah)
    if rek_asal == rek_tujuan:
        raise ValueError("Rekening asal dan tujuan tidak boleh sama")
    try:
        asal = _ambil_rek(conn, rek_asal)
        _ambil_rek(conn, rek_tujuan)
        if asal["saldo"] < jumlah:
            raise ValueError(f"Saldo tidak cukup (saldo {asal['saldo']:,}, transfer {jumlah:,})")
        conn.execute("UPDATE rekening SET saldo = saldo - ? WHERE no_rek=?", (jumlah, rek_asal))
        conn.execute("UPDATE rekening SET saldo = saldo + ? WHERE no_rek=?", (jumlah, rek_tujuan))
        return buat_jurnal(
            conn, tanggal or _hari_ini(), f"Transfer {rek_asal} ke {rek_tujuan}",
            [(AKUN_TABUNGAN, jumlah, 0), (AKUN_TABUNGAN, 0, jumlah)], user_id,
        )
    except Exception:
        conn.rollback()
        raise


def rekonsiliasi_tabungan(conn):
    """Kontrol: total saldo rekening tabungan harus sama dengan saldo buku besar 2.1.01."""
    sub = conn.execute(
        "SELECT COALESCE(SUM(saldo),0) FROM rekening WHERE jenis='tabungan'"
    ).fetchone()[0]
    gl = conn.execute(
        "SELECT COALESCE(SUM(kredit - debit),0) FROM jurnal_detail WHERE kode_akun=?",
        (AKUN_TABUNGAN,),
    ).fetchone()[0]
    return sub, gl, sub == gl
