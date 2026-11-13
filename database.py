import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bnn.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SKEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    peran TEXT NOT NULL CHECK (peran IN ('teller','akuntan','supervisor'))
);

CREATE TABLE IF NOT EXISTS akun (
    kode TEXT PRIMARY KEY,
    nama TEXT NOT NULL,
    kelompok TEXT NOT NULL CHECK (kelompok IN ('aset','liabilitas','ekuitas','pendapatan','beban')),
    saldo_normal TEXT NOT NULL CHECK (saldo_normal IN ('D','K'))
);

CREATE TABLE IF NOT EXISTS nasabah (
    cif TEXT PRIMARY KEY,
    nama TEXT NOT NULL,
    nik TEXT,
    alamat TEXT,
    tgl_daftar TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rekening (
    no_rek TEXT PRIMARY KEY,
    cif TEXT NOT NULL REFERENCES nasabah(cif),
    jenis TEXT NOT NULL CHECK (jenis IN ('tabungan','giro','deposito')),
    saldo INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'aktif'
);

CREATE TABLE IF NOT EXISTS periode (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulan INTEGER NOT NULL,
    tahun INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'terbuka' CHECK (status IN ('terbuka','ditutup')),
    UNIQUE (bulan, tahun)
);

CREATE TABLE IF NOT EXISTS jurnal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no_jurnal TEXT UNIQUE,
    tanggal TEXT NOT NULL,
    keterangan TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS jurnal_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurnal_id INTEGER NOT NULL REFERENCES jurnal(id),
    kode_akun TEXT NOT NULL REFERENCES akun(kode),
    debit INTEGER NOT NULL DEFAULT 0 CHECK (debit >= 0),
    kredit INTEGER NOT NULL DEFAULT 0 CHECK (kredit >= 0)
);
"""

AKUN_AWAL = [
    ("1.1.01", "Kas", "aset", "D"),
    ("1.1.02", "Giro pada Bank Indonesia", "aset", "D"),
    ("1.2.01", "Kredit yang diberikan", "aset", "D"),
    ("1.2.02", "Bunga yang masih akan diterima", "aset", "D"),
    ("1.2.09", "CKPN kredit", "aset", "K"),
    ("1.3.01", "Aset tetap", "aset", "D"),
    ("2.1.01", "Tabungan", "liabilitas", "K"),
    ("2.1.02", "Deposito", "liabilitas", "K"),
    ("3.1.01", "Modal disetor", "ekuitas", "K"),
    ("4.1.01", "Pendapatan bunga", "pendapatan", "K"),
    ("5.1.01", "Beban bunga", "beban", "D"),
    ("5.2.01", "Beban operasional", "beban", "D"),
    ("5.3.01", "Beban kerugian kredit", "beban", "D"),
]


def init_db():
    conn = get_conn()
    conn.executescript(SKEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO akun(kode, nama, kelompok, saldo_normal) VALUES (?,?,?,?)",
        AKUN_AWAL,
    )
    conn.commit()
    jumlah = conn.execute("SELECT COUNT(*) FROM akun").fetchone()[0]
    conn.close()
    return jumlah


if __name__ == "__main__":
    print("Database siap. Jumlah akun:", init_db())
