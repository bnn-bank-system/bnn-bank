"""Mengisi data contoh agar aplikasi langsung terlihat hidup saat didemokan."""
from datetime import date, timedelta

from akuntansi import buat_jurnal
from deposito import akrual_deposito, proses_jatuh_tempo, tempatkan_deposito
from kredit import akrual_bunga, bayar_angsuran, bentuk_ckpn, cairkan_kredit
from transaksi import buat_nasabah, buka_rekening, setor_tunai, tarik_tunai, transfer


def _bayar_sampai(conn, no_kredit, batas):
    """Membayar angsuran yang sudah jatuh tempo sampai batas; berhenti bila saldo tidak cukup (menunggak)."""
    while True:
        a = conn.execute(
            """SELECT a.jatuh_tempo FROM angsuran a JOIN kredit k ON k.id = a.kredit_id
               WHERE k.no_kredit=? AND a.status='belum' ORDER BY a.ke LIMIT 1""",
            (no_kredit,)).fetchone()
        if not a or a["jatuh_tempo"] > batas:
            return
        try:
            bayar_angsuran(conn, no_kredit, a["jatuh_tempo"])
        except ValueError:
            return


def isi_data_contoh(conn):
    if conn.execute("SELECT COUNT(*) FROM jurnal").fetchone()[0] > 0:
        raise ValueError("Data sudah ada, data contoh hanya bisa diisi pada database kosong")

    hari = date.today()
    t = lambda n: (hari - timedelta(days=n)).isoformat()

    buat_jurnal(conn, t(200), "Setoran modal pendiri",
                [("1.1.01", 700_000_000, 0), ("3.1.01", 0, 700_000_000)])

    a = buat_nasabah(conn, "Siti Aminah", "3201000000000001", "Banjar", t(200))
    b = buat_nasabah(conn, "Budi Santoso", "3201000000000002", "Ciamis", t(200))
    c = buat_nasabah(conn, "Dewi Lestari", "3201000000000003", "Tasikmalaya", t(200))
    ra = buka_rekening(conn, a, 25_000_000, t(200))
    rb = buka_rekening(conn, b, 15_000_000, t(200))
    rc = buka_rekening(conn, c, 10_000_000, t(200))

    setor_tunai(conn, ra, 5_000_000, t(190))
    tarik_tunai(conn, ra, 2_000_000, t(180))
    transfer(conn, ra, rb, 3_000_000, t(170))

    # Kredit 1: Siti menarik hampir seluruh dana, sehingga lama-lama menunggak
    k1 = cairkan_kredit(conn, ra, 20_000_000, 12.0, 12, "anuitas", t(150))
    tarik_tunai(conn, ra, 40_000_000, t(149))
    # Kredit 2: Budi membayar tepat waktu
    k2 = cairkan_kredit(conn, rb, 30_000_000, 15.0, 6, "flat", t(100))
    _bayar_sampai(conn, k1, t(0))
    _bayar_sampai(conn, k2, t(0))

    tempatkan_deposito(conn, rc, 8_000_000, 5.5, 3, True, t(100))
    proses_jatuh_tempo(conn, t(0))
    buat_jurnal(conn, t(0), "Beban operasional",
                [("5.2.01", 1_000_000, 0), ("1.1.01", 0, 1_000_000)])
    akrual_bunga(conn, t(0))
    akrual_deposito(conn, t(0))
    bentuk_ckpn(conn, t(0))
    return "Data contoh berhasil diisi (3 nasabah, 2 kredit, 1 deposito)"
