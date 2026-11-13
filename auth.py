"""Login dan pengguna BNN. Password disimpan sebagai hash bcrypt, bukan teks biasa."""
import re

import bcrypt

PERAN = ("teller", "akuntan", "supervisor")

USER_AWAL = [
    ("supervisor", "Bnn@2026", "supervisor"),
    ("akuntan", "Bnn@2026", "akuntan"),
    ("teller", "Bnn@2026", "teller"),
]


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


def seed_users(conn):
    """Membuat tiga akun demo jika tabel users masih kosong."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for u, p, r in USER_AWAL:
            conn.execute("INSERT INTO users(username, password_hash, peran) VALUES (?,?,?)",
                         (u, _hash(p), r))
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
