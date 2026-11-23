"""Layanan nasabah (Customer Service) BNN: pendaftaran, ubah data, status rekening, ringkasan nasabah.

CS tidak memegang uang: pembukaan rekening dilakukan dengan saldo nol, setoran awal dilayani teller.
Semua tindakan CS dicatat di log aktivitas.
"""
import re
from datetime import date, timedelta

from auth import _siap as siap_auth
from auth import catat
from deposito import _siap as siap_deposito
from kredit import _siap as siap_kredit
from transaksi import buat_nasabah, buka_rekening

STATUS = ("aktif", "diblokir", "tutup")
AKSI_CS = ("daftar nasabah", "buka rekening", "ubah data nasabah", "ubah status rekening")


def _cek_nik(nik):
    if not re.fullmatch(r"\d{16}", nik):
        raise ValueError("NIK harus 16 digit angka")


def daftarkan_nasabah(conn, nama, nik, alamat, user):
    nama, nik, alamat = nama.strip(), nik.strip(), alamat.strip()
    if not nama:
        raise ValueError("Nama wajib diisi")
    _cek_nik(nik)
    if not alamat:
        raise ValueError("Alamat wajib diisi")
    if conn.execute("SELECT 1 FROM nasabah WHERE nik=?", (nik,)).fetchone():
        raise ValueError("NIK sudah terdaftar")
    cif = buat_nasabah(conn, nama, nik, alamat)
    catat(conn, user, "daftar nasabah", f"{cif} {nama}")
    return cif


def buka_rekening_baru(conn, cif, user):
    no = buka_rekening(conn, cif, 0, None, user["id"])
    catat(conn, user, "buka rekening", f"{no} untuk {cif}")
    return no


def cari_nasabah(conn, q):
    k = f"%{q.strip()}%"
    return conn.execute(
        """SELECT n.*, (SELECT COUNT(*) FROM rekening r WHERE r.cif = n.cif) AS jumlah_rekening
           FROM nasabah n WHERE n.cif LIKE ? OR n.nama LIKE ? OR n.nik LIKE ?
              OR n.cif IN (SELECT cif FROM rekening WHERE no_rek LIKE ?)
           ORDER BY n.cif LIMIT 50""", (k, k, k, k)).fetchall()


def ubah_nasabah(conn, cif, nama, nik, alamat, user):
    if not conn.execute("SELECT 1 FROM nasabah WHERE cif=?", (cif,)).fetchone():
        raise ValueError(f"Nasabah {cif} tidak ditemukan")
    nama, nik, alamat = nama.strip(), nik.strip(), alamat.strip()
    if not nama or not alamat:
        raise ValueError("Nama dan alamat wajib diisi")
    _cek_nik(nik)
    if conn.execute("SELECT 1 FROM nasabah WHERE nik=? AND cif<>?", (nik, cif)).fetchone():
        raise ValueError("NIK sudah dipakai nasabah lain")
    conn.execute("UPDATE nasabah SET nama=?, nik=?, alamat=? WHERE cif=?", (nama, nik, alamat, cif))
    conn.commit()
    catat(conn, user, "ubah data nasabah", f"{cif} {nama}")


def ubah_status_rekening(conn, no_rek, status_baru, alasan, user):
    rek = conn.execute("SELECT * FROM rekening WHERE no_rek=?", (no_rek,)).fetchone()
    if not rek:
        raise ValueError(f"Rekening {no_rek} tidak ditemukan")
    if rek["status"] == "tutup":
        raise ValueError("Rekening sudah ditutup dan tidak dapat diubah")
    if status_baru not in STATUS:
        raise ValueError("Status tidak valid")
    if status_baru == rek["status"]:
        raise ValueError("Status tidak berubah")
    if not alasan.strip():
        raise ValueError("Alasan wajib diisi")
    if status_baru == "tutup":
        siap_kredit(conn)
        siap_deposito(conn)
        if rek["saldo"] != 0:
            raise ValueError("Rekening hanya bisa ditutup bila saldo nol")
        if conn.execute("SELECT 1 FROM kredit WHERE no_rek=? AND status='aktif'", (no_rek,)).fetchone():
            raise ValueError("Rekening masih terkait kredit yang aktif")
        if conn.execute("SELECT 1 FROM deposito WHERE no_rek=? AND status='aktif'", (no_rek,)).fetchone():
            raise ValueError("Rekening masih terkait deposito yang aktif")
    conn.execute("UPDATE rekening SET status=? WHERE no_rek=?", (status_baru, no_rek))
    conn.commit()
    catat(conn, user, "ubah status rekening", f"{no_rek}: {rek['status']} menjadi {status_baru}. Alasan: {alasan.strip()}")


def ringkasan_cs(conn):
    def n(sql, par=()):
        return conn.execute(sql, par).fetchone()[0]
    batas = (date.today() - timedelta(days=30)).isoformat()
    return {"nasabah": n("SELECT COUNT(*) FROM nasabah"),
            "aktif": n("SELECT COUNT(*) FROM rekening WHERE status='aktif'"),
            "diblokir": n("SELECT COUNT(*) FROM rekening WHERE status='diblokir'"),
            "tutup": n("SELECT COUNT(*) FROM rekening WHERE status='tutup'"),
            "baru_30_hari": n("SELECT COUNT(*) FROM nasabah WHERE tgl_daftar >= ?", (batas,))}


def ringkas_nasabah(conn, cif):
    """Rekening, kredit, dan deposito milik satu nasabah (hanya baca)."""
    siap_kredit(conn)
    siap_deposito(conn)
    rekening = conn.execute("SELECT no_rek, jenis, saldo, status FROM rekening WHERE cif=? ORDER BY no_rek", (cif,)).fetchall()
    kredit = conn.execute(
        """SELECT k.no_kredit, k.plafon, k.status,
                  (SELECT COALESCE(SUM(a.pokok),0) FROM angsuran a WHERE a.kredit_id = k.id AND a.status='belum') AS sisa
           FROM kredit k JOIN rekening r ON r.no_rek = k.no_rek WHERE r.cif=? ORDER BY k.id""", (cif,)).fetchall()
    deposito = conn.execute(
        """SELECT d.no_bilyet, d.nominal, d.jatuh_tempo, d.status FROM deposito d
           JOIN rekening r ON r.no_rek = d.no_rek WHERE r.cif=? ORDER BY d.id""", (cif,)).fetchall()
    return {"rekening": rekening, "kredit": kredit, "deposito": deposito}


def riwayat_layanan(conn, batas=20):
    siap_auth(conn)
    return conn.execute(
        f"SELECT waktu, username, aksi, keterangan FROM log_aktivitas WHERE aksi IN ({','.join('?' * len(AKSI_CS))}) "
        "ORDER BY id DESC LIMIT ?", AKSI_CS + (batas,)).fetchall()
