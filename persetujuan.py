"""Maker-checker BNN (prinsip empat mata).

- Maker  : teller / akuntan membuat pengajuan.
- Checker: supervisor menyetujui atau menolak. Pembuat tidak boleh menyetujui pengajuannya sendiri.
- Yang diperiksa: jurnal manual (selalu) serta tarik tunai dan transfer mulai AMBANG_PERSETUJUAN.
- Transaksi supervisor dieksekusi langsung (penyederhanaan: hanya ada satu level supervisor).
- Pengajuan yang disetujui dieksekusi atas nama maker, sehingga kolom Petugas tetap menunjuk pembuatnya.
"""
import json
from datetime import date, datetime

from akuntansi import buat_jurnal, periode_ditutup
from transaksi import _ambil_rek, tarik_tunai, transfer

AMBANG_PERSETUJUAN = 10_000_000


def _siap(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS persetujuan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, jenis TEXT NOT NULL, ringkasan TEXT NOT NULL,
        payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'menunggu',
        maker_id INTEGER NOT NULL, checker_id INTEGER, dibuat TEXT NOT NULL,
        diputuskan TEXT, catatan TEXT, no_jurnal TEXT)""")
    conn.commit()


def _sekarang():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _jalankan(conn, jenis, p, maker_id):
    if jenis == "jurnal_manual":
        return buat_jurnal(conn, p["tanggal"], p["keterangan"], [tuple(b) for b in p["baris"]], maker_id)
    if jenis == "tarik_tunai":
        return tarik_tunai(conn, p["no_rek"], p["jumlah"], p["tanggal"], maker_id)
    if jenis == "transfer":
        return transfer(conn, p["no_rek"], p["tujuan"], p["jumlah"], p["tanggal"], maker_id)
    raise ValueError("Jenis pengajuan tidak dikenal")


def _simpan(conn, jenis, ringkasan, payload, user):
    cur = conn.execute("INSERT INTO persetujuan(jenis, ringkasan, payload, maker_id, dibuat) VALUES (?,?,?,?,?)",
                       (jenis, ringkasan, json.dumps(payload), user["id"], _sekarang()))
    conn.commit()
    return {"status": "menunggu", "id": cur.lastrowid}


def ajukan_jurnal_manual(conn, tanggal, keterangan, baris, user):
    """baris = [(kode_akun, debit, kredit), ...]. Mengembalikan {'status': 'langsung'|'menunggu', ...}."""
    _siap(conn)
    if not keterangan.strip():
        raise ValueError("Keterangan wajib diisi")
    if len(baris) < 2:
        raise ValueError("Jurnal minimal terdiri dari dua baris")
    if any(b[0] == "2.1.01" for b in baris):
        raise ValueError("Akun 2.1.01 Tabungan hanya lewat menu Transaksi teller")
    td, tk = sum(b[1] for b in baris), sum(b[2] for b in baris)
    if td != tk:
        raise ValueError(f"Jurnal tidak seimbang (debit {td:,} vs kredit {tk:,})")
    if periode_ditutup(conn, tanggal):
        raise ValueError("Periode sudah ditutup")
    payload = {"tanggal": tanggal, "keterangan": keterangan.strip(), "baris": [list(b) for b in baris]}
    if user["peran"] == "supervisor":
        return {"status": "langsung", "no_jurnal": _jalankan(conn, "jurnal_manual", payload, user["id"])}
    return _simpan(conn, "jurnal_manual", f"Jurnal manual: {keterangan.strip()} ({td:,})", payload, user)


def ajukan_transaksi(conn, jenis, no_rek, jumlah, tanggal, user, tujuan=None):
    """jenis: 'tarik_tunai' atau 'transfer'. Di bawah ambang atau oleh supervisor: langsung dieksekusi."""
    _siap(conn)
    if jenis not in ("tarik_tunai", "transfer"):
        raise ValueError("Jenis transaksi tidak dikenal")
    if not isinstance(jumlah, int) or jumlah <= 0:
        raise ValueError("Jumlah harus bilangan bulat rupiah lebih dari 0")
    rek = _ambil_rek(conn, no_rek)
    if rek["saldo"] < jumlah:
        raise ValueError(f"Saldo tidak cukup (saldo {rek['saldo']:,}, jumlah {jumlah:,})")
    if jenis == "transfer":
        if not tujuan or tujuan == no_rek:
            raise ValueError("Rekening tujuan tidak valid")
        _ambil_rek(conn, tujuan)
    payload = {"no_rek": no_rek, "jumlah": jumlah, "tanggal": tanggal, "tujuan": tujuan}
    if user["peran"] == "supervisor" or jumlah < AMBANG_PERSETUJUAN:
        return {"status": "langsung", "no_jurnal": _jalankan(conn, jenis, payload, user["id"])}
    nama = "Tarik tunai" if jenis == "tarik_tunai" else f"Transfer ke {tujuan}"
    return _simpan(conn, jenis, f"{nama} rek {no_rek} sebesar {jumlah:,}", payload, user)


def _ambil_menunggu(conn, id_):
    row = conn.execute("SELECT * FROM persetujuan WHERE id=?", (id_,)).fetchone()
    if not row:
        raise ValueError(f"Pengajuan #{id_} tidak ditemukan")
    if row["status"] != "menunggu":
        raise ValueError(f"Pengajuan #{id_} sudah {row['status']}")
    return row


def setujui(conn, id_, checker):
    _siap(conn)
    if checker["peran"] != "supervisor":
        raise ValueError("Hanya supervisor yang dapat menyetujui")
    row = _ambil_menunggu(conn, id_)
    if row["maker_id"] == checker["id"]:
        raise ValueError("Pembuat dan penyetuju tidak boleh orang yang sama")
    try:
        conn.execute("UPDATE persetujuan SET status='disetujui', checker_id=?, diputuskan=? WHERE id=?",
                     (checker["id"], _sekarang(), id_))
        no = _jalankan(conn, row["jenis"], json.loads(row["payload"]), row["maker_id"])
        conn.execute("UPDATE persetujuan SET no_jurnal=? WHERE id=?", (no, id_))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return no


def tolak(conn, id_, checker, catatan):
    _siap(conn)
    if checker["peran"] != "supervisor":
        raise ValueError("Hanya supervisor yang dapat menolak")
    if not catatan.strip():
        raise ValueError("Catatan wajib diisi saat menolak")
    _ambil_menunggu(conn, id_)
    conn.execute("UPDATE persetujuan SET status='ditolak', checker_id=?, diputuskan=?, catatan=? WHERE id=?",
                 (checker["id"], _sekarang(), catatan.strip(), id_))
    conn.commit()


def daftar_pengajuan(conn, status=None, maker_id=None):
    _siap(conn)
    sql = """SELECT p.*, m.username AS maker, c.username AS checker FROM persetujuan p
             LEFT JOIN users m ON m.id = p.maker_id LEFT JOIN users c ON c.id = p.checker_id WHERE 1=1"""
    par = []
    if status:
        sql += " AND p.status=?"; par.append(status)
    if maker_id:
        sql += " AND p.maker_id=?"; par.append(maker_id)
    return conn.execute(sql + " ORDER BY p.id DESC", par).fetchall()


def jumlah_menunggu(conn):
    _siap(conn)
    return conn.execute("SELECT COUNT(*) FROM persetujuan WHERE status='menunggu'").fetchone()[0]
