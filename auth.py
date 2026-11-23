"""Login, pengguna, dan log aktivitas BNN. Password disimpan sebagai hash bcrypt, bukan teks biasa.

Peran: teller, akuntan, supervisor, cs (customer service).
Tabel users dari versi lama otomatis dimigrasi agar menerima peran cs; data dan nomor pengguna tetap.
"""
import re
from datetime import datetime

import bcrypt

PERAN = ("teller", "akuntan", "supervisor", "cs")

USER_AWAL = [
    ("supervisor", "Bnn@2026", "supervisor"),
    ("akuntan", "Bnn@2026", "akuntan"),
    ("teller", "Bnn@2026", "teller"),
    ("cs", "Bnn@2026", "cs"),
]

_MIGRASI = """
PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE users_baru (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    peran TEXT NOT NULL CHECK (peran IN ('teller','akuntan','supervisor','cs'))
);
INSERT INTO users_baru(id, username, password_hash, peran) SELECT id, username, password_hash, peran FROM users;
DROP TABLE users;
ALTER TABLE users_baru RENAME TO users;
COMMIT;
PRAGMA foreign_keys=ON;
"""


def _hash(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _cek(pw, h):
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def _validasi_password(pw):
    if len(pw) < 8:
        raise ValueError("Password minimal 8 karakter")
    if len(pw.encode()) > 72:
        raise ValueError("Password terlalu panjang (maksimal 72 karakter)")


def _siap(conn):
    r = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if r is None:
        raise RuntimeError("Tabel users belum ada. Jalankan init_db() terlebih dulu")
    if "'cs'" not in r[0]:
        conn.commit()
        conn.executescript(_MIGRASI)
    conn.execute("""CREATE TABLE IF NOT EXISTS log_aktivitas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT NOT NULL, user_id INTEGER,
        username TEXT NOT NULL, aksi TEXT NOT NULL, keterangan TEXT)""")
    conn.commit()


def catat(conn, user, aksi, keterangan=""):
    """Mencatat aktivitas penting (misalnya layanan CS) beserta pelakunya."""
    conn.execute("INSERT INTO log_aktivitas(waktu, user_id, username, aksi, keterangan) VALUES (?,?,?,?,?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["id"], user["username"], aksi, keterangan))
    conn.commit()


def seed_users(conn):
    """Memastikan akun demo ada. Akun yang sudah ada (termasuk password yang sudah diganti) tidak diubah."""
    _siap(conn)
    for u, p, r in USER_AWAL:
        if not conn.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            conn.execute("INSERT INTO users(username, password_hash, peran) VALUES (?,?,?)", (u, _hash(p), r))
    conn.commit()


def login(conn, username, password):
    row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    if not row or not _cek(password, row["password_hash"]):
        raise ValueError("Username atau password salah")
    return {"id": row["id"], "username": row["username"], "peran": row["peran"]}


def tambah_user(conn, username, password, peran):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,20}", username):
        raise ValueError("Username 3-20 karakter: huruf kecil, angka, atau garis bawah")
    if peran not in PERAN:
        raise ValueError("Peran tidak valid")
    _validasi_password(password)
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise ValueError("Username sudah dipakai")
    conn.execute("INSERT INTO users(username, password_hash, peran) VALUES (?,?,?)",
                 (username, _hash(password), peran))
    conn.commit()


def ganti_password(conn, user_id, lama, baru):
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not _cek(lama, row["password_hash"]):
        raise ValueError("Password lama salah")
    _validasi_password(baru)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(baru), user_id))
    conn.commit()


def daftar_user(conn):
    return conn.execute("SELECT username, peran FROM users ORDER BY id").fetchall()
