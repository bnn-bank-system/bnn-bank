"""Uji peran CS: migrasi pengguna, pendaftaran, ubah data, status rekening (database sementara)."""
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

try:
    import bcrypt  # noqa: F401
except ImportError:  # hanya untuk lingkungan uji tanpa bcrypt
    import hashlib
    fb = types.ModuleType("bcrypt")
    fb.gensalt = lambda: b"s"
    fb.hashpw = lambda p, s: b"h$" + hashlib.sha256(p).hexdigest().encode()
    fb.checkpw = lambda p, h: h == fb.hashpw(p, b"")
    sys.modules["bcrypt"] = fb

import database

database.DB_PATH = Path(tempfile.mkdtemp()) / "uji.db"
database.init_db()
c = database.get_conn()

from akuntansi import neraca_saldo
from auth import login, seed_users
from data_contoh import isi_data_contoh
from layanan import (buka_rekening_baru, cari_nasabah, daftarkan_nasabah, ringkas_nasabah, ringkasan_cs,
                     riwayat_layanan, ubah_nasabah, ubah_status_rekening)
from transaksi import rekonsiliasi_tabungan, setor_tunai, tarik_tunai


def harus_ditolak(nama, fn):
    try:
        fn(); print("  GAGAL, seharusnya ditolak:", nama); raise SystemExit(1)
    except ValueError as e:
        print(f"  Ditolak (seharusnya) - {nama}: {e}")


print("1. Migrasi tabel pengguna dari versi lama (tanpa peran cs)")
for i, (u, r) in enumerate([("supervisor", "supervisor"), ("akuntan", "akuntan"), ("teller", "teller")], 1):
    c.execute("INSERT INTO users(id, username, password_hash, peran) VALUES (?,?,?,?)", (i, u, "hash_lama", r))
c.execute("INSERT INTO jurnal(no_jurnal, tanggal, keterangan, user_id) VALUES ('JU-0001','2026-01-01','uji',3)")
c.commit()
try:
    c.execute("INSERT INTO users(username, password_hash, peran) VALUES ('x','h','cs')")
    print("  GAGAL: skema lama seharusnya menolak peran cs"); raise SystemExit(1)
except sqlite3.IntegrityError:
    c.rollback(); print("  Skema lama menolak peran cs (sesuai dugaan)")
seed_users(c)
seed_users(c)
rows = c.execute("SELECT id, username, peran FROM users ORDER BY id").fetchall()
print("  Setelah migrasi:", [(r["id"], r["username"], r["peran"]) for r in rows])
assert [r["username"] for r in rows] == ["supervisor", "akuntan", "teller", "cs"]
assert c.execute("SELECT password_hash FROM users WHERE id=1").fetchone()[0] == "hash_lama", "data lama harus utuh"
assert c.execute("SELECT u.username FROM jurnal j JOIN users u ON u.id=j.user_id").fetchone()[0] == "teller"
assert c.execute("PRAGMA foreign_key_check").fetchall() == []
print("  Data pengguna lama utuh, relasi jurnal ke pengguna utuh, seed berulang tidak menggandakan akun")
c.execute("DELETE FROM jurnal"); c.commit()  # bersihkan jurnal contoh agar data contoh bisa diisi
u_cs = login(c, "cs", "Bnn@2026"); print("  Login cs:", u_cs)
harus_ditolak("password salah", lambda: login(c, "cs", "salah"))

print("\n2. Pendaftaran nasabah")
isi_data_contoh(c)
harus_ditolak("NIK kurang dari 16 digit", lambda: daftarkan_nasabah(c, "Rina", "123", "Banjar", u_cs))
harus_ditolak("NIK mengandung huruf", lambda: daftarkan_nasabah(c, "Rina", "32010000000000AB", "Banjar", u_cs))
harus_ditolak("NIK sudah terdaftar", lambda: daftarkan_nasabah(c, "Rina", "3201000000000001", "Banjar", u_cs))
harus_ditolak("nama kosong", lambda: daftarkan_nasabah(c, " ", "3201000000000099", "Banjar", u_cs))
cif = daftarkan_nasabah(c, "Rina Marlina", "3201000000000099", "Banjar", u_cs)
no_rek = buka_rekening_baru(c, cif, u_cs)
print(f"  Nasabah {cif}, rekening {no_rek}, saldo awal:", c.execute("SELECT saldo FROM rekening WHERE no_rek=?", (no_rek,)).fetchone()[0])
assert c.execute("SELECT saldo FROM rekening WHERE no_rek=?", (no_rek,)).fetchone()[0] == 0

print("\n3. Cari dan ubah data")
print("  Cari 'rina':", [r["cif"] for r in cari_nasabah(c, "rina")], "| cari no. rekening:", [r["cif"] for r in cari_nasabah(c, no_rek)])
assert cari_nasabah(c, "rina")[0]["jumlah_rekening"] == 1
ubah_nasabah(c, cif, "Rina Marlina S.", "3201000000000099", "Ciamis", u_cs)
assert c.execute("SELECT alamat FROM nasabah WHERE cif=?", (cif,)).fetchone()[0] == "Ciamis"
harus_ditolak("NIK dipakai nasabah lain", lambda: ubah_nasabah(c, cif, "Rina", "3201000000000002", "Ciamis", u_cs))

print("\n4. Status rekening")
harus_ditolak("blokir tanpa alasan", lambda: ubah_status_rekening(c, no_rek, "diblokir", " ", u_cs))
ubah_status_rekening(c, no_rek, "diblokir", "Permintaan nasabah (kartu hilang)", u_cs)
harus_ditolak("setor tunai ke rekening diblokir", lambda: setor_tunai(c, no_rek, 100_000))
ubah_status_rekening(c, no_rek, "aktif", "Nasabah sudah memverifikasi identitas", u_cs)
setor_tunai(c, no_rek, 500_000)
harus_ditolak("tutup rekening bersaldo", lambda: ubah_status_rekening(c, no_rek, "tutup", "Pindah bank", u_cs))
tarik_tunai(c, no_rek, 500_000)
ubah_status_rekening(c, no_rek, "tutup", "Pindah bank", u_cs)
print("  Rekening", no_rek, "ditutup setelah saldo nol")
harus_ditolak("mengubah rekening yang sudah ditutup", lambda: ubah_status_rekening(c, no_rek, "aktif", "Coba", u_cs))
harus_ditolak("setor ke rekening tertutup", lambda: setor_tunai(c, no_rek, 100_000))
k_rek = c.execute("SELECT no_rek FROM kredit WHERE status='aktif' LIMIT 1").fetchone()[0]
d_rek = c.execute("SELECT no_rek FROM deposito WHERE status='aktif' LIMIT 1").fetchone()[0]
for rk, ket in ((k_rek, "kredit aktif"), (d_rek, "deposito aktif")):
    s = c.execute("SELECT saldo FROM rekening WHERE no_rek=?", (rk,)).fetchone()[0]
    if s:
        tarik_tunai(c, rk, s)
    harus_ditolak(f"tutup rekening dengan {ket}", lambda rk=rk: ubah_status_rekening(c, rk, "tutup", "Uji", u_cs))

print("\n5. Ringkasan dan riwayat")
r = ringkas_nasabah(c, c.execute("SELECT r.cif FROM kredit k JOIN rekening r ON r.no_rek=k.no_rek LIMIT 1").fetchone()[0])
print("  Ringkasan nasabah berkredit: rekening", len(r["rekening"]), "| kredit", len(r["kredit"]), "| deposito", len(r["deposito"]))
assert len(r["kredit"]) == 1
print("  Ringkasan CS:", ringkasan_cs(c))
for x in riwayat_layanan(c, 6):
    print(f"   {x['waktu']} {x['username']:<4} {x['aksi']:<22} {x['keterangan'][:60]}")
assert len(riwayat_layanan(c, 100)) == 6, "harus ada 6 tindakan CS tercatat"

_, td, tk = neraca_saldo(c)
assert td == tk and rekonsiliasi_tabungan(c)[2]
print("\n  Neraca saldo seimbang dan rekonsiliasi tabungan sesuai")
print("\nSEMUA UJI LOLOS")
