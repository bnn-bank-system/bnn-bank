"""Ekspor laporan BNN ke Excel (.xlsx) dan PDF."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from akuntansi import neraca_saldo, rupiah
from lanjutan import arus_kas, perubahan_ekuitas, rasio
from laporan import laba_rugi, posisi_keuangan

ROSE, BLUSH, DEEP = "B76E79", "F7ECEC", "5E3A41"


def susun(conn, dari, sampai):
    """Daftar bagian: (judul, header, baris). Angka mentah (int) akan diformat sesuai tujuan."""
    pk, lr = posisi_keuangan(conn, sampai), laba_rugi(conn, dari, sampai)
    ak, pe, rs = arus_kas(conn, dari, sampai), perubahan_ekuitas(conn, dari, sampai), rasio(conn, sampai)
    baris, td, tk = neraca_saldo(conn, sampai)

    b_pk = [["ASET", None]] + [[n, v] for _, n, v in pk["aset"]] + [["Total aset", pk["total_aset"]], ["LIABILITAS", None]]
    b_pk += [[n, v] for _, n, v in pk["liabilitas"]] + [["Total liabilitas", pk["total_liabilitas"]], ["EKUITAS", None]]
    b_pk += [[n, v] for _, n, v in pk["ekuitas"]] + [["Laba berjalan", pk["laba_berjalan"]],
             ["Total ekuitas", pk["total_ekuitas"]],
             ["TOTAL LIABILITAS DAN EKUITAS", pk["total_liabilitas"] + pk["total_ekuitas"]]]

    b_lr = [["PENDAPATAN", None]] + [[n, v] for _, n, v in lr["pendapatan"]] + [["Total pendapatan", lr["total_pendapatan"]],
            ["BEBAN", None]] + [[n, v] for _, n, v in lr["beban"]] + [["Total beban", lr["total_beban"]],
            ["LABA (RUGI) BERSIH", lr["laba"]]]

    b_ak = [["Kas dan setara kas awal periode", ak["awal"]]]
    for judul, kunci in (("ARUS KAS DARI AKTIVITAS OPERASIONAL", "operasional"),
                         ("ARUS KAS DARI AKTIVITAS INVESTASI", "investasi"),
                         ("ARUS KAS DARI AKTIVITAS PENDANAAN", "pendanaan")):
        b_ak += [[judul, None]] + [[l, a] for l, a in ak[kunci]] + [[f"Total {kunci}", ak[f"total_{kunci}"]]]
    b_ak += [["Kenaikan (penurunan) kas bersih", ak["kenaikan"]], ["Kas dan setara kas akhir periode", ak["akhir"]]]

    b_pe = [["Ekuitas awal periode", pe["awal"]], ["Penambahan modal", pe["tambahan_modal"]],
            ["Laba (rugi) periode berjalan", pe["laba"]], ["Penyesuaian lainnya", pe["lainnya"]],
            ["Ekuitas akhir periode", pe["akhir"]]]

    b_ns = [[k, n, d, c] for k, n, d, c in baris] + [["", "TOTAL", td, tk]]
    b_rs = [[r["nama"], r["teks"], r["acuan"], r["status"]] for r in rs["baris"]]
    return [
        (f"Laporan Posisi Keuangan per {sampai}", ["Akun", "Jumlah (Rp)"], b_pk),
        (f"Laporan Laba Rugi {dari} s.d. {sampai}", ["Akun", "Jumlah (Rp)"], b_lr),
        (f"Laporan Arus Kas {dari} s.d. {sampai}", ["Keterangan", "Jumlah (Rp)"], b_ak),
        (f"Laporan Perubahan Ekuitas {dari} s.d. {sampai}", ["Keterangan", "Jumlah (Rp)"], b_pe),
        (f"Neraca Saldo per {sampai}", ["Kode", "Akun", "Debit (Rp)", "Kredit (Rp)"], b_ns),
        (f"Rasio Keuangan per {sampai}", ["Rasio", "Nilai", "Acuan umum", "Status"], b_rs),
    ]


def _tebal(label):
    return isinstance(label, str) and (label.isupper() or label.startswith("Total") or label.startswith("Kenaikan (penurunan) kas")
                                       or label.startswith("Ekuitas akhir") or label.startswith("Kas dan setara kas akhir"))


def excel_laporan(conn, dari, sampai):
    wb = Workbook()
    wb.remove(wb.active)
    isi = PatternFill("solid", fgColor=ROSE)
    for judul, header, baris in susun(conn, dari, sampai):
        ws = wb.create_sheet(judul.split(" per ")[0].split(" 20")[0][:31])
        ws["A1"] = "BNN - Bank Neneng Nopitasari"; ws["A1"].font = Font(bold=True, size=14, color=ROSE)
        ws["A2"] = judul; ws["A2"].font = Font(bold=True, color=DEEP)
        for i, h in enumerate(header, 1):
            c = ws.cell(row=4, column=i, value=h)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), isi
        for r, b in enumerate(baris, 5):
            for i, v in enumerate(b, 1):
                c = ws.cell(row=r, column=i, value=v)
                if isinstance(v, int):
                    c.number_format = "#,##0"; c.alignment = Alignment(horizontal="right")
                if _tebal(b[0] if len(header) == 2 else b[1]):
                    c.font = Font(bold=True, color=DEEP)
        for i, w in enumerate([46, 22, 22, 22][:len(header)] if len(header) > 2 else [48, 22], 1):
            ws.column_dimensions[chr(64 + i)].width = w
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf_laporan(conn, dari, sampai):
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#" + ROSE), spaceBefore=10, spaceAfter=6)
    kecil = ParagraphStyle("k", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#" + DEEP))
    isi = []
    isi += [Paragraph("BNN - Bank Neneng Nopitasari", ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, leading=24,
                                                                    textColor=colors.HexColor("#" + ROSE))),
            Paragraph(f"Laporan keuangan periode {dari} s.d. {sampai} | dicetak {date.today().isoformat()}", kecil),
            Spacer(1, 8)]
    for judul, header, baris in susun(conn, dari, sampai):
        data = [header]
        for b in baris:
            data.append([rupiah(v) if isinstance(v, int) else ("" if v is None else str(v)) for v in b])
        lebar = [10.5 * cm, 5.5 * cm] if len(header) == 2 else ([2 * cm, 6.5 * cm, 3.9 * cm, 3.9 * cm] if len(header) == 4 and header[0] == "Kode" else [6 * cm, 3 * cm, 4.5 * cm, 2.5 * cm])
        t = Table(data, colWidths=lebar, repeatRows=1)
        gaya = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + ROSE)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8B4B8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#" + BLUSH)])]
        if len(header) == 2:
            gaya.append(("ALIGN", (1, 0), (1, -1), "RIGHT"))
        elif header[0] == "Kode":
            gaya.append(("ALIGN", (2, 0), (3, -1), "RIGHT"))
        for i, b in enumerate(baris, 1):
            if _tebal(b[0] if len(header) == 2 else b[1]):
                gaya.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        t.setStyle(TableStyle(gaya))
        isi += [Paragraph(judul, h1), t]
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                      title="Laporan Keuangan BNN", author="BNN").build(isi)
    return buf.getvalue()
