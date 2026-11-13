"""Modul kredit BNN: pencairan, jadwal angsuran, bunga akrual, kolektibilitas, CKPN.

Jurnal yang dibentuk:
  Pencairan   : D 1.2.01 Kredit yang diberikan          K 2.1.01 Tabungan nasabah
  Akrual bunga: D 1.2.02 Bunga yang masih akan diterima K 4.1.01 Pendapatan bunga
  Angsuran    : D 2.1.01 Tabungan  K 1.2.01 (pokok)  K 1.2.02 (bunga yang sudah diakrual)
                                   K 4.1.01 (bunga yang belum diakrual)
  CKPN        : D 5.3.01 Beban kerugian kredit          K 1.2.09 CKPN kredit  (atau sebaliknya)

CATATAN: tarif CKPN di bawah adalah ASUMSI penyederhanaan dari PSAK 71 (tahap 1/2/3)
dan boleh diubah sesuai arahan dosen atau ketentuan yang berlaku.
"""
import calendar
import math
from datetime import date

from akuntansi import buat_jurnal
from transaksi import _ambil_rek

AKUN_KREDIT = "1.2.01"
AKUN_BUNGA_YAD = "1.2.02"
AKUN_CKPN = "1.2.09"
AKUN_BEBAN_CKPN = "5.3.01"
AKUN_PEND_BUNGA = "4.1.01"
AKUN_TABUNGAN = "2.1.01"

TARIF_CKPN = {1: 0.01, 2: 0.05, 3: 0.15, 4: 0.50, 5: 1.00}
NAMA_KOL = {1: "Lancar", 2: "Dalam perhatian khusus", 3: "Kurang lancar",
            4: "Diragukan", 5: "Macet"}


def _siap(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS kredit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, no_kredit TEXT UNIQUE NOT NULL,
        no_rek TEXT NOT NULL REFERENCES rekening(no_rek),
        plafon INTEGER NOT NULL, bunga_tahunan REAL NOT NULL, tenor INTEGER NOT NULL,
        metode TEXT NOT NULL, tgl_cair TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'aktif')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS angsuran (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kredit_id INTEGER NOT NULL REFERENCES kredit(id),
        ke INTEGER NOT NULL, jatuh_tempo TEXT NOT NULL, pokok INTEGER NOT NULL, bunga INTEGER NOT NULL,
        bunga_diakui INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'belum',
        tgl_bayar TEXT, UNIQUE (kredit_id, ke))""")


def _bulat(x):
    return int(math.floor(x + 0.5))


def tambah_bulan(d, n):
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def hitung_jadwal(plafon, bunga_tahunan, tenor, metode, tgl_cair):
    """Mengembalikan daftar angsuran. Jumlah pokok selalu persis sama dengan plafon."""
    if not isinstance(plafon, int) or plafon <= 0:
        raise ValueError("Plafon harus bilangan bulat rupiah lebih dari 0")
    if not 1 <= tenor <= 360:
        raise ValueError("Tenor 1 sampai 360 bulan")
    if bunga_tahunan < 0:
        raise ValueError("Suku bunga tidak boleh negatif")
    if metode not in ("anuitas", "flat"):
        raise ValueError("Metode harus anuitas atau flat")

    r = bunga_tahunan / 100 / 12
    sisa = plafon
    pmt = _bulat(plafon * r / (1 - (1 + r) ** -tenor)) if r > 0 else _bulat(plafon / tenor)
    jadwal = []
    for ke in range(1, tenor + 1):
        if metode == "anuitas":
            bunga = _bulat(sisa * r)
            pokok = sisa if ke == tenor else pmt - bunga
        else:
            bunga = _bulat(plafon * r)
            pokok = sisa if ke == tenor else plafon // tenor
        sisa -= pokok
        jadwal.append({"ke": ke, "jatuh_tempo": tambah_bulan(tgl_cair, ke).isoformat(),
                       "pokok": pokok, "bunga": bunga})
    return jadwal


def cairkan_kredit(conn, no_rek, plafon, bunga_tahunan, tenor, metode="anuitas",
                   tanggal=None, user_id=None):
    _siap(conn)
    tgl = date.fromisoformat(tanggal) if tanggal else date.today()
    try:
        _ambil_rek(conn, no_rek)
        jadwal = hitung_jadwal(plafon, bunga_tahunan, tenor, metode, tgl)
        no_kredit = f"KRD-{conn.execute('SELECT COUNT(*) FROM kredit').fetchone()[0] + 1:04d}"
        kid = conn.execute(
            """INSERT INTO kredit(no_kredit, no_rek, plafon, bunga_tahunan, tenor, metode, tgl_cair)
               VALUES (?,?,?,?,?,?,?)""",
            (no_kredit, no_rek, plafon, bunga_tahunan, tenor, metode, tgl.isoformat())).lastrowid
        conn.executemany(
            "INSERT INTO angsuran(kredit_id, ke, jatuh_tempo, pokok, bunga) VALUES (?,?,?,?,?)",
            [(kid, j["ke"], j["jatuh_tempo"], j["pokok"], j["bunga"]) for j in jadwal])
        conn.execute("UPDATE rekening SET saldo = saldo + ? WHERE no_rek=?", (plafon, no_rek))
        buat_jurnal(conn, tgl.isoformat(), f"Pencairan kredit {no_kredit} ke rek {no_rek}",
                    [(AKUN_KREDIT, plafon, 0), (AKUN_TABUNGAN, 0, plafon)], user_id)
    except Exception:
        conn.rollback()
        raise
    return no_kredit


def _ambil_kredit(conn, no_kredit):
    k = conn.execute("SELECT * FROM kredit WHERE no_kredit=?", (no_kredit,)).fetchone()
    if not k:
        raise ValueError(f"Kredit {no_kredit} tidak ditemukan")
    if k["status"] != "aktif":
        raise ValueError(f"Kredit {no_kredit} sudah {k['status']}")
    return k


def bayar_angsuran(conn, no_kredit, tanggal=None, user_id=None):
    """Mendebet rekening tabungan nasabah untuk angsuran terlama yang belum dibayar."""
    _siap(conn)
    tgl = tanggal or date.today().isoformat()
    try:
        k = _ambil_kredit(conn, no_kredit)
        a = conn.execute("SELECT * FROM angsuran WHERE kredit_id=? AND status='belum' "
                         "ORDER BY ke LIMIT 1", (k["id"],)).fetchone()
        if not a:
            raise ValueError("Tidak ada angsuran yang belum dibayar")
        total = a["pokok"] + a["bunga"]
        rek = _ambil_rek(conn, k["no_rek"])
        if rek["saldo"] < total:
            raise ValueError(f"Saldo tidak cukup untuk angsuran ke-{a['ke']} "
                             f"(butuh {total:,}, saldo {rek['saldo']:,})")
        conn.execute("UPDATE rekening SET saldo = saldo - ? WHERE no_rek=?", (total, k["no_rek"]))

        baris = [(AKUN_TABUNGAN, total, 0)]
        if a["pokok"] > 0:
            baris.append((AKUN_KREDIT, 0, a["pokok"]))
        if a["bunga_diakui"] > 0:
            baris.append((AKUN_BUNGA_YAD, 0, a["bunga_diakui"]))
        if a["bunga"] - a["bunga_diakui"] > 0:
            baris.append((AKUN_PEND_BUNGA, 0, a["bunga"] - a["bunga_diakui"]))

        conn.execute("UPDATE angsuran SET status='lunas', bunga_diakui=bunga, tgl_bayar=? WHERE id=?",
                     (tgl, a["id"]))
        sisa = conn.execute("SELECT COUNT(*) FROM angsuran WHERE kredit_id=? AND status='belum'",
                            (k["id"],)).fetchone()[0]
        if sisa == 0:
            conn.execute("UPDATE kredit SET status='lunas' WHERE id=?", (k["id"],))
        return buat_jurnal(conn, tgl, f"Angsuran ke-{a['ke']} kredit {no_kredit}", baris, user_id)
    except Exception:
        conn.rollback()
        raise


def akrual_bunga(conn, tanggal, user_id=None):
    """Mengakui pendapatan bunga yang sudah 'berjalan' sampai tanggal (biasanya akhir bulan),
    secara proporsional per hari. Aman dijalankan berulang, tidak ada pengakuan ganda.
    Mengembalikan (jumlah, no_jurnal)."""
    _siap(conn)
    t = date.fromisoformat(tanggal)
    total = 0
    try:
        for k in conn.execute("SELECT * FROM kredit WHERE status='aktif' AND tgl_cair <= ?",
                              (tanggal,)).fetchall():
            awal = date.fromisoformat(k["tgl_cair"])
            for a in conn.execute("SELECT * FROM angsuran WHERE kredit_id=? ORDER BY ke",
                                  (k["id"],)).fetchall():
                tempo = date.fromisoformat(a["jatuh_tempo"])
                if a["status"] == "belum" and awal < t:
                    hari_periode = (tempo - awal).days
                    hari_lalu = min((t - awal).days, hari_periode)
                    target = _bulat(a["bunga"] * hari_lalu / hari_periode) if hari_periode else a["bunga"]
                    delta = target - a["bunga_diakui"]
                    if delta > 0:
                        conn.execute("UPDATE angsuran SET bunga_diakui = bunga_diakui + ? WHERE id=?",
                                     (delta, a["id"]))
                        total += delta
                awal = tempo
        if total == 0:
            conn.rollback()
            return 0, None
        no = buat_jurnal(conn, tanggal, f"Akrual pendapatan bunga kredit s.d. {tanggal}",
                         [(AKUN_BUNGA_YAD, total, 0), (AKUN_PEND_BUNGA, 0, total)], user_id)
        return total, no
    except Exception:
        conn.rollback()
        raise


def kolektibilitas(conn, no_kredit, tanggal):
    """Mengembalikan (hari_tunggakan, kolektibilitas 1-5).
    1: tidak ada tunggakan | 2: 1-90 hari | 3: 91-120 | 4: 121-180 | 5: lebih dari 180."""
    _siap(conn)
    k = conn.execute("SELECT id FROM kredit WHERE no_kredit=?", (no_kredit,)).fetchone()
    if not k:
        raise ValueError(f"Kredit {no_kredit} tidak ditemukan")
    return _kol(conn, k["id"], tanggal)


def _kol(conn, kredit_id, tanggal):
    a = conn.execute("SELECT jatuh_tempo FROM angsuran WHERE kredit_id=? AND status='belum' "
                     "AND jatuh_tempo < ? ORDER BY ke LIMIT 1", (kredit_id, tanggal)).fetchone()
    dpd = (date.fromisoformat(tanggal) - date.fromisoformat(a["jatuh_tempo"])).days if a else 0
    kol = 1 if dpd <= 0 else 2 if dpd <= 90 else 3 if dpd <= 120 else 4 if dpd <= 180 else 5
    return dpd, kol


def hitung_ckpn(conn, tanggal):
    _siap(conn)
    rincian, total = [], 0
    for k in conn.execute("SELECT * FROM kredit WHERE status='aktif' ORDER BY id").fetchall():
        sisa = conn.execute("SELECT COALESCE(SUM(pokok),0) FROM angsuran WHERE kredit_id=? "
                            "AND status='belum'", (k["id"],)).fetchone()[0]
        dpd, kol = _kol(conn, k["id"], tanggal)
        ckpn = _bulat(sisa * TARIF_CKPN[kol])
        total += ckpn
        rincian.append({"no_kredit": k["no_kredit"], "sisa_pokok": sisa, "hari_tunggakan": dpd,
                        "kolektibilitas": kol, "keterangan": NAMA_KOL[kol],
                        "tarif": TARIF_CKPN[kol], "ckpn": ckpn})
    saldo = conn.execute("SELECT COALESCE(SUM(kredit - debit),0) FROM jurnal_detail "
                         "WHERE kode_akun=?", (AKUN_CKPN,)).fetchone()[0]
    return {"rincian": rincian, "ckpn_dibutuhkan": total, "saldo_ckpn": saldo, "selisih": total - saldo}


def bentuk_ckpn(conn, tanggal, user_id=None):
    """Menyesuaikan saldo CKPN ke kebutuhan. Mengembalikan no_jurnal, atau None bila sudah sesuai."""
    h = hitung_ckpn(conn, tanggal)
    s = h["selisih"]
    if s == 0:
        return None
    if s > 0:
        baris = [(AKUN_BEBAN_CKPN, s, 0), (AKUN_CKPN, 0, s)]
        ket = f"Pembentukan CKPN kredit per {tanggal}"
    else:
        baris = [(AKUN_CKPN, -s, 0), (AKUN_BEBAN_CKPN, 0, -s)]
        ket = f"Pemulihan CKPN kredit per {tanggal}"
    return buat_jurnal(conn, tanggal, ket, baris, user_id)
