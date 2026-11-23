"""Aplikasi akuntansi bank BNN (Bank Neneng Nopitasari).

Jalankan:  streamlit run app.py
"""
import base64
import json
import time
from datetime import date

import pandas as pd
import streamlit as st

from akhir_bulan import _siap as init_akhir_bulan
from akhir_bulan import (AKUN_TERKENDALI, AMBANG_PAJAK, BIAYA_ADMIN, SALDO_MIN_BUNGA, TARIF_BUNGA,
                         TARIF_PAJAK, balik_jurnal, buka_kembali, proses_bulanan, status_periode,
                         tutup_buku)
from akuntansi import buat_jurnal, buku_besar, neraca_saldo, rupiah
from auth import PERAN, daftar_user, ganti_password, login, seed_users, tambah_user
from data_contoh import isi_data_contoh
from database import get_conn, init_db
from deposito import _siap as init_deposito
from deposito import (_bunga_periode, _pajak, akrual_deposito, daftar_deposito, proses_jatuh_tempo,
                      rekonsiliasi_deposito, tempatkan_deposito)
from ekspor import excel_laporan, pdf_laporan
from kredit import _siap as init_kredit
from lanjutan import _siap as init_lanjutan
from lanjutan import arus_kas, jurnal_penutup, perubahan_ekuitas, rasio
from kredit import (akrual_bunga, bayar_angsuran, bentuk_ckpn, cairkan_kredit,
                    hitung_ckpn, hitung_jadwal)
from layanan import (buka_rekening_baru, cari_nasabah, daftarkan_nasabah, ringkas_nasabah, ringkasan_cs,
                     riwayat_layanan, ubah_nasabah, ubah_status_rekening)
from laporan import laba_rugi, posisi_keuangan, ringkasan
from persetujuan import _siap as init_persetujuan
from persetujuan import (AMBANG_PERSETUJUAN, ajukan_jurnal_manual, ajukan_transaksi, daftar_pengajuan,
                         jumlah_menunggu, setujui, tolak)
from transaksi import (buat_nasabah, buka_rekening, rekonsiliasi_tabungan,
                       setor_tunai, tarik_tunai, transfer)

# ---------- logo pita (SVG beranimasi, dipakai di login, loading, dan indikator) ----------
PITA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100">
<style>
.a{transform-box:fill-box;animation-duration:1.5s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}
.tl{transform-origin:100% 0%;animation-name:sl}.tr{transform-origin:0% 0%;animation-name:sr}
.ll{transform-origin:100% 50%;animation-name:pl}.lr{transform-origin:0% 50%;animation-name:pr}
.kn{transform-origin:50% 50%;animation-name:k}
@keyframes sl{0%,100%{transform:rotate(0)}50%{transform:rotate(7deg)}}
@keyframes sr{0%,100%{transform:rotate(0)}50%{transform:rotate(-7deg)}}
@keyframes pl{0%,100%{transform:scale(1)}50%{transform:scale(1.1,.9)}}
@keyframes pr{0%,100%{transform:scale(1)}50%{transform:scale(1.1,.9)}}
@keyframes k{0%,100%{transform:scale(1)}50%{transform:scale(1.12)}}
</style>
<g stroke="#B76E79" stroke-width="2" stroke-linejoin="round">
<path class="a tl" fill="#C98F98" d="M54 50 L34 92 L46 86 L52 96 L62 52 Z"/>
<path class="a tr" fill="#C98F98" d="M66 50 L86 92 L74 86 L68 96 L58 52 Z"/>
<path class="a ll" fill="#D8B4B8" d="M54 42 C40 8 4 12 8 42 C4 72 40 76 54 42 Z"/>
<path class="a lr" fill="#D8B4B8" d="M66 42 C80 8 116 12 112 42 C116 72 80 76 66 42 Z"/>
<rect class="a kn" fill="#B76E79" x="50" y="32" width="20" height="20" rx="8"/>
</g></svg>"""
PITA_URI = "data:image/svg+xml;base64," + base64.b64encode(PITA_SVG.encode()).decode()

CSS = """
<style>
.stApp {background:#FBF4F4;}
[data-testid="stSidebar"] {background:#EBD3D5;}
h1, h2, h3, h4 {color:#5E3A41;}
.bnn-top {background:#B76E79;color:#FFF7F7;padding:12px 20px;border-radius:12px;margin-bottom:14px;
          display:flex;justify-content:space-between;align-items:center;}
.bnn-top b {font-size:22px;letter-spacing:3px;} .bnn-top span {font-size:13px;opacity:.9;margin-left:10px;}
[data-testid="stMetric"] {background:#F3DFE1;border-radius:10px;padding:10px 14px;}
[data-testid="stMetricValue"] {font-size:1.5rem;}
[data-testid="stMetricValue"] div {overflow:visible;text-overflow:clip;white-space:nowrap;}
[data-testid="stForm"] {background:#F7ECEC;border:1px solid #D8B4B8;border-radius:14px;}
.stButton > button, [data-testid="stFormSubmitButton"] button {
    background:#B76E79;color:#FFF7F7;border:none;border-radius:8px;}
.stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {background:#9F5A65;color:#FFF7F7;}
/* indikator "sedang memuat" bawaan Streamlit diganti pita kecil */
[data-testid="stStatusWidget"] {visibility:hidden;}
[data-testid="stStatusWidget"]::after {visibility:visible;content:"";position:fixed;top:6px;right:90px;
    width:52px;height:44px;background:url("__PITA__") center/contain no-repeat;}
/* layar loading pita */
.bnn-splash {position:fixed;inset:0;z-index:99999;background:rgba(251,244,244,.96);
    display:flex;flex-direction:column;align-items:center;justify-content:center;}
.bnn-splash b {font-size:30px;letter-spacing:6px;color:#5E3A41;margin-top:6px;}
.bnn-splash span {color:#8A6A35;font-size:14px;}
.bnn-dots::after {content:"";animation:bnn-d 1.2s steps(1) infinite;}
@keyframes bnn-d {0%{content:""}25%{content:"."}50%{content:".."}75%,100%{content:"..."}}
.bnn-login {text-align:center;margin-top:30px;}
.bnn-login h1 {margin:0;letter-spacing:6px;} .bnn-login p {color:#8A6A35;margin:0 0 14px;}
</style>
""".replace("__PITA__", PITA_URI)

CSS_LOGIN = """<style>[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {display:none;}</style>"""


PERAN_LABEL = {"cs": "Customer Service"}


def splash(teks="Memuat"):
    kotak = st.empty()
    kotak.markdown(
        f'<div class="bnn-splash"><img src="{PITA_URI}" width="180"/><b>BNN</b>'
        f'<span>{teks}<i class="bnn-dots"></i></span></div>', unsafe_allow_html=True)
    time.sleep(1.4)
    kotak.empty()


# ---------- alat bantu ----------
def flash(jenis, teks):
    st.session_state["flash"] = (jenis, teks)


def tampil_flash():
    f = st.session_state.pop("flash", None)
    if f:
        (st.success if f[0] == "ok" else st.error)(f[1])


def tabel(df):
    st.dataframe(df, hide_index=True)


def opsi_rekening(conn):
    rows = conn.execute(
        """SELECT r.no_rek, n.nama, r.saldo FROM rekening r JOIN nasabah n ON n.cif = r.cif
           WHERE r.status='aktif' AND r.jenis='tabungan' ORDER BY r.no_rek""").fetchall()
    return {r["no_rek"]: f"{r['no_rek']} - {r['nama']} (saldo {rupiah(r['saldo'])})" for r in rows}


# ---------- halaman ----------
def halaman_dashboard(conn, user):
    st.subheader("Dashboard")
    if user["peran"] == "cs":
        r = ringkasan_cs(conn)
        for kol, (judul, nilai) in zip(st.columns(4), [("Nasabah", r["nasabah"]), ("Rekening aktif", r["aktif"]),
                                                       ("Rekening diblokir", r["diblokir"]),
                                                       ("Nasabah baru (30 hari)", r["baru_30_hari"])]):
            kol.metric(judul, nilai)
        st.info("Gunakan menu Layanan nasabah untuk pendaftaran, perubahan data, dan status rekening. "
                "Setoran awal dan transaksi uang dilayani teller.")
        return
    if user["peran"] == "supervisor" and jumlah_menunggu(conn):
        st.warning(f"{jumlah_menunggu(conn)} pengajuan menunggu persetujuan Anda. Buka menu Persetujuan.")
    r = ringkasan(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total aset", rupiah(r["total_aset"]))
    c2.metric("Dana pihak ketiga", rupiah(r["dpk"]))
    c3.metric("Kredit neto", rupiah(r["kredit_neto"]))
    c4.metric("Laba berjalan", rupiah(r["laba"]))
    rs = rasio(conn)["baris"]
    st.markdown("#### Rasio keuangan (disetahunkan)")
    for kol, x in zip(st.columns(4), [rs[0], rs[1], rs[2], rs[3]]):
        kol.metric(x["nama"], x["teks"], x["status"] if x["status"] != "-" else None, delta_color="off")
    st.markdown("#### Jurnal terbaru")
    rows = conn.execute(
        """SELECT j.tanggal, j.no_jurnal, j.keterangan, SUM(d.debit) AS nominal
           FROM jurnal j JOIN jurnal_detail d ON d.jurnal_id = j.id
           GROUP BY j.id ORDER BY j.id DESC LIMIT 8""").fetchall()
    if not rows:
        st.info("Belum ada transaksi." + (" Klik 'Isi data contoh' di menu kiri untuk mencoba."
                                           if user["peran"] == "supervisor" else ""))
        return
    tabel(pd.DataFrame([{"Tanggal": x["tanggal"], "No. jurnal": x["no_jurnal"],
                         "Keterangan": x["keterangan"], "Nominal": rupiah(x["nominal"])} for x in rows]))


def halaman_nasabah(conn, user):
    st.subheader("Nasabah dan rekening")
    kiri, kanan = st.columns(2)
    with kiri:
        st.markdown("**Daftarkan nasabah baru**")
        with st.form("form_nasabah", clear_on_submit=True):
            nama = st.text_input("Nama lengkap")
            nik = st.text_input("NIK")
            alamat = st.text_input("Alamat")
            kirim = st.form_submit_button("Simpan nasabah")
        if kirim:
            try:
                flash("ok", f"Nasabah tersimpan dengan nomor {buat_nasabah(conn, nama, nik, alamat)}")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()
    with kanan:
        st.markdown("**Buka rekening tabungan**")
        nas = conn.execute("SELECT cif, nama FROM nasabah ORDER BY cif").fetchall()
        if not nas:
            st.info("Belum ada nasabah.")
        else:
            peta = {r["cif"]: f"{r['cif']} - {r['nama']}" for r in nas}
            with st.form("form_rekening", clear_on_submit=True):
                cif = st.selectbox("Nasabah", list(peta), format_func=peta.get)
                setoran = st.number_input("Setoran awal (Rp)", min_value=0, value=0, step=10000)
                kirim = st.form_submit_button("Buka rekening")
            if kirim:
                try:
                    flash("ok", f"Rekening {buka_rekening(conn, cif, int(setoran), None, user['id'])} berhasil dibuka")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()
    st.markdown("#### Daftar rekening")
    rows = conn.execute(
        """SELECT r.no_rek, n.cif, n.nama, r.jenis, r.saldo, r.status
           FROM rekening r JOIN nasabah n ON n.cif = r.cif ORDER BY r.no_rek""").fetchall()
    if rows:
        tabel(pd.DataFrame([{"No. rekening": x["no_rek"], "CIF": x["cif"], "Nama": x["nama"],
                             "Jenis": x["jenis"], "Saldo": rupiah(x["saldo"]), "Status": x["status"]} for x in rows]))
    else:
        st.caption("Belum ada rekening.")


def halaman_transaksi(conn, user):
    st.subheader("Transaksi teller")
    label = opsi_rekening(conn)
    if not label:
        st.info("Belum ada rekening. Buka rekening dulu di menu Nasabah dan rekening.")
        return
    jenis = st.radio("Jenis transaksi", ["Setor tunai", "Tarik tunai", "Transfer"], horizontal=True)
    asal = st.selectbox("Rekening" if jenis != "Transfer" else "Rekening asal", list(label), format_func=label.get)
    tujuan = st.selectbox("Rekening tujuan", list(label), format_func=label.get) if jenis == "Transfer" else None
    jumlah = st.number_input("Jumlah (Rp)", min_value=0, value=0, step=10000)
    tgl = st.date_input("Tanggal transaksi", value=date.today())
    pratinjau = {"Setor tunai": [("1.1.01 Kas", jumlah, 0), ("2.1.01 Tabungan", 0, jumlah)],
                 "Tarik tunai": [("2.1.01 Tabungan", jumlah, 0), ("1.1.01 Kas", 0, jumlah)],
                 "Transfer": [("2.1.01 Tabungan (asal)", jumlah, 0), ("2.1.01 Tabungan (tujuan)", 0, jumlah)]}[jenis]
    st.markdown("**Pratinjau jurnal otomatis**")
    tabel(pd.DataFrame([{"Akun": a, "Debit": rupiah(d), "Kredit": rupiah(k)} for a, d, k in pratinjau]))
    if user["peran"] != "supervisor":
        st.caption(f"Tarik tunai dan transfer mulai {rupiah(AMBANG_PERSETUJUAN)} memerlukan persetujuan supervisor.")
    if st.button("Proses transaksi"):
        try:
            iso = tgl.isoformat()
            if jenis == "Setor tunai":
                no = setor_tunai(conn, asal, int(jumlah), iso, user["id"])
                flash("ok", f"{jenis} berhasil dicatat dengan nomor jurnal {no}")
            else:
                h = ajukan_transaksi(conn, "tarik_tunai" if jenis == "Tarik tunai" else "transfer",
                                     asal, int(jumlah), iso, user, tujuan)
                if h["status"] == "menunggu":
                    flash("ok", f"{jenis} {rupiah(int(jumlah))} memerlukan persetujuan supervisor "
                                f"(pengajuan #{h['id']}). Pembukuan belum berubah.")
                else:
                    flash("ok", f"{jenis} berhasil dicatat dengan nomor jurnal {h['no_jurnal']}")
        except ValueError as e:
            flash("err", str(e))
        st.rerun()


def halaman_jurnal_manual(conn, user):
    st.subheader("Jurnal manual")
    st.caption("Untuk transaksi non-teller: modal, pendapatan, beban, CKPN, dan sejenisnya. "
               "Akun 2.1.01 Tabungan tidak boleh dipakai di sini agar saldo rekening tetap sesuai.")
    akun = conn.execute("SELECT kode, nama FROM akun ORDER BY kode").fetchall()
    peta = {"": "- pilih akun -"}
    peta.update({a["kode"]: f"{a['kode']} - {a['nama']}" for a in akun})
    ver = st.session_state.get("ver_jm", 0)
    tgl = st.date_input("Tanggal", value=date.today(), key=f"jm_tgl_{ver}")
    ket = st.text_input("Keterangan", key=f"jm_ket_{ver}")
    h1, h2, h3 = st.columns([3, 1.3, 1.3])
    h1.markdown("**Akun**"); h2.markdown("**Debit**"); h3.markdown("**Kredit**")
    baris = []
    for i in range(4):
        c1, c2, c3 = st.columns([3, 1.3, 1.3])
        kode = c1.selectbox(f"Akun {i + 1}", list(peta), format_func=peta.get,
                            key=f"jm_k{i}_{ver}", label_visibility="collapsed")
        d = c2.number_input(f"Debit {i + 1}", min_value=0, value=0, step=10000,
                            key=f"jm_d{i}_{ver}", label_visibility="collapsed")
        k = c3.number_input(f"Kredit {i + 1}", min_value=0, value=0, step=10000,
                            key=f"jm_c{i}_{ver}", label_visibility="collapsed")
        if kode and (d or k):
            baris.append((kode, int(d), int(k)))
    td, tk = sum(b[1] for b in baris), sum(b[2] for b in baris)
    st.write(f"Total debit {rupiah(td)} | Total kredit {rupiah(tk)}")
    if baris and td == tk:
        st.success("Jurnal seimbang")
    elif baris:
        st.warning("Jurnal belum seimbang")
    if st.button("Catat jurnal"):
        try:
            if any(b[0] == "2.1.01" for b in baris):
                raise ValueError("Akun 2.1.01 Tabungan hanya lewat menu Transaksi teller")
            if not ket.strip():
                raise ValueError("Keterangan wajib diisi")
            h = ajukan_jurnal_manual(conn, tgl.isoformat(), ket.strip(), baris, user)
            st.session_state["ver_jm"] = ver + 1
            flash("ok", f"Jurnal {h['no_jurnal']} berhasil dicatat" if h["status"] == "langsung" else
                  f"Jurnal diajukan dan menunggu persetujuan supervisor (pengajuan #{h['id']})")
        except ValueError as e:
            flash("err", str(e))
        st.rerun()


def halaman_jurnal_umum(conn, user):
    st.subheader("Jurnal umum")
    a, b = st.columns(2)
    dari = a.date_input("Dari tanggal", value=date(date.today().year, 1, 1))
    sampai = b.date_input("Sampai tanggal", value=date.today())
    rows = conn.execute(
        """SELECT j.id, j.tanggal, j.no_jurnal, j.keterangan, u.username AS petugas,
                  d.kode_akun, a.nama, d.debit, d.kredit
           FROM jurnal_detail d JOIN jurnal j ON j.id = d.jurnal_id
           JOIN akun a ON a.kode = d.kode_akun LEFT JOIN users u ON u.id = j.user_id
           WHERE j.tanggal BETWEEN ? AND ? ORDER BY j.tanggal, j.id, d.id""",
        (dari.isoformat(), sampai.isoformat())).fetchall()
    if not rows:
        st.info("Tidak ada jurnal pada rentang tanggal ini.")
        return
    data, terakhir = [], None
    for r in rows:
        baru = r["id"] != terakhir
        terakhir = r["id"]
        data.append({"Tanggal": r["tanggal"] if baru else "", "No. jurnal": r["no_jurnal"] if baru else "",
                     "Keterangan": r["keterangan"] if baru else "",
                     "Petugas": (r["petugas"] or "-") if baru else "",
                     "Kode": r["kode_akun"], "Akun": r["nama"] if r["debit"] else "    " + r["nama"],
                     "Debit": rupiah(r["debit"]) if r["debit"] else "",
                     "Kredit": rupiah(r["kredit"]) if r["kredit"] else ""})
    tabel(pd.DataFrame(data))


def halaman_buku_besar(conn, user):
    st.subheader("Buku besar")
    akun = conn.execute("SELECT kode, nama FROM akun ORDER BY kode").fetchall()
    peta = {a["kode"]: f"{a['kode']} - {a['nama']}" for a in akun}
    kode = st.selectbox("Akun", list(peta), format_func=peta.get)
    rows = buku_besar(conn, kode)
    if not rows:
        st.info("Belum ada mutasi pada akun ini.")
        return
    tabel(pd.DataFrame([{"Tanggal": r["tanggal"], "No. jurnal": r["no_jurnal"], "Keterangan": r["keterangan"],
                         "Debit": rupiah(r["debit"]) if r["debit"] else "",
                         "Kredit": rupiah(r["kredit"]) if r["kredit"] else "",
                         "Saldo": rupiah(r["saldo"])} for r in rows]))


def halaman_neraca_saldo(conn, user):
    st.subheader("Neraca saldo")
    sampai = st.date_input("Per tanggal", value=date.today())
    baris, td, tk = neraca_saldo(conn, sampai.isoformat())
    if not baris:
        st.info("Belum ada data.")
        return
    data = [{"Kode": k, "Akun": n, "Debit": rupiah(d) if d else "", "Kredit": rupiah(c) if c else ""}
            for k, n, d, c in baris]
    data.append({"Kode": "", "Akun": "TOTAL", "Debit": rupiah(td), "Kredit": rupiah(tk)})
    tabel(pd.DataFrame(data))
    if td == tk:
        st.success("Neraca saldo seimbang")
    else:
        st.error(f"Neraca saldo tidak seimbang, selisih {rupiah(abs(td - tk))}")
    sub, gl, ok = rekonsiliasi_tabungan(conn)
    st.markdown("#### Rekonsiliasi tabungan")
    st.write(f"Saldo seluruh rekening {rupiah(sub)} | Buku besar 2.1.01 {rupiah(gl)}")
    (st.success if ok else st.error)("Sesuai" if ok else "Tidak sesuai, periksa transaksi")
    sub2, gl2, ok2 = rekonsiliasi_deposito(conn)
    st.markdown("#### Rekonsiliasi deposito")
    st.write(f"Total nominal deposito aktif {rupiah(sub2)} | Buku besar 2.1.02 {rupiah(gl2)}")
    (st.success if ok2 else st.error)("Sesuai" if ok2 else "Tidak sesuai, periksa deposito")


def halaman_laporan(conn, user):
    st.subheader("Laporan keuangan")
    tab1, tab2 = st.tabs(["Posisi keuangan", "Laba rugi"])
    with tab1:
        sampai = st.date_input("Per tanggal", value=date.today(), key="lap_pos")
        p = posisi_keuangan(conn, sampai.isoformat())
        kiri, kanan = st.columns(2)
        with kiri:
            st.markdown("**Aset**")
            rows = [{"Akun": n, "Jumlah": rupiah(v)} for _, n, v in p["aset"]]
            rows.append({"Akun": "TOTAL ASET", "Jumlah": rupiah(p["total_aset"])})
            tabel(pd.DataFrame(rows))
        with kanan:
            st.markdown("**Liabilitas dan ekuitas**")
            rows = [{"Akun": n, "Jumlah": rupiah(v)} for _, n, v in p["liabilitas"]]
            rows.append({"Akun": "Total liabilitas", "Jumlah": rupiah(p["total_liabilitas"])})
            rows += [{"Akun": n, "Jumlah": rupiah(v)} for _, n, v in p["ekuitas"]]
            rows.append({"Akun": "Laba berjalan", "Jumlah": rupiah(p["laba_berjalan"])})
            rows.append({"Akun": "Total ekuitas", "Jumlah": rupiah(p["total_ekuitas"])})
            rows.append({"Akun": "TOTAL LIABILITAS DAN EKUITAS",
                         "Jumlah": rupiah(p["total_liabilitas"] + p["total_ekuitas"])})
            tabel(pd.DataFrame(rows))
        (st.success if p["seimbang"] else st.error)(
            "Aset = Liabilitas + Ekuitas" if p["seimbang"] else "Posisi keuangan tidak seimbang")
    with tab2:
        a, b = st.columns(2)
        dari = a.date_input("Dari tanggal", value=date(date.today().year, 1, 1), key="lr_dari")
        sampai = b.date_input("Sampai tanggal", value=date.today(), key="lr_sampai")
        lr = laba_rugi(conn, dari.isoformat(), sampai.isoformat())
        rows = [{"Akun": "PENDAPATAN", "Jumlah": ""}]
        rows += [{"Akun": n, "Jumlah": rupiah(v)} for _, n, v in lr["pendapatan"]]
        rows.append({"Akun": "Total pendapatan", "Jumlah": rupiah(lr["total_pendapatan"])})
        rows.append({"Akun": "BEBAN", "Jumlah": ""})
        rows += [{"Akun": n, "Jumlah": rupiah(v)} for _, n, v in lr["beban"]]
        rows.append({"Akun": "Total beban", "Jumlah": rupiah(lr["total_beban"])})
        rows.append({"Akun": "LABA (RUGI) BERSIH", "Jumlah": rupiah(lr["laba"])})
        tabel(pd.DataFrame(rows))


def halaman_kredit(conn, user):
    st.subheader("Kredit")
    init_kredit(conn)
    t1, t2, t3, t4 = st.tabs(["Pencairan", "Daftar dan jadwal", "Bayar angsuran", "Kolektibilitas dan CKPN"])
    uid = user["id"]

    with t1:
        label = opsi_rekening(conn)
        if not label:
            st.info("Belum ada rekening tabungan nasabah. Buka rekening dulu.")
        else:
            rek = st.selectbox("Rekening penerima", list(label), format_func=label.get, key="kr_rek")
            c1, c2, c3 = st.columns(3)
            plafon = c1.number_input("Plafon (Rp)", min_value=0, value=0, step=1_000_000, key="kr_plafon")
            bunga = c2.number_input("Bunga per tahun (%)", min_value=0.0, value=12.0, step=0.5, key="kr_bunga")
            tenor = c3.number_input("Tenor (bulan)", min_value=1, value=12, step=1, key="kr_tenor")
            metode = st.selectbox("Metode bunga", ["anuitas", "flat"], key="kr_metode")
            tgl = st.date_input("Tanggal pencairan", value=date.today(), key="kr_tgl")
            if plafon > 0:
                try:
                    jd = hitung_jadwal(int(plafon), float(bunga), int(tenor), metode, tgl)
                    st.markdown("**Pratinjau jadwal angsuran**")
                    tabel(pd.DataFrame([{"Ke": j["ke"], "Jatuh tempo": j["jatuh_tempo"],
                                         "Pokok": rupiah(j["pokok"]), "Bunga": rupiah(j["bunga"]),
                                         "Angsuran": rupiah(j["pokok"] + j["bunga"])} for j in jd]))
                except ValueError as e:
                    st.error(str(e))
            if st.button("Cairkan kredit"):
                try:
                    no = cairkan_kredit(conn, rek, int(plafon), float(bunga), int(tenor),
                                        metode, tgl.isoformat(), uid)
                    flash("ok", f"Kredit {no} dicairkan ke rekening {rek}")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()

    with t2:
        rows = conn.execute(
            """SELECT k.no_kredit, n.nama, k.plafon, k.bunga_tahunan, k.tenor, k.metode, k.tgl_cair, k.status,
                      (SELECT COALESCE(SUM(a.pokok),0) FROM angsuran a
                        WHERE a.kredit_id = k.id AND a.status='belum') AS sisa
               FROM kredit k JOIN rekening r ON r.no_rek = k.no_rek JOIN nasabah n ON n.cif = r.cif
               ORDER BY k.id""").fetchall()
        if not rows:
            st.info("Belum ada kredit.")
        else:
            tabel(pd.DataFrame([{"No. kredit": r["no_kredit"], "Debitur": r["nama"], "Plafon": rupiah(r["plafon"]),
                                 "Bunga": f"{r['bunga_tahunan']:g}%", "Tenor": r["tenor"], "Metode": r["metode"],
                                 "Tgl cair": r["tgl_cair"], "Status": r["status"],
                                 "Sisa pokok": rupiah(r["sisa"])} for r in rows]))
            peta = {r["no_kredit"]: f"{r['no_kredit']} - {r['nama']}" for r in rows}
            pilih = st.selectbox("Lihat jadwal angsuran", list(peta), format_func=peta.get, key="kr_jadwal")
            ang = conn.execute(
                """SELECT a.* FROM angsuran a JOIN kredit k ON k.id = a.kredit_id
                   WHERE k.no_kredit=? ORDER BY a.ke""", (pilih,)).fetchall()
            tabel(pd.DataFrame([{"Ke": a["ke"], "Jatuh tempo": a["jatuh_tempo"], "Pokok": rupiah(a["pokok"]),
                                 "Bunga": rupiah(a["bunga"]), "Angsuran": rupiah(a["pokok"] + a["bunga"]),
                                 "Status": a["status"], "Tgl bayar": a["tgl_bayar"] or ""} for a in ang]))

    with t3:
        aktif = conn.execute(
            """SELECT k.no_kredit, n.nama FROM kredit k JOIN rekening r ON r.no_rek = k.no_rek
               JOIN nasabah n ON n.cif = r.cif WHERE k.status='aktif' ORDER BY k.id""").fetchall()
        if not aktif:
            st.info("Tidak ada kredit aktif.")
        else:
            peta = {r["no_kredit"]: f"{r['no_kredit']} - {r['nama']}" for r in aktif}
            pilih = st.selectbox("Kredit", list(peta), format_func=peta.get, key="kr_bayar")
            a = conn.execute(
                """SELECT a.* FROM angsuran a JOIN kredit k ON k.id = a.kredit_id
                   WHERE k.no_kredit=? AND a.status='belum' ORDER BY a.ke LIMIT 1""", (pilih,)).fetchone()
            st.write(f"Angsuran ke-{a['ke']} jatuh tempo {a['jatuh_tempo']}: pokok {rupiah(a['pokok'])} "
                     f"+ bunga {rupiah(a['bunga'])} = **{rupiah(a['pokok'] + a['bunga'])}**")
            tgl = st.date_input("Tanggal pembayaran", value=date.today(), key="kr_bayar_tgl")
            if st.button("Debet angsuran dari tabungan"):
                try:
                    no = bayar_angsuran(conn, pilih, tgl.isoformat(), uid)
                    flash("ok", f"Angsuran dibayar, nomor jurnal {no}")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()

    with t4:
        tgl = st.date_input("Per tanggal", value=date.today(), key="kr_kol_tgl")
        iso = tgl.isoformat()
        h = hitung_ckpn(conn, iso)
        m1, m2, m3 = st.columns(3)
        m1.metric("CKPN dibutuhkan", rupiah(h["ckpn_dibutuhkan"]))
        m2.metric("Saldo CKPN saat ini", rupiah(h["saldo_ckpn"]))
        m3.metric("Selisih", rupiah(h["selisih"]))
        if h["rincian"]:
            tabel(pd.DataFrame([{"No. kredit": r["no_kredit"], "Sisa pokok": rupiah(r["sisa_pokok"]),
                                 "Hari tunggakan": r["hari_tunggakan"], "Kol": r["kolektibilitas"],
                                 "Keterangan": r["keterangan"], "Tarif": f"{r['tarif']:.0%}",
                                 "CKPN": rupiah(r["ckpn"])} for r in h["rincian"]]))
        st.caption("Tarif CKPN adalah asumsi penyederhanaan dari PSAK 71. Ubah di TARIF_CKPN pada kredit.py.")
        b1, b2 = st.columns(2)
        if b1.button("Jalankan akrual bunga s.d. tanggal ini"):
            try:
                jml, no = akrual_bunga(conn, iso, uid)
                flash("ok", f"Akrual bunga {rupiah(jml)} dicatat ({no})" if no else "Tidak ada bunga yang perlu diakrual")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()
        if b2.button("Bentuk atau sesuaikan CKPN"):
            try:
                no = bentuk_ckpn(conn, iso, uid)
                flash("ok", f"CKPN disesuaikan ({no})" if no else "CKPN sudah sesuai, tidak ada jurnal")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()


def halaman_akhir_bulan(conn, user):
    st.subheader("Proses akhir bulan")
    init_akhir_bulan(conn)
    uid = user["id"]
    t1, t2, t3, t4 = st.tabs(["Bunga dan biaya tabungan", "Tutup buku", "Jurnal pembalik", "Tutup tahun"])
    with t4:
        _tab_tutup_tahun(conn, user)

    with t1:
        tgl = st.date_input("Tanggal proses", value=date.today(), key="ab_tgl")
        periode = tgl.strftime("%Y-%m")
        st.caption(f"Periode {periode}. Parameter (asumsi): bunga {TARIF_BUNGA:.1%} per tahun untuk saldo minimal "
                   f"{rupiah(SALDO_MIN_BUNGA)}; pajak {TARIF_PAJAK:.0%} bila saldo di atas {rupiah(AMBANG_PAJAK)}; "
                   f"biaya administrasi {rupiah(BIAYA_ADMIN)} per rekening. Ubah di akhir_bulan.py.")
        rows = conn.execute(
            """SELECT p.no_rek, n.nama, p.saldo, p.bunga, p.pajak, p.admin FROM proses_bulanan p
               JOIN rekening r ON r.no_rek = p.no_rek JOIN nasabah n ON n.cif = r.cif
               WHERE p.periode=? ORDER BY p.no_rek""", (periode,)).fetchall()
        if rows:
            tabel(pd.DataFrame([{"No. rekening": r["no_rek"], "Nama": r["nama"], "Saldo saat proses": rupiah(r["saldo"]),
                                 "Bunga": rupiah(r["bunga"]), "Pajak": rupiah(r["pajak"]),
                                 "Administrasi": rupiah(r["admin"])} for r in rows]))
        else:
            st.info(f"Periode {periode} belum diproses.")
        if st.button("Jalankan proses bulanan"):
            try:
                h = proses_bulanan(conn, periode, tgl.isoformat(), uid)
                flash("ok", (f"Diproses {h['rekening']} rekening: bunga {rupiah(h['bunga'])}, pajak {rupiah(h['pajak'])}, "
                             f"administrasi {rupiah(h['admin'])}") if h else "Semua rekening sudah diproses untuk periode ini")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()

    with t2:
        ps = status_periode(conn)
        if not ps:
            st.info("Belum ada jurnal.")
        else:
            tabel(pd.DataFrame([{"Periode": x["periode"], "Jumlah jurnal": x["jurnal"], "Status": x["status"]} for x in ps]))
            st.caption("Tutup buku dilakukan berurutan dari periode terlama. Sebaiknya tutup suatu bulan setelah proses "
                       "bulanan dan akrual bunga selesai. Periode yang ditutup menolak jurnal baru.")
            terbuka = [x["periode"] for x in ps if x["status"] != "ditutup"]
            ditutup = [x["periode"] for x in ps if x["status"] == "ditutup"]
            c1, c2 = st.columns(2)
            with c1:
                if terbuka:
                    pil = st.selectbox("Periode yang ditutup", terbuka, key="ab_tutup")
                    if st.button("Tutup buku periode ini"):
                        try:
                            h = tutup_buku(conn, int(pil[5:]), int(pil[:4]), uid)
                            flash("ok", f"Periode {h['periode']} ditutup. Neraca saldo seimbang {rupiah(h['total_debit'])}")
                        except ValueError as e:
                            flash("err", str(e))
                        st.rerun()
            with c2:
                if user["peran"] == "supervisor" and ditutup:
                    pil2 = st.selectbox("Periode dibuka kembali", ditutup[::-1], key="ab_buka")
                    if st.button("Buka kembali periode"):
                        try:
                            buka_kembali(conn, int(pil2[5:]), int(pil2[:4]))
                            flash("ok", f"Periode {pil2} dibuka kembali")
                        except ValueError as e:
                            flash("err", str(e))
                        st.rerun()
                elif ditutup:
                    st.caption("Hanya supervisor yang dapat membuka kembali periode.")

    with t3:
        ver = st.session_state.get("ver_ab", 0)
        terkendali = ",".join("?" * len(AKUN_TERKENDALI))
        daftar = conn.execute(
            f"""SELECT j.no_jurnal, j.tanggal, j.keterangan, SUM(d.debit) AS nominal
                FROM jurnal j JOIN jurnal_detail d ON d.jurnal_id = j.id
                WHERE j.no_jurnal NOT IN (SELECT no_jurnal_asal FROM pembalikan)
                  AND j.no_jurnal NOT IN (SELECT no_jurnal_balik FROM pembalikan)
                  AND j.id NOT IN (SELECT jurnal_id FROM jurnal_detail WHERE kode_akun IN ({terkendali}))
                GROUP BY j.id ORDER BY j.id DESC LIMIT 50""", tuple(AKUN_TERKENDALI)).fetchall()
        st.caption("Jurnal tidak dihapus, tetapi dikoreksi dengan jurnal lawan. Jurnal yang memakai akun tabungan "
                   "dan kredit tidak muncul di sini karena saldo rekening dan jadwal angsuran harus ikut berubah.")
        if not daftar:
            st.info("Tidak ada jurnal yang bisa dibalik.")
        else:
            peta = {r["no_jurnal"]: f"{r['no_jurnal']} | {r['tanggal']} | {r['keterangan']} | {rupiah(r['nominal'])}"
                    for r in daftar}
            pil = st.selectbox("Jurnal yang dikoreksi", list(peta), format_func=peta.get, key=f"ab_balik_{ver}")
            det = conn.execute(
                """SELECT d.kode_akun, a.nama, d.debit, d.kredit FROM jurnal_detail d
                   JOIN jurnal j ON j.id = d.jurnal_id JOIN akun a ON a.kode = d.kode_akun
                   WHERE j.no_jurnal=? ORDER BY d.id""", (pil,)).fetchall()
            tabel(pd.DataFrame([{"Kode": d["kode_akun"], "Akun": d["nama"],
                                 "Debit": rupiah(d["debit"]) if d["debit"] else "",
                                 "Kredit": rupiah(d["kredit"]) if d["kredit"] else ""} for d in det]))
            alasan = st.text_input("Alasan pembalikan", key=f"ab_alasan_{ver}")
            tgl = st.date_input("Tanggal jurnal pembalik", value=date.today(), key=f"ab_balik_tgl_{ver}")
            if st.button("Buat jurnal pembalik"):
                try:
                    no = balik_jurnal(conn, pil, alasan, tgl.isoformat(), uid)
                    st.session_state["ver_ab"] = ver + 1
                    flash("ok", f"{pil} dibalik dengan jurnal {no}")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()
        riwayat = conn.execute("SELECT * FROM pembalikan ORDER BY id DESC").fetchall()
        if riwayat:
            st.markdown("#### Riwayat pembalikan")
            tabel(pd.DataFrame([{"Tanggal": r["tanggal"], "Jurnal asal": r["no_jurnal_asal"],
                                 "Jurnal pembalik": r["no_jurnal_balik"], "Alasan": r["alasan"]} for r in riwayat]))


def halaman_persetujuan(conn, user):
    st.subheader("Persetujuan (maker-checker)")
    init_persetujuan(conn)
    supervisor = user["peran"] == "supervisor"
    ver = st.session_state.get("ver_ps", 0)

    if supervisor:
        st.markdown("#### Menunggu persetujuan")
        menunggu = daftar_pengajuan(conn, "menunggu")
        if not menunggu:
            st.info("Tidak ada pengajuan yang menunggu.")
        else:
            peta = {r["id"]: f"#{r['id']} | {r['dibuat']} | {r['maker']} | {r['ringkasan']}" for r in menunggu}
            pil = st.selectbox("Pengajuan", list(peta), format_func=peta.get, key=f"ps_pil_{ver}")
            r = next(x for x in menunggu if x["id"] == pil)
            p = json.loads(r["payload"])
            if r["jenis"] == "jurnal_manual":
                st.write(f"Tanggal {p['tanggal']} | {p['keterangan']}")
                tabel(pd.DataFrame([{"Akun": b[0], "Debit": rupiah(b[1]) if b[1] else "",
                                     "Kredit": rupiah(b[2]) if b[2] else ""} for b in p["baris"]]))
            else:
                st.write(f"Tanggal {p['tanggal']} | rekening {p['no_rek']}"
                         + (f" ke {p['tujuan']}" if p.get("tujuan") else "") + f" | {rupiah(p['jumlah'])}")
            catatan = st.text_input("Catatan (wajib bila menolak)", key=f"ps_cat_{ver}")
            b1, b2 = st.columns(2)
            if b1.button("Setujui"):
                try:
                    no = setujui(conn, pil, user)
                    st.session_state["ver_ps"] = ver + 1
                    flash("ok", f"Pengajuan #{pil} disetujui dan dicatat sebagai {no}")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()
            if b2.button("Tolak"):
                try:
                    tolak(conn, pil, user, catatan)
                    st.session_state["ver_ps"] = ver + 1
                    flash("ok", f"Pengajuan #{pil} ditolak")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()

    st.markdown("#### Riwayat pengajuan" if supervisor else "#### Pengajuan saya")
    rows = daftar_pengajuan(conn, None, None if supervisor else user["id"])
    if not rows:
        st.caption("Belum ada pengajuan.")
    else:
        tabel(pd.DataFrame([{"No": r["id"], "Waktu": r["dibuat"], "Pembuat": r["maker"], "Pengajuan": r["ringkasan"],
                             "Status": r["status"], "Penyetuju": r["checker"] or "", "Catatan": r["catatan"] or "",
                             "No. jurnal": r["no_jurnal"] or ""} for r in rows]))


def _tab_tutup_tahun(conn, user):
    st.caption("Jurnal penutup memindahkan saldo seluruh pendapatan dan beban setahun ke 3.2.01 Laba ditahan, "
               "dicatat tanggal 31 Desember. Laporan laba rugi setahun tidak berubah. Lakukan di akhir tahun, "
               "setelah semua bulan ditutup. Hanya supervisor.")
    tahun = st.number_input("Tahun", min_value=2000, max_value=2100, value=date.today().year, step=1, key="tt_tahun")
    if user["peran"] != "supervisor":
        st.info("Hanya supervisor yang dapat membuat jurnal penutup.")
    elif st.button("Buat jurnal penutup tahun ini"):
        try:
            init_lanjutan(conn)
            h = jurnal_penutup(conn, int(tahun), user["id"])
            flash("ok", f"Jurnal penutup {h['no_jurnal']} dibuat. Laba {rupiah(h['laba'])} dipindahkan ke Laba ditahan")
        except ValueError as e:
            flash("err", str(e))
        st.rerun()
    init_lanjutan(conn)
    riwayat = conn.execute("SELECT * FROM penutupan_tahun ORDER BY tahun DESC").fetchall()
    if riwayat:
        tabel(pd.DataFrame([{"Tahun": r["tahun"], "No. jurnal": r["no_jurnal"], "Laba dipindahkan": rupiah(r["laba"])}
                            for r in riwayat]))


def halaman_deposito(conn, user):
    st.subheader("Deposito")
    init_deposito(conn)
    uid = user["id"]
    t1, t2, t3 = st.tabs(["Penempatan", "Daftar deposito", "Akrual dan jatuh tempo"])
    with t1:
        label = opsi_rekening(conn)
        if not label:
            st.info("Belum ada rekening tabungan.")
        else:
            rek = st.selectbox("Sumber dana (rekening tabungan)", list(label), format_func=label.get, key="dp_rek")
            c1, c2, c3 = st.columns(3)
            nominal = c1.number_input("Nominal (Rp)", min_value=0, value=0, step=1_000_000, key="dp_nom")
            bunga = c2.number_input("Bunga per tahun (%)", min_value=0.0, value=5.0, step=0.25, key="dp_bunga")
            tenor = c3.selectbox("Tenor (bulan)", [1, 3, 6, 12, 24], index=1, key="dp_tenor")
            aro = st.checkbox("Perpanjang otomatis (ARO)", key="dp_aro")
            tgl = st.date_input("Tanggal penempatan", value=date.today(), key="dp_tgl")
            if nominal > 0:
                d = {"nominal": int(nominal), "bunga_tahunan": float(bunga), "tenor": int(tenor)}
                b = _bunga_periode(d)
                st.caption(f"Estimasi bunga per periode {rupiah(b)}, pajak {rupiah(_pajak(int(nominal), b))}, "
                           f"bunga bersih {rupiah(b - _pajak(int(nominal), b))}.")
            if st.button("Tempatkan deposito"):
                try:
                    no = tempatkan_deposito(conn, rek, int(nominal), float(bunga), int(tenor), aro, tgl.isoformat(), uid)
                    flash("ok", f"Deposito {no} berhasil ditempatkan")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()
    with t2:
        rows = daftar_deposito(conn)
        if not rows:
            st.info("Belum ada deposito.")
        else:
            tabel(pd.DataFrame([{"No. bilyet": r["no_bilyet"], "Nasabah": r["nama"], "Nominal": rupiah(r["nominal"]),
                                 "Bunga": f"{r['bunga_tahunan']:g}%", "Tenor": r["tenor"], "Mulai": r["tgl_mulai"],
                                 "Jatuh tempo": r["jatuh_tempo"], "ARO": "ya" if r["aro"] else "tidak",
                                 "Perpanjangan": r["perpanjangan"], "Status": r["status"]} for r in rows]))
    with t3:
        tgl = st.date_input("Per tanggal", value=date.today(), key="dp_proses_tgl")
        st.caption("Akrual mengakui beban bunga yang sudah berjalan. Proses jatuh tempo mencairkan deposito, "
                   "atau memperpanjangnya bila ARO (bunga bersih dibayar ke tabungan).")
        b1, b2 = st.columns(2)
        if b1.button("Jalankan akrual bunga deposito"):
            try:
                jml, no = akrual_deposito(conn, tgl.isoformat(), uid)
                flash("ok", f"Akrual {rupiah(jml)} dicatat ({no})" if no else "Tidak ada bunga yang perlu diakrual")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()
        if b2.button("Proses jatuh tempo"):
            try:
                hasil = proses_jatuh_tempo(conn, tgl.isoformat(), uid)
                flash("ok", "; ".join(f"{h['no_bilyet']} {h['aksi']} (bunga {rupiah(h['bunga'])}, pajak {rupiah(h['pajak'])})"
                                      for h in hasil) if hasil else "Tidak ada deposito yang jatuh tempo")
            except ValueError as e:
                flash("err", str(e))
            st.rerun()


def halaman_lanjutan(conn, user):
    st.subheader("Laporan lanjutan")
    a, b = st.columns(2)
    dari = a.date_input("Dari tanggal", value=date(date.today().year, 1, 1), key="ln_dari")
    sampai = b.date_input("Sampai tanggal", value=date.today(), key="ln_sampai")
    d, s_ = dari.isoformat(), sampai.isoformat()
    t1, t2, t3, t4 = st.tabs(["Rasio keuangan", "Arus kas", "Perubahan ekuitas", "Ekspor PDF dan Excel"])
    with t1:
        rs = rasio(conn, s_)["baris"]
        tabel(pd.DataFrame([{"Rasio": r["nama"], "Nilai": r["teks"], "Acuan umum": r["acuan"], "Status": r["status"]}
                            for r in rs]))
        st.caption("Rasio memakai saldo akhir (bukan rata-rata) dan disetahunkan dari awal tahun. Acuan hanyalah patokan "
                   "umum, cocokkan dengan materi kuliah. CAR belum dihitung.")
    with t2:
        ak = arus_kas(conn, d, s_)
        rows = [{"Keterangan": "Kas dan setara kas awal periode", "Jumlah": rupiah(ak["awal"])}]
        for judul, kunci in (("Aktivitas operasional", "operasional"), ("Aktivitas investasi", "investasi"),
                             ("Aktivitas pendanaan", "pendanaan")):
            rows.append({"Keterangan": judul.upper(), "Jumlah": ""})
            rows += [{"Keterangan": l, "Jumlah": rupiah(x)} for l, x in ak[kunci]]
            rows.append({"Keterangan": f"Total {kunci}", "Jumlah": rupiah(ak[f"total_{kunci}"])})
        rows.append({"Keterangan": "Kenaikan (penurunan) kas bersih", "Jumlah": rupiah(ak["kenaikan"])})
        rows.append({"Keterangan": "KAS DAN SETARA KAS AKHIR", "Jumlah": rupiah(ak["akhir"])})
        tabel(pd.DataFrame(rows))
        (st.success if ak["cocok"] else st.error)(
            "Kas akhir sama dengan saldo buku besar (Kas + Giro pada BI)" if ak["cocok"] else "Kas akhir tidak cocok dengan buku besar")
    with t3:
        pe = perubahan_ekuitas(conn, d, s_)
        tabel(pd.DataFrame([{"Keterangan": "Ekuitas awal periode", "Jumlah": rupiah(pe["awal"])},
                            {"Keterangan": "Penambahan modal", "Jumlah": rupiah(pe["tambahan_modal"])},
                            {"Keterangan": "Laba (rugi) periode berjalan", "Jumlah": rupiah(pe["laba"])},
                            {"Keterangan": "Penyesuaian lainnya", "Jumlah": rupiah(pe["lainnya"])},
                            {"Keterangan": "EKUITAS AKHIR PERIODE", "Jumlah": rupiah(pe["akhir"])}]))
    with t4:
        st.write("Berkas berisi posisi keuangan, laba rugi, arus kas, perubahan ekuitas, neraca saldo, dan rasio.")
        e1, e2 = st.columns(2)
        e1.download_button("Unduh Excel", data=excel_laporan(conn, d, s_), file_name=f"laporan_bnn_{s_}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        e2.download_button("Unduh PDF", data=pdf_laporan(conn, d, s_), file_name=f"laporan_bnn_{s_}.pdf",
                           mime="application/pdf")


def halaman_layanan(conn, user):
    st.subheader("Layanan nasabah")
    t1, t2, t3, t4 = st.tabs(["Pendaftaran dan rekening baru", "Cari dan ubah data", "Status rekening",
                              "Ringkasan nasabah"])
    nas = conn.execute("SELECT cif, nama FROM nasabah ORDER BY cif").fetchall()
    peta = {r["cif"]: f"{r['cif']} - {r['nama']}" for r in nas}

    with t1:
        kiri, kanan = st.columns(2)
        with kiri:
            st.markdown("**Daftarkan nasabah baru**")
            with st.form("cs_daftar", clear_on_submit=True):
                nama = st.text_input("Nama lengkap sesuai KTP")
                nik = st.text_input("NIK (16 digit)")
                alamat = st.text_input("Alamat")
                kirim = st.form_submit_button("Simpan nasabah")
            if kirim:
                try:
                    flash("ok", f"Nasabah terdaftar dengan nomor {daftarkan_nasabah(conn, nama, nik, alamat, user)}")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()
        with kanan:
            st.markdown("**Buka rekening tabungan**")
            if not peta:
                st.info("Belum ada nasabah.")
            else:
                with st.form("cs_rekening", clear_on_submit=True):
                    cif = st.selectbox("Nasabah", list(peta), format_func=peta.get)
                    kirim = st.form_submit_button("Buka rekening")
                st.caption("Rekening dibuka dengan saldo nol. Setoran awal dilakukan di teller.")
                if kirim:
                    try:
                        flash("ok", f"Rekening {buka_rekening_baru(conn, cif, user)} berhasil dibuka")
                    except ValueError as e:
                        flash("err", str(e))
                    st.rerun()

    with t2:
        q = st.text_input("Cari (nomor CIF, nama, NIK, atau nomor rekening)", key="cs_cari")
        hasil = cari_nasabah(conn, q) if q.strip() else []
        if q.strip() and not hasil:
            st.info("Nasabah tidak ditemukan.")
        elif hasil:
            tabel(pd.DataFrame([{"CIF": r["cif"], "Nama": r["nama"], "NIK": r["nik"] or "", "Alamat": r["alamat"] or "",
                                 "Jumlah rekening": r["jumlah_rekening"]} for r in hasil]))
            pilih = st.selectbox("Pilih nasabah untuk diubah", [r["cif"] for r in hasil],
                                 format_func=lambda c: next(f"{x['cif']} - {x['nama']}" for x in hasil if x["cif"] == c),
                                 key="cs_pilih")
            n = next(r for r in hasil if r["cif"] == pilih)
            with st.form(f"cs_ubah_{pilih}"):
                nama = st.text_input("Nama", value=n["nama"])
                nik = st.text_input("NIK (16 digit)", value=n["nik"] or "")
                alamat = st.text_input("Alamat", value=n["alamat"] or "")
                kirim = st.form_submit_button("Simpan perubahan")
            if kirim:
                try:
                    ubah_nasabah(conn, pilih, nama, nik, alamat, user)
                    flash("ok", f"Data {pilih} diperbarui")
                except ValueError as e:
                    flash("err", str(e))
                st.rerun()

    with t3:
        rek = conn.execute("""SELECT r.no_rek, n.nama, r.saldo, r.status FROM rekening r
                              JOIN nasabah n ON n.cif = r.cif ORDER BY r.no_rek""").fetchall()
        if not rek:
            st.info("Belum ada rekening.")
        else:
            pr = {r["no_rek"]: f"{r['no_rek']} - {r['nama']} | {r['status']} | saldo {rupiah(r['saldo'])}" for r in rek}
            no = st.selectbox("Rekening", list(pr), format_func=pr.get, key="cs_status_rek")
            saat_ini = next(r["status"] for r in rek if r["no_rek"] == no)
            if saat_ini == "tutup":
                st.info("Rekening ini sudah ditutup dan tidak dapat diubah lagi.")
            else:
                baru = st.selectbox("Status baru", [x for x in ("aktif", "diblokir", "tutup") if x != saat_ini],
                                    key=f"cs_baru_{no}")
                alasan = st.text_input("Alasan (wajib)", key=f"cs_alasan_{no}")
                st.caption("Rekening diblokir tidak bisa bertransaksi, termasuk debet angsuran. Penutupan hanya bila "
                           "saldo nol dan tidak ada kredit atau deposito aktif, serta tidak dapat dibatalkan.")
                if st.button("Ubah status rekening"):
                    try:
                        ubah_status_rekening(conn, no, baru, alasan, user)
                        flash("ok", f"Status rekening {no} menjadi {baru}")
                    except ValueError as e:
                        flash("err", str(e))
                    st.rerun()

    with t4:
        if not peta:
            st.info("Belum ada nasabah.")
        else:
            cif = st.selectbox("Nasabah", list(peta), format_func=peta.get, key="cs_ringkas")
            r = ringkas_nasabah(conn, cif)
            st.markdown("**Rekening**")
            tabel(pd.DataFrame([{"No. rekening": x["no_rek"], "Jenis": x["jenis"], "Saldo": rupiah(x["saldo"]),
                                 "Status": x["status"]} for x in r["rekening"]]))
            if r["kredit"]:
                st.markdown("**Kredit**")
                tabel(pd.DataFrame([{"No. kredit": x["no_kredit"], "Plafon": rupiah(x["plafon"]),
                                     "Sisa pokok": rupiah(x["sisa"]), "Status": x["status"]} for x in r["kredit"]]))
            if r["deposito"]:
                st.markdown("**Deposito**")
                tabel(pd.DataFrame([{"No. bilyet": x["no_bilyet"], "Nominal": rupiah(x["nominal"]),
                                     "Jatuh tempo": x["jatuh_tempo"], "Status": x["status"]} for x in r["deposito"]]))
    riwayat = riwayat_layanan(conn)
    if riwayat:
        st.markdown("#### Riwayat layanan terakhir")
        tabel(pd.DataFrame([{"Waktu": x["waktu"], "Petugas": x["username"], "Tindakan": x["aksi"],
                             "Keterangan": x["keterangan"]} for x in riwayat]))


def halaman_akun_saya(conn, user):
    st.subheader("Akun saya")
    st.write(f"Masuk sebagai **{user['username']}** (peran: {user['peran']})")
    with st.form("form_ganti_pw", clear_on_submit=True):
        lama = st.text_input("Password lama", type="password")
        baru = st.text_input("Password baru (minimal 8 karakter)", type="password")
        ulang = st.text_input("Ulangi password baru", type="password")
        kirim = st.form_submit_button("Ganti password")
    if kirim:
        try:
            if baru != ulang:
                raise ValueError("Password baru dan ulangannya tidak sama")
            ganti_password(conn, user["id"], lama, baru)
            flash("ok", "Password berhasil diganti")
        except ValueError as e:
            flash("err", str(e))
        st.rerun()


def halaman_pengguna(conn, user):
    st.subheader("Kelola pengguna")
    if user["peran"] != "supervisor":
        st.error("Hanya supervisor yang boleh membuka halaman ini.")
        return
    with st.form("form_user", clear_on_submit=True):
        u = st.text_input("Username")
        p = st.text_input("Password awal (minimal 8 karakter)", type="password")
        r = st.selectbox("Peran", list(PERAN))
        kirim = st.form_submit_button("Tambah pengguna")
    if kirim:
        try:
            tambah_user(conn, u, p, r)
            flash("ok", f"Pengguna {u.strip().lower()} ditambahkan")
        except ValueError as e:
            flash("err", str(e))
        st.rerun()
    tabel(pd.DataFrame([{"Username": x["username"], "Peran": x["peran"]} for x in daftar_user(conn)]))


# (kunci, bagian menu, judul, ikon, fungsi)
DAFTAR = [
    ("dashboard", "Operasional", "Dashboard", ":material/dashboard:", halaman_dashboard),
    ("nasabah", "Operasional", "Nasabah dan rekening", ":material/group:", halaman_nasabah),
    ("layanan", "Operasional", "Layanan nasabah", ":material/support_agent:", halaman_layanan),
    ("transaksi", "Operasional", "Transaksi teller", ":material/swap_horiz:", halaman_transaksi),
    ("persetujuan", "Operasional", "Persetujuan", ":material/fact_check:", halaman_persetujuan),
    ("jurnal_manual", "Pembukuan", "Jurnal manual", ":material/edit_note:", halaman_jurnal_manual),
    ("jurnal_umum", "Pembukuan", "Jurnal umum", ":material/menu_book:", halaman_jurnal_umum),
    ("buku_besar", "Pembukuan", "Buku besar", ":material/auto_stories:", halaman_buku_besar),
    ("akhir_bulan", "Pembukuan", "Proses akhir bulan", ":material/event_available:", halaman_akhir_bulan),
    ("kredit", "Kredit dan deposito", "Kredit", ":material/request_quote:", halaman_kredit),
    ("deposito", "Kredit dan deposito", "Deposito", ":material/savings:", halaman_deposito),
    ("neraca", "Laporan", "Neraca saldo", ":material/balance:", halaman_neraca_saldo),
    ("laporan", "Laporan", "Laporan keuangan", ":material/description:", halaman_laporan),
    ("lanjutan", "Laporan", "Laporan lanjutan", ":material/analytics:", halaman_lanjutan),
    ("akun", "Pengaturan", "Akun saya", ":material/account_circle:", halaman_akun_saya),
    ("pengguna", "Pengaturan", "Kelola pengguna", ":material/admin_panel_settings:", halaman_pengguna),
]
HALAMAN = {k: f for k, _, _, _, f in DAFTAR}

AKSES = {
    "teller": {"dashboard", "nasabah", "transaksi", "persetujuan", "akun"},
    "cs": {"dashboard", "layanan", "akun"},
    "akuntan": {"dashboard", "persetujuan", "jurnal_manual", "jurnal_umum", "buku_besar", "akhir_bulan", "kredit", "deposito", "neraca", "laporan", "lanjutan", "akun"},
    "supervisor": {k for k, *_ in DAFTAR},
}


def bungkus(fn):
    def _jalan():
        conn = get_conn()
        try:
            fn(conn, st.session_state["user"])
        finally:
            conn.close()
    return _jalan


def halaman_login():
    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
    _, tengah, _ = st.columns([1, 1.1, 1])
    with tengah:
        st.markdown(f'<div class="bnn-login"><img src="{PITA_URI}" width="140"/><h1>BNN</h1>'
                    f'<p>Bank Neneng Nopitasari</p></div>', unsafe_allow_html=True)
        with st.form("form_login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            masuk = st.form_submit_button("Masuk")
        if masuk:
            gagal = st.session_state.get("gagal", 0)
            if gagal >= 5:
                st.error("Terlalu banyak percobaan gagal. Muat ulang halaman untuk mencoba lagi.")
            else:
                conn = get_conn()
                try:
                    st.session_state["user"] = login(conn, username, password)
                    st.session_state["splash"] = True
                    st.session_state["gagal"] = 0
                    st.rerun()
                except ValueError as e:
                    st.session_state["gagal"] = gagal + 1
                    st.error(str(e))
                finally:
                    conn.close()
        with st.expander("Akun demo"):
            st.write("Username: supervisor, akuntan, teller, atau cs. Password awal: Bnn@2026. "
                     "Ganti lewat menu Akun saya setelah masuk.")


def main():
    st.set_page_config(page_title="BNN - Bank Neneng Nopitasari", page_icon="🎀", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_db()
    conn = get_conn()
    seed_users(conn)
    init_kredit(conn)
    init_akhir_bulan(conn)
    init_persetujuan(conn)
    init_deposito(conn)
    init_lanjutan(conn)
    conn.close()

    user = st.session_state.get("user")
    if not user:
        halaman_login()
        return
    if st.session_state.pop("splash", False):
        splash()

    bagian = {}
    for kunci, grup, judul, ikon, fn in DAFTAR:
        if kunci in AKSES[user["peran"]]:
            kw = {} if kunci == "dashboard" else {"url_path": kunci}
            bagian.setdefault(grup, []).append(
                st.Page(bungkus(fn), title=judul, icon=ikon, default=(kunci == "dashboard"), **kw))
    pg = st.navigation(bagian)

    with st.sidebar:
        st.divider()
        st.caption(f"Masuk sebagai **{user['username']}** ({user['peran']})")
        if user["peran"] == "supervisor" and st.button("Isi data contoh"):
            c = get_conn()
            try:
                flash("ok", isi_data_contoh(c))
            except ValueError as e:
                flash("err", str(e))
            finally:
                c.close()
            st.rerun()
        if st.button("Keluar"):
            st.session_state.clear()
            st.rerun()

    st.markdown(f'<div class="bnn-top"><div><b>BNN</b><span>Bank Neneng Nopitasari</span></div>'
                f'<div style="font-size:13px">Petugas: {user["username"]} | Peran: {PERAN_LABEL.get(user["peran"], user["peran"].title())}</div></div>',
                unsafe_allow_html=True)
    tampil_flash()
    pg.run()


main()
