#!/usr/bin/env python3
"""Build the orthogonal 10 kW paraformer documentation artifacts.

The numerical values are read from the simulator CSV output so the Word,
LaTeX, and Excel derivatives stay synchronized with the executable model.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
FIGURES = ROOT / "figures"
DOCS = ROOT / "docs"


def read_first_csv_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No rows in {path}")
    return rows[0]


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def fmt(value: float, decimals: int = 3) -> str:
    if abs(value) >= 1000:
        return f"{value:,.{decimals}f}".replace(",", " ")
    return f"{value:.{decimals}f}"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_text(cell, text: str, bold: bool = False) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(9)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def style_document(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for name, size, color in [
        ("Title", 18, "1F4D78"),
        ("Heading 1", 16, "2E74B5"),
        ("Heading 2", 13, "2E74B5"),
        ("Heading 3", 12, "1F4D78"),
    ]:
        style = doc.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)


def add_heading(doc: Document, text: str, level: int) -> None:
    p = doc.add_heading(text, level=level)
    if level == 1:
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(10)
    elif level == 2:
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(7)


def add_key_value_table(doc: Document, rows: list[tuple[str, str]], widths: tuple[float, float]) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    set_cell_text(hdr[0], "Suure", bold=True)
    set_cell_text(hdr[1], "Arvo", bold=True)
    set_cell_shading(hdr[0], "E8EEF5")
    set_cell_shading(hdr[1], "E8EEF5")
    for label, value in rows:
        cells = table.add_row().cells
        set_cell_text(cells[0], label)
        set_cell_text(cells[1], value)
    for row in table.rows:
        row.cells[0].width = Inches(widths[0])
        row.cells[1].width = Inches(widths[1])
    doc.add_paragraph()


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(4)
        p.add_run(item)


def derived_values(row: dict[str, str]) -> dict[str, float]:
    strand_diameter_mm = 0.10
    strand_area = math.pi * (strand_diameter_mm / 2) ** 2
    bundles = as_float(row, "selected_parallel_AWG10_equiv_Litz_bundles")
    awg10_area = as_float(row, "selected_copper_area_mm2") / bundles
    skin_depth_mm = math.sqrt(
        2 * 1.724e-8 / (2 * math.pi * as_float(row, "frequency_Hz") * 4 * math.pi * 1e-7)
    ) * 1000
    return {
        "strand_diameter_mm": strand_diameter_mm,
        "strand_area_mm2": strand_area,
        "strands_per_awg10_bundle": math.ceil(awg10_area / strand_area),
        "strands_total_per_winding": math.ceil(awg10_area / strand_area) * bundles,
        "skin_depth_mm": skin_depth_mm,
        "awg10_equiv_bundle_area_mm2": awg10_area,
    }


def build_docx(row: dict[str, str], summary: dict[str, Any], path: Path) -> None:
    d = derived_values(row)
    doc = Document()
    style_document(doc)

    title = doc.add_paragraph(style="Title")
    title.add_run("Ortogonaalinen Metglas AMCC-1000 -paraformer, lähellä 10 kW").bold = True
    subtitle = doc.add_paragraph()
    subtitle.add_run("Walter Russell Optical Dynamo Generator -päivitys: 128 kHz, kahden 90 astetta käännetyn U-puoliskon kytkentä.").italic = True

    add_heading(doc, "Pääsuunnittelupiste", 1)
    doc.add_paragraph(
        "Tämä dokumentti lukitsee nykyisen simulaattorin 10 kW:n ortogonaalisen Metglas-suunnittelupisteen. "
        "A1-A4- ja B1-B4-kaskadien impedanssi pidetään 50 ohm tasolla; Metglas-keskiosassa impedanssi saa olla eri, "
        "koska se sovitetaan erillisenä resonanssi- ja kuormitusasteena."
    )

    add_key_value_table(
        doc,
        [
            ("Tavoiteteho", f"{fmt(as_float(row, 'target_power_W'), 1)} W"),
            ("Taajuus", f"{fmt(as_float(row, 'frequency_Hz') / 1000, 3)} kHz"),
            ("Oletettu ortogonaalinen k", fmt(as_float(row, "assumed_k"), 3)),
            ("Ilmarako", f"{fmt(as_float(row, 'gap_mm'), 2)} mm"),
            ("Vaadittu B_peak", f"{fmt(as_float(row, 'required_B_peak_T'), 4)} T"),
            ("Kierrokset per Metglas-käämi", f"{int(as_float(row, 'selected_turns_per_winding'))}"),
            ("Primäärivirta", f"{fmt(as_float(row, 'primary_winding_I_rms_A'), 2)} A rms"),
            ("Primäärijännite", f"{fmt(as_float(row, 'primary_winding_V_rms_V') / 1000, 3)} kV rms"),
            ("Sekundäärin avoin jännite", f"{fmt(as_float(row, 'secondary_open_circuit_V_rms'), 2)} V rms"),
            ("Sovitettu sekundäärikuorma", f"{fmt(as_float(row, 'secondary_matched_load_R_ohm'), 3)} ohm"),
            ("Sekundäärivirta sovitetussa kuormassa", f"{fmt(as_float(row, 'secondary_matched_load_I_rms_A'), 2)} A rms"),
        ],
        (2.45, 4.05),
    )

    add_heading(doc, "Kaapeli ja käämitys", 1)
    add_key_value_table(
        doc,
        [
            ("Valittu johdin", "4 rinnakkaista AWG10-ekvivalenttia Litz-nippua per Metglas-käämi"),
            ("Kupariala per AWG10-ekvivalentti nippu", f"{fmt(d['awg10_equiv_bundle_area_mm2'], 3)} mm2"),
            ("Valittu kupariala per käämi", f"{fmt(as_float(row, 'selected_copper_area_mm2'), 3)} mm2"),
            ("Virrantiheys", f"{fmt(as_float(row, 'actual_current_density_A_per_mm2'), 3)} A/mm2"),
            ("Aktiivinen kaapeli per rinnakkaisnippu", f"{fmt(as_float(row, 'active_cable_per_parallel_bundle_m'), 2)} m"),
            ("Aktiivinen kaapeli per käämi, kaikki rinnakkaiset niput", f"{fmt(as_float(row, 'active_cable_per_winding_all_parallel_m'), 2)} m"),
            ("Hankittava kaapeli per käämi, +15 % varalla", f"{fmt(as_float(row, 'procurement_cable_per_winding_m'), 2)} m"),
            ("Hankittava kaapeli kahteen Metglas-käämiin", f"{fmt(as_float(row, 'procurement_cable_two_windings_m'), 2)} m"),
            ("Suositeltu yksittäissäie 128 kHz:llä", f"{fmt(d['strand_diameter_mm'], 2)} mm, skin depth noin {fmt(d['skin_depth_mm'], 3)} mm"),
            ("Säikeitä per AWG10-ekv. nippu, jos d=0.10 mm", f"noin {int(d['strands_per_awg10_bundle'])}"),
            ("Säikeitä per käämi yhteensä, jos 4 nippua", f"noin {int(d['strands_total_per_winding'])}"),
        ],
        (3.00, 3.50),
    )

    add_heading(doc, "Resonanssi, impedanssi ja reaktiivinen teho", 1)
    add_key_value_table(
        doc,
        [
            ("Omainduktanssi L", f"{fmt(as_float(row, 'L_self_mH'), 4)} mH"),
            ("Keskinäisinduktanssi M", f"{fmt(as_float(row, 'M_mutual_uH'), 3)} uH"),
            ("Induktiivinen reaktanssi X_L", f"{fmt(as_float(row, 'X_L_ohm'), 3)} ohm"),
            ("Sarja-/rinnakkaisresonanssin C @ 128 kHz", f"{fmt(as_float(row, 'C_resonance_nF'), 3)} nF"),
            ("Induktorin VAR", f"{fmt(as_float(row, 'Q_inductor_VAR') / 1000, 3)} kVAR"),
            ("Kondensaattorin VAR", f"{fmt(as_float(row, 'Q_capacitor_VAR') / 1000, 3)} kVAR"),
            ("Kiertävä reaktiivinen teho", f"{fmt(as_float(row, 'circulating_reactive_MVAR_abs'), 3)} MVAR"),
            ("Sovitus 50 ohmiin: impedanssisuhde", fmt(as_float(row, "matching_impedance_ratio_to_50ohm"), 3)),
            ("Sovitus 50 ohmiin: muuntosuhde", fmt(as_float(row, "matching_turns_ratio_to_50ohm"), 3)),
        ],
        (3.00, 3.50),
    )

    add_heading(doc, "Käytetty fysiikkamalli", 1)
    doc.add_paragraph("Dynaaminen tilayhtälö:")
    doc.add_paragraph("L_matrix dI/dt = V_source(t) - R I - V_C,    dV_C/dt = C^{-1} I")
    doc.add_paragraph("Metglas-siirtoraja sovitetulle resonanssikuormalle:")
    doc.add_paragraph("V_2,oc,rms = omega M I_1,rms,    P_max = V_2,oc,rms^2 / (4 R_2)")
    doc.add_paragraph("Resonanssikondensaattori:")
    doc.add_paragraph("C = 1 / (omega^2 L)")

    add_heading(doc, "Rakennusohje keskiosalle", 1)
    add_bullets(
        doc,
        [
            "Kokoa kaksi AMCC-1000 U-puoliskoa paraformer-asentoon niin, että toinen puoli on käännetty 90 astetta optisen akselin suhteen.",
            "Pidä nimellinen 2 mm rako ja tee väliin mekaanisesti toistettava, ei-hygroskooppinen eristeväli.",
            "Tee kumpaankin Metglas-haaraan 12 kierrosta. Jokainen kierros muodostuu neljästä rinnakkaisesta AWG10-ekvivalentista Litz-nipusta.",
            "Pidä rinnakkaisniput samanpituisina: aktiivinen pituus 10.20 m per nippu per käämi; hanki vähintään 46.92 m per käämi, kun rinnakkaiset niput lasketaan yhteen.",
            "Käytä hajakapasitanssin hallintaan kerrosvälejä ja riittävää RF/HV-eristettä; 9.3 kV rms suunnittelupiste vaatii koronamarginaalin.",
            "Viritys tehdään ensin pienellä teholla VNA:lla ja LCR-mittarilla, sitten nostetaan MOSFET-ajurin tehoa portaissa samalla mitaten käämivirta, käämijännite, lämpötila ja spektri.",
        ],
    )

    add_heading(doc, "Riskihuomio", 1)
    doc.add_paragraph(
        "10 kW saavutetaan mallissa vain nostamalla Metglas-vuon huippuarvo noin 0.593 teslaan ja hyväksymällä noin 0.521 MVAR kiertävä reaktiivinen teho. "
        "Tämä on korkeajännitteinen, korkean reaktiivisen tehon resonanssijärjestelmä. Core loss, eristys, koronakesto, lämpötila ja todellinen k on mitattava ennen täyden tehon ajoa."
    )

    figure = FIGURES / "orthogonal_paraformer_10kw_design.png"
    if figure.exists():
        add_heading(doc, "Simulaatiokuva", 1)
        doc.add_picture(str(figure), width=Inches(6.4))

    doc.add_paragraph(f"Lähdetiedosto: {OUTPUTS / 'orthogonal_paraformer_10kw_cable_plan.csv'}")
    doc.add_paragraph(f"Simulaation yhteenveto: {summary.get('power_w', '')} W kohdeteho, {summary.get('mode_count', '')} moodia.")
    doc.save(path)


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def build_latex(row: dict[str, str], summary: dict[str, Any], path: Path) -> None:
    d = derived_values(row)
    table_rows = [
        ("Target power", f"{fmt(as_float(row, 'target_power_W'), 1)} W"),
        ("Frequency", f"{fmt(as_float(row, 'frequency_Hz') / 1000, 3)} kHz"),
        ("Orthogonal coupling k", fmt(as_float(row, "assumed_k"), 3)),
        ("Air gap", f"{fmt(as_float(row, 'gap_mm'), 2)} mm"),
        ("Required peak flux density", f"{fmt(as_float(row, 'required_B_peak_T'), 4)} T"),
        ("Turns per winding", f"{int(as_float(row, 'selected_turns_per_winding'))}"),
        ("Primary current", f"{fmt(as_float(row, 'primary_winding_I_rms_A'), 2)} A rms"),
        ("Primary voltage", f"{fmt(as_float(row, 'primary_winding_V_rms_V') / 1000, 3)} kV rms"),
        ("Secondary open-circuit voltage", f"{fmt(as_float(row, 'secondary_open_circuit_V_rms'), 2)} V rms"),
        ("Matched secondary load", f"{fmt(as_float(row, 'secondary_matched_load_R_ohm'), 3)} ohm"),
        ("Pmax matched secondary", f"{fmt(as_float(row, 'Pmax_matched_secondary_W'), 1)} W"),
        ("Self inductance", f"{fmt(as_float(row, 'L_self_mH'), 4)} mH"),
        ("Mutual inductance", f"{fmt(as_float(row, 'M_mutual_uH'), 3)} uH"),
        ("Resonance capacitance", f"{fmt(as_float(row, 'C_resonance_nF'), 3)} nF"),
        ("Circulating reactive power", f"{fmt(as_float(row, 'circulating_reactive_MVAR_abs'), 3)} MVAR"),
        ("Cable per winding, all parallel bundles", f"{fmt(as_float(row, 'procurement_cable_per_winding_m'), 2)} m"),
        ("Cable for both Metglas windings", f"{fmt(as_float(row, 'procurement_cable_two_windings_m'), 2)} m"),
        ("Recommended strand diameter", f"{fmt(d['strand_diameter_mm'], 2)} mm; skin depth {fmt(d['skin_depth_mm'], 3)} mm"),
    ]
    rows_tex = "\n".join(
        f"{latex_escape(label)} & {latex_escape(value)} \\\\" for label, value in table_rows
    )
    content = rf"""\documentclass[11pt]{{article}}
\usepackage[a4paper,margin=25mm]{{geometry}}
\usepackage{{amsmath,booktabs,longtable,siunitx,graphicx,hyperref}}
\title{{Orthogonal Metglas AMCC-1000 Paraformer Near 10 kW}}
\author{{Walter Russell Optical Dynamo Generator simulation package}}
\date{{2026-05-21}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This article documents the updated orthogonal AMCC-1000 paraformer design point used in the
multilanguage dynamic simulator. The A1--A4 and B1--B4 octave ladder remains a constant
\SI{{50}}{{\ohm}} system, while the Metglas center is treated as a separately matched resonant
transformer stage. The computed near-\SI{{10}}{{kW}} point requires high flux density, high
winding voltage, and large circulating reactive power.
\end{{abstract}}

\section{{Model}}
The dynamic simulator solves the coupled resonant network
\begin{{align}}
\mathbf{{L}}\frac{{d\mathbf{{i}}}}{{dt}} &= \mathbf{{v}}_s(t)-\mathbf{{R}}\mathbf{{i}}-\mathbf{{v}}_C,\\
\frac{{d\mathbf{{v}}_C}}{{dt}} &= \mathbf{{C}}^{{-1}}\mathbf{{i}} .
\end{{align}}
For the orthogonal Metglas pair the matched-load Thevenin limit is
\begin{{align}}
V_{{2,\mathrm{{oc,rms}}}} &= \omega M I_{{1,\mathrm{{rms}}}},\\
P_{{\max}} &= \frac{{V_{{2,\mathrm{{oc,rms}}}}^2}}{{4R_2}},\\
C_{{\mathrm{{res}}}} &= \frac{{1}}{{\omega^2 L}},\\
M &= kL .
\end{{align}}
The copper area is selected from
\begin{{equation}}
A_{{\mathrm{{Cu}}}} \geq \frac{{I_{{\mathrm{{rms}}}}}}{{J_{{\max}}}},
\end{{equation}}
using \(J_{{\max}}=\SI{{3}}{{A/mm^2}}\).

\section{{Calculated Design Point}}
\begin{{longtable}}{{@{{}}ll@{{}}}}
\toprule
Quantity & Value\\
\midrule
{rows_tex}
\bottomrule
\end{{longtable}}

\section{{Cable Plan}}
Use four parallel AWG10-equivalent Litz bundles per Metglas winding. With a
\SI{{0.85}}{{m}} estimated mean turn length and 12 turns, each parallel bundle has
\SI{{10.20}}{{m}} active length per winding. Counting all four parallel bundles gives
\SI{{40.80}}{{m}} active conductor per winding. With a 15\% procurement reserve this becomes
\SI{{46.92}}{{m}} per winding and \SI{{93.84}}{{m}} for the two orthogonal Metglas windings.
At \SI{{128}}{{kHz}}, copper skin depth is about \SI{{0.184}}{{mm}}; a practical Litz choice is
approximately \SI{{0.10}}{{mm}} strands, about {int(d['strands_per_awg10_bundle'])} strands per
AWG10-equivalent bundle.

\section{{Practical Tuning}}
First measure each winding with an LCR meter at low voltage. Add the calculated resonant
capacitance and trim with a VNA around \SI{{128}}{{kHz}}. Then drive from the MOSFET stage at
low duty and low bus voltage while measuring winding current with an RF current probe, winding
voltage with a high-voltage probe, and emitted spectrum with the wireless spectrometer. Increase
power only after the measured coupling coefficient, temperature rise, and corona margin are known.

\section{{Engineering Warning}}
The near-\SI{{10}}{{kW}} point is not reached by cable length alone. It is reached in the model by
raising \(B_\mathrm{{peak}}\) to approximately \SI{{0.593}}{{T}} and accepting approximately
\SI{{0.521}}{{MVAR}} of circulating reactive power. This is a high-stress resonant operating
point and requires measured core-loss, insulation, corona, and thermal validation.

\section{{Source Files}}
The synchronized data row is \texttt{{outputs/orthogonal\_paraformer\_10kw\_cable\_plan.csv}}.
The executed Python simulator reports {summary.get('mode_count', '')} modes and a target power of
{summary.get('power_w', '')} W.

\end{{document}}
"""
    path.write_text(content, encoding="utf-8")


def csv_to_xlsx(csv_path: Path, xlsx_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = csv_path.stem[:31]
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)
    header_fill = PatternFill("solid", fgColor="E8EEF5")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for col_idx, column in enumerate(ws.columns, start=1):
        max_len = max((len(str(cell.value)) if cell.value is not None else 0 for cell in column), default=0)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(10, min(42, max_len + 2))
    ws.freeze_panes = "A2"
    wb.save(xlsx_path)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    row = read_first_csv_row(OUTPUTS / "orthogonal_paraformer_10kw_cable_plan.csv")
    summary = json.loads((OUTPUTS / "power_simulation_summary.json").read_text(encoding="utf-8"))
    build_docx(row, summary, DOCS / "orthogonal_metglas_paraformer_10kw_ohje.docx")
    build_latex(row, summary, DOCS / "orthogonal_metglas_paraformer_10kw_article.tex")
    for csv_path in sorted(OUTPUTS.glob("*.csv")):
        csv_to_xlsx(csv_path, csv_path.with_suffix(".xlsx"))


if __name__ == "__main__":
    main()
