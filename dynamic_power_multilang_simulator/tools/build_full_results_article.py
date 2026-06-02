#!/usr/bin/env python3
"""Build the detailed English LaTeX article from the latest simulation outputs."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
WR = REPO / "generator" / "outputs"
PWR = ROOT / "outputs"
DOCS = ROOT / "docs"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, ValueError, TypeError):
        return default


def tex(s: object) -> str:
    text = str(s)
    repl = {
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
    return "".join(repl.get(ch, ch) for ch in text)


def n(value: float, digits: int = 3) -> str:
    if abs(value) >= 1000:
        return f"{value:,.{digits}f}".replace(",", r"\,")
    return f"{value:.{digits}f}"


def table(headers: list[str], body: Iterable[Iterable[object]], align: str | None = None) -> str:
    if align is None:
        align = "l" + "r" * (len(headers) - 1)
    lines = [r"\begin{tabular}{" + align + "}", r"\toprule"]
    lines.append(" & ".join(tex(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    for row in body:
        lines.append(" & ".join(tex(x) for x in row) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def figure(path: str, caption: str, label: str, width: str = r"0.98\textwidth") -> str:
    return rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width={width}]{{{path}}}
\caption{{{caption}}}
\label{{{label}}}
\end{{figure}}
"""


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    stage_imp = rows(WR / "stage_impedance_power.csv")
    branch = rows(WR / "branch_lc_tuning_plan.csv")
    cables = rows(WR / "cable_lengths.csv")
    wire = rows(WR / "wire_awg_litz_plan.csv")
    bobbins = rows(WR / "bobbin_geometry_and_fill.csv")
    core_geom = rows(WR / "paraformer_u_core_geometry.csv")
    amcc = rows(WR / "amcc1000_128k_sweep.csv")
    stage_rms = rows(PWR / "stage_rms_watts_amps_volts_summary.csv")
    transfer = rows(PWR / "metglas_transformer_transfer_limit.csv")
    core_dyn = rows(PWR / "core_dynamic_summary.csv")
    ortho = rows(PWR / "orthogonal_paraformer_10kw_cable_plan.csv")[0]
    summary = json.loads((PWR / "power_simulation_summary.json").read_text(encoding="utf-8"))

    unique_stage_imp = []
    seen = set()
    for r in stage_imp:
        st = r["stage"]
        if st not in seen:
            unique_stage_imp.append(r)
            seen.add(st)
    first_branch_by_stage = {}
    for r in branch:
        first_branch_by_stage.setdefault(r["stage"], r)

    coil_table = table(
        [
            "Stage",
            "Mirror",
            "f (kHz)",
            "Zstage (ohm)",
            "Active cables",
            "Cable lengths in bobbin (m)",
            "Target L (uH)",
            "Target C (nF)",
            "Branch L/C",
            "Bare branch L (uH)",
            "Series trim (uH)",
            "I10k (Arms)",
            "Cu loss 10 kW (W)",
        ],
        [
            [
                r["stage"],
                r["mirror_pair"],
                n(f(r, "frequency_kHz"), 1),
                n(f(r, "target_impedance_ohm"), 1),
                r["active_cables"],
                r["segment_lengths_m"],
                n(f(r, "target_L_uH"), 3),
                n(f(r, "target_C_nF"), 3),
                f"{n(f(r, 'branch_target_L_uH'), 3)} uH / {n(f(r, 'branch_target_C_nF'), 3)} nF",
                n(f(first_branch_by_stage.get(r["stage"], {}), "grover_loop_array_L_uH"), 3),
                n(f(first_branch_by_stage.get(r["stage"], {}), "series_trim_L_uH_if_needed"), 3),
                n(f(r, "current_10kW_Arms"), 3),
                n(f(r, "loss_10kW_W"), 3),
            ]
            for r in unique_stage_imp
        ],
        align="llrllrrrrrrrr",
    )

    cable_table = table(
        ["Cable", "Cut + 3% (m)", "Visited stages", "Modern wire", "Connection note"],
        [
            [
                r["cable"],
                n(f(r, "cut_plus_3pct_m"), 2),
                r["visited_stages"],
                r["wire"],
                "same magnetic polarity",
            ]
            for r in cables
        ],
        align="lrlll",
    )

    wire_table = table(
        [
            "Cable",
            "Hist. AWG",
            "Modern AWG eq.",
            "Litz",
            "Cu area (mm2)",
            "OD (mm)",
            "Rdc 60C (ohm/m)",
            "Role",
        ],
        [
            [
                r["cable"],
                r["historical_awg_from_russell_text"],
                r["recommended_modern_awg_equivalent"],
                f"{r['strand_count']} x AWG{r['strand_awg']}",
                n(f(r, "copper_area_mm2"), 3),
                n(f(r, "estimated_silk_litz_od_mm"), 3),
                n(f(r, "rdc_ohm_per_m_60C"), 5),
                r["role"],
            ]
            for r in wire
        ],
        align="lrrlrrrl",
    )

    bobbin_table = table(
        [
            "Stage",
            "Family",
            "Axial (mm)",
            "ID (mm)",
            "Mean D (mm)",
            "OD (mm)",
            "Active cables",
            "Turns by cable",
            "Fill (%)",
            "Pack radial depth (mm)",
        ],
        [
            [
                r["stage"],
                r["bobbin_family"],
                n(f(r, "axial_length_mm"), 1),
                n(f(r, "inner_diameter_mm"), 1),
                n(f(r, "mean_diameter_mm"), 1),
                n(f(r, "outer_diameter_mm"), 1),
                r["active_cables"],
                r["turns_by_cable"],
                n(f(r, "fill_percent_of_source_window"), 3),
                n(f(r, "required_radial_depth_mm_from_pack"), 3),
            ]
            for r in bobbins
        ],
        align="llrrrrllrr",
    )

    stage_dyn_table = table(
        [
            "Stage",
            "f (kHz)",
            "Branches",
            "Psrc (W)",
            "Qsrc (var)",
            "S (VA)",
            "Pcu (W)",
            "QL sum (var)",
            "QC sum (var)",
            "PF",
        ],
        [
            [
                r["stage"],
                n(f(r, "frequency_Hz") / 1000, 1),
                r["active_branch_count"],
                n(f(r, "P_source_W"), 2),
                n(f(r, "Q_source_VAR"), 2),
                n(f(r, "S_source_VA"), 2),
                n(f(r, "P_copper_W"), 3),
                n(f(r, "Q_inductor_VAR_sum"), 1),
                n(f(r, "Q_capacitor_VAR_sum"), 1),
                n(f(r, "power_factor_source"), 4),
            ]
            for r in stage_rms
        ],
        align="lrrrrrrrrr",
    )

    core_table = table(
        [
            "Part",
            "Orientation",
            "Flux axis",
            "Winding",
            "Turns ref.",
            "Gap (mm)",
            "L (mH)",
            "XL 128 kHz (ohm)",
        ],
        [
            [
                r["part"],
                r["orientation_deg_about_optical_axis"],
                r["flux_axis"],
                r["winding"],
                n(f(r, "turns_reference"), 1),
                n(f(r, "gap_mm"), 1),
                n(f(r, "L_self_mH"), 5),
                n(f(r, "X_L_at_128k_ohm"), 3),
            ]
            for r in core_geom
        ],
        align="lrlrrrrr",
    )

    core_dyn_table = table(
        [
            "Mode",
            "L (uH)",
            "C (nF)",
            "Rdyn (ohm)",
            "Target I (A)",
            "Sim I (A)",
            "Bpeak (T)",
            "Cap V (Vrms)",
            "Damping W",
        ],
        [
            [
                r["mode"],
                n(f(r, "L_uH"), 3),
                n(f(r, "C_nF"), 3),
                n(f(r, "R_dynamic_ohm"), 3),
                n(f(r, "target_I_rms_A"), 3),
                n(f(r, "sim_I_rms_A"), 3),
                n(f(r, "B_peak_T"), 5),
                n(f(r, "capacitor_V_rms_V"), 2),
                n(f(r, "dynamic_damping_loss_W"), 2),
            ]
            for r in core_dyn
        ],
        align="lrrrrrrrr",
    )

    amcc_table = table(
        ["Gap (mm)", "B limit (T)", "L (mH)", "XL (ohm)", "Cres (nF)", "Vrms", "Irms"],
        [
            [
                n(f(r, "gap_mm"), 1),
                n(f(r, "B_limit_T"), 3),
                n(f(r, "L_mH"), 5),
                n(f(r, "X_L_ohm"), 3),
                n(f(r, "C_resonance_nF"), 3),
                n(f(r, "Vrms_at_B_limit"), 1),
                n(f(r, "Irms_magnetizing_at_B_limit"), 3),
            ]
            for r in amcc
        ],
        align="rrrrrrr",
    )

    transfer_table = table(
        ["Case", "k", "M (uH)", "I1 (A)", "V2oc (Vrms)", "R2 dyn (ohm)", "Pmax (W)"],
        [
            [
                r["case"],
                n(f(r, "k"), 3),
                n(f(r, "M_uH"), 3),
                n(f(r, "primary_I_rms_A"), 3),
                n(f(r, "secondary_open_circuit_V_rms"), 2),
                n(f(r, "secondary_R_dynamic_ohm"), 3),
                n(f(r, "Pmax_matched_secondary_W"), 3),
            ]
            for r in transfer
        ],
        align="lrrrrrr",
    )

    ortho_table = table(
        ["Quantity", "Value"],
        [
            ("Frequency", f"{n(f(ortho, 'frequency_Hz')/1000, 3)} kHz"),
            ("Assumed orthogonal coupling k", n(f(ortho, "assumed_k"), 3)),
            ("Gap", f"{n(f(ortho, 'gap_mm'), 2)} mm"),
            ("Required B peak", f"{n(f(ortho, 'required_B_peak_T'), 4)} T"),
            ("Selected turns per winding", n(f(ortho, "selected_turns_per_winding"), 0)),
            ("Primary winding current", f"{n(f(ortho, 'primary_winding_I_rms_A'), 2)} Arms"),
            ("Primary winding voltage", f"{n(f(ortho, 'primary_winding_V_rms_V')/1000, 3)} kVrms"),
            ("Secondary open-circuit voltage", f"{n(f(ortho, 'secondary_open_circuit_V_rms'), 2)} Vrms"),
            ("Secondary matched load", f"{n(f(ortho, 'secondary_matched_load_R_ohm'), 3)} ohm"),
            ("Secondary matched load current", f"{n(f(ortho, 'secondary_matched_load_I_rms_A'), 2)} Arms"),
            ("Pmax matched secondary", f"{n(f(ortho, 'Pmax_matched_secondary_W'), 1)} W"),
            ("L self", f"{n(f(ortho, 'L_self_mH'), 4)} mH"),
            ("M mutual", f"{n(f(ortho, 'M_mutual_uH'), 3)} uH"),
            ("XL", f"{n(f(ortho, 'X_L_ohm'), 3)} ohm"),
            ("C resonance", f"{n(f(ortho, 'C_resonance_nF'), 3)} nF"),
            ("Circulating reactive power", f"{n(f(ortho, 'circulating_reactive_MVAR_abs'), 3)} MVAR"),
            ("Parallel AWG10-equivalent Litz bundles", n(f(ortho, "selected_parallel_AWG10_equiv_Litz_bundles"), 0)),
            ("Selected copper area", f"{n(f(ortho, 'selected_copper_area_mm2'), 3)} mm2"),
            ("Current density", f"{n(f(ortho, 'actual_current_density_A_per_mm2'), 3)} A/mm2"),
            ("Active cable per parallel bundle", f"{n(f(ortho, 'active_cable_per_parallel_bundle_m'), 2)} m"),
            ("Active cable per winding, all parallel bundles", f"{n(f(ortho, 'active_cable_per_winding_all_parallel_m'), 2)} m"),
            ("Procurement cable per winding", f"{n(f(ortho, 'procurement_cable_per_winding_m'), 2)} m"),
            ("Procurement cable, two windings", f"{n(f(ortho, 'procurement_cable_two_windings_m'), 2)} m"),
        ],
        align="lr",
    )

    vac_open = f(ortho, "secondary_open_circuit_V_rms")
    rs = f(ortho, "secondary_matched_load_R_ohm")
    vac_load = vac_open / 2
    iac = f(ortho, "secondary_matched_load_I_rms_A")
    vdc_nom = math.sqrt(2) * vac_load
    vdc_noload = math.sqrt(2) * vac_open
    idc_nom = f(ortho, "Pmax_matched_secondary_W") / vdc_nom
    diode_avg = (math.sqrt(2) * iac) / math.pi
    diode_rms = iac / math.sqrt(2)
    c_20v = idc_nom / (2 * f(ortho, "frequency_Hz") * 20.0)
    c_50v = idc_nom / (2 * f(ortho, "frequency_Hz") * 50.0)
    rdc_nom = vdc_nom**2 / f(ortho, "Pmax_matched_secondary_W")
    match_ratio = rdc_nom / rs
    turns_ratio = math.sqrt(match_ratio)

    diode_table = table(
        ["Parameter", "Calculated value", "Design implication"],
        [
            ("B-side Thevenin voltage", f"{n(vac_open, 2)} Vrms", "open-circuit RF value"),
            ("Matched RF load voltage", f"{n(vac_load, 2)} Vrms", "half of Thevenin voltage"),
            ("Matched RF load current", f"{n(iac, 2)} Arms", "sets diode RMS stress"),
            ("Nominal capacitor-input DC bus", f"{n(vdc_nom, 1)} Vdc", "loaded near matched point"),
            ("No-load capacitor DC bus", f"{n(vdc_noload, 1)} Vdc", "sets insulation and clamp rating"),
            ("Nominal DC current at 10 kW", f"{n(idc_nom, 2)} A", "load and capacitor ripple current"),
            ("Per-diode average current estimate", f"{n(diode_avg, 2)} A", "half-wave bridge conduction"),
            ("Per-diode RMS current estimate", f"{n(diode_rms, 2)} A", "thermal sizing baseline"),
            ("DC load equivalent", f"{n(rdc_nom, 2)} ohm", "for 10 kW near nominal Vdc"),
            ("Rdc/RF match ratio", f"{n(match_ratio, 3)}", "optional RF transformer ratio"),
            ("Matching turns ratio", f"{n(turns_ratio, 3)}", "sqrt(Rdc/RF)"),
            ("DC-link capacitance for 20 Vpp ripple", f"{n(c_20v*1e6, 2)} uF", "film capacitor bank"),
            ("DC-link capacitance for 50 Vpp ripple", f"{n(c_50v*1e6, 2)} uF", "minimum pulse bank"),
        ],
        align="lrl",
    )

    fig_imagen_system = figure(
        "../figures/imagen2_orthogonal_amcc1000_system_explainer_v2.png",
        "Imagen2-generated system explainer used as a visual map.  The numbers correspond to the A1 MOSFET driver, octave ladder, A4 focus region, orthogonal AMCC-1000 center, B4 pickup, B-side SiC rectifier, DC link and load, Litz bundles, X/Y flux axes, and measurement probes.  The numerical values in the article tables are authoritative; generated image text should be read as schematic annotation.",
        "fig:imagen2-system",
    )
    fig_stage_reactive = figure(
        "../figures/stage_reactive_power.png",
        "Reactive power by stage from the dynamic simulation.  The net LC reactive power is near zero when the branch is tuned, but the inductor and capacitor individually exchange substantial VAR.",
        "fig:stage-reactive",
    )
    fig_metglas_sweep = figure(
        "../figures/metglas_transfer_power_sweep.png",
        r"Metglas transfer power sweep.  The weak orthogonal \(k=0.08\) case at \SI{50}{mT} is far below \SI{10}{kW}; high power requires either much stronger coupling, much higher flux, or both.",
        "fig:metglas-sweep",
    )
    fig_ortho_bars = figure(
        "../figures/orthogonal_paraformer_10kw_design.png",
        r"Condensed numerical bar plot for the near-\SI{10}{kW} orthogonal design point.",
        "fig:ortho-bars",
    )

    article = rf"""\documentclass[11pt]{{article}}
\usepackage[a4paper,margin=22mm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,longtable,array,graphicx,float,hyperref,siunitx,xcolor}}
\usepackage{{caption}}
\usepackage{{microtype}}
\setlength{{\parskip}}{{0.55em}}
\setlength{{\parindent}}{{0pt}}
\hypersetup{{colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black}}
\sisetup{{detect-all=true,per-mode=symbol}}
\title{{Detailed Physical Analysis of the Orthogonal Metglas AMCC-1000 Walter Russell Optical Dynamo Generator Design}}
\author{{Generated from the latest simulation outputs in \texttt{{dynamic\_power\_multilang\_simulator}}}}
\date{{22 May 2026}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This article consolidates the latest numerical results for an eight-stage
Walter Russell Optical Dynamo Generator inspired build using modern silk-covered
Litz conductors and an orthogonal Metglas AMCC-1000 paraformer center.  The
outer structure preserves the corrected eight-coil cascade A1--A4 and B4--B1:
two active cable paths in stages 1--2, four active cable paths in stage 3, and
all eight cable paths in stage 4.  The A/B ladder is held to a target
\SI{{50}}{{\ohm}} stage impedance while the Metglas center is treated as a
separately matched resonant transformer.  The current near-\SI{{10}}{{kW}}
orthogonal design point uses \SI{{128}}{{kHz}}, \(k=0.08\), a \SI{{2}}{{mm}}
gap, \SI{{12}} turns per Metglas winding, \SI{{55.92}}{{A_{{rms}}}} primary
current, and \SI{{9.314}}{{kV_{{rms}}}} primary winding voltage.  It transfers
\SI{{10}}{{kW}} in the matched-load model only by accepting
\SI{{0.593}}{{T}} peak flux density and approximately \SI{{0.521}}{{MVAR}} of
circulating reactive power.  The design is therefore a high-voltage, high-Q,
high-reactive-power RF experiment, not a low-stress power transformer.
\end{{abstract}}

\section{{Scope, Assumptions, and Safety Boundary}}
The analysis below is an engineering model of the present files, not a claim of
over-unity operation.  The simulator solves a coupled RLC network and evaluates
ordinary conservation-of-energy quantities: real power, reactive power, copper
loss, damping loss, magnetic energy, electric energy, and a Thevenin matched-load
transfer bound.  The result should be treated as a design envelope for bench
experiments with proper isolation, interlocks, shields, thermal measurement, and
instrumentation.

The highest-stress result is the orthogonal Metglas point.  It requires
\SI{{9.314}}{{kV_{{rms}}}} on the primary winding and a circulating reactive power
near \SI{{0.521}}{{MVAR}}.  At \SI{{128}}{{kHz}}, layout parasitics, inter-turn
capacitance, diode junction capacitance, corona onset, and core heating can
dominate the ideal calculation.  No full-power run should be attempted before
low-power vector-network measurements establish the real coupling coefficient,
loaded Q, winding capacitance, insulation margin, and core loss.

{fig_imagen_system}

\section{{Topology and Cable Occupancy}}
The build is an eight-coil cascade around a center paraformer.  On the A side,
A1 and A2 carry only C1 and C2.  A3 carries C1--C4.  A4 carries C1--C8.  The B
side mirrors this order in reverse: B4 carries C1--C8, B3 carries C1--C4, and B2
and B1 carry C1 and C2.  This preserves the corrected interpretation: four coils
before the center and four identical mirrored coils after it.

Each cable is treated as a continuous routed conductor segment, not as an
independent isolated winding in every bobbin.  Resonant L/C trimming is assigned
per active branch so the stage impedance remains \SI{{50}}{{\ohm}} despite the
changing number of active cables.  This is the practical answer to the
``impedance must not change'' constraint: as branches are added, each branch
target impedance increases so their parallel combination remains constant.

\subsection{{Stage Values}}
\resizebox{{\textwidth}}{{!}}{{%
{coil_table}
}}

The wound lengths in this table are now solved physical lengths, not
placeholders.  Each active branch length is found by the same Grover coaxial
loop-array model used to report the branch inductance, so the series-trim
column is zero within numerical precision.  A1, for example, uses
\SI{{75.937339}}{{m}} per C1/C2 branch on the large bobbin,
\SI{{128.599732}}{{turns}}, and \SI{{994.718394}}{{\micro H}} per branch.
The two equal branches in parallel therefore produce the
\SI{{497.359197}}{{\micro H}} stage target while the external stage impedance
remains \SI{{50}}{{\ohm}}.

\subsection{{Cable Inventory}}
\resizebox{{\textwidth}}{{!}}{{%
{cable_table}
}}

\subsection{{Modern Litz Selections}}
The original Russell notes refer to historical wire sizes near AWG 11, 12, 18
or 14, and 22.  The modern design replaces these with RF Litz equivalents so the
\SI{{128}}{{kHz}} stage is not dominated by skin effect.  For copper,
\begin{{equation}}
\delta = \sqrt{{\frac{{2\rho}}{{\omega \mu_0}}}},
\end{{equation}}
which gives approximately \SI{{0.185}}{{mm}} skin depth at \SI{{128}}{{kHz}}.
AWG36 strands with diameter near \SI{{0.127}}{{mm}} are below this depth and are
therefore a reasonable RF strand choice.

\resizebox{{\textwidth}}{{!}}{{%
{wire_table}
}}

\section{{Bobbin Geometry and Placement}}
The large bobbins are used for A1, A2, B2, and B1.  The small bobbins are used
for A3, A4, B4, and B3.  Cables are placed side-by-side in the same polarity,
not bifilar-cancellation wound.  Where several cable groups occupy the same
bobbin, they should be layered with insulation and physical separation so that
the high-voltage A4/B4 region does not force unnecessary capacitive coupling.

\resizebox{{\textwidth}}{{!}}{{%
{bobbin_table}
}}

\section{{Resonance and Impedance Equations}}
For each branch, the target resonance is
\begin{{equation}}
f_0 = \frac{{1}}{{2\pi\sqrt{{LC}}}},
\end{{equation}}
and the characteristic branch impedance is
\begin{{equation}}
Z_b = \sqrt{{\frac{{L}}{{C}}}}.
\end{{equation}}
If \(N_b\) equalized active branches operate in parallel, the stage impedance is
\begin{{equation}}
Z_{{\mathrm{{stage}}}} = \frac{{Z_b}}{{N_b}}.
\end{{equation}}
The design therefore uses \(Z_b=\SI{{100}}{{\ohm}}\) when two branches are
active, \(Z_b=\SI{{200}}{{\ohm}}\) when four branches are active, and
\(Z_b=\SI{{400}}{{\ohm}}\) when eight branches are active.  This is why A4 and
B4 can include all eight cable paths while the external stage impedance remains
\SI{{50}}{{\ohm}}.

For sinusoidal RMS phasors,
\begin{{align}}
S &= V_{{\mathrm{{rms}}}} I_{{\mathrm{{rms}}}}^*,\\
P &= \Re(S),\qquad Q=\Im(S),\\
Q_L &= I_{{\mathrm{{rms}}}}^2 \omega L,\\
Q_C &= -\frac{{I_{{\mathrm{{rms}}}}^2}}{{\omega C}} .
\end{{align}}
The ideal branch resonance cancels \(Q_L+Q_C\), but each inductor and capacitor
still carries large circulating reactive power.  This is visible in the dynamic
results below.

\section{{Dynamic RMS, Watts, Amperes, Volts, and VAR Results}}
The multilanguage simulator solves the state-space model
\begin{{align}}
\mathbf{{L}}\frac{{d\mathbf{{i}}}}{{dt}} &= \mathbf{{v}}_s(t)-\mathbf{{R}}\mathbf{{i}}-\mathbf{{v}}_C,\\
\frac{{d\mathbf{{v}}_C}}{{dt}} &= \mathbf{{C}}^{{-1}}\mathbf{{i}} .
\end{{align}}
The latest Python run contains {summary.get("mode_count", "")} modes.  The
stage source power sum is \SI{{{n(float(summary.get("total_stage_source_W", 0)), 3)}}}{{W}} in the
matched octave-ladder excitation case, with total copper loss of
\SI{{{n(float(summary.get("total_stage_copper_W", 0)), 3)}}}{{W}} in the modeled conductors.
These numbers are not the same as the separate orthogonal Metglas
\SI{{10}}{{kW}} matched-transfer design point; they are the dynamic drive values
for the full ladder model.

\resizebox{{\textwidth}}{{!}}{{%
{stage_dyn_table}
}}

{fig_stage_reactive}

\section{{Metglas AMCC-1000 Orthogonal Center}}
The center uses two AMCC-1000 U-core equivalents in a paraformer arrangement.
U\_A is assigned the X flux axis and U\_B the Y flux axis.  U\_B is rotated
\SI{{90}}{{deg}} about the optical axis, so the pair is intentionally not a
conventional closed transformer.  Coupling is therefore modeled as weak
orthogonal coupling, here \(k=0.08\).

\resizebox{{0.82\textwidth}}{{!}}{{%
{core_table}
}}

The reference AMCC sweep below shows how gap and flux limit affect inductance,
reactance, resonant capacitance, and magnetizing current.  The \SI{{2}}{{mm}},
\SI{{50}}{{mT}} reference has only \SI{{70.99}}{{W}} of ideal matched-transfer
power at \(k=0.08\), far below \SI{{10}}{{kW}}.  The near-\SI{{10}}{{kW}} point
therefore cannot be obtained by merely adding wire; it requires a much larger
flux swing and a different winding selection.

\resizebox{{\textwidth}}{{!}}{{%
{amcc_table}
}}

\subsection{{Dynamic Core Modes}}
\resizebox{{0.88\textwidth}}{{!}}{{%
{core_dyn_table}
}}

\subsection{{Matched-Transfer Limit}}
For an orthogonal resonant pair, the secondary open-circuit RMS voltage is
\begin{{equation}}
V_{{2,\mathrm{{oc}}}} = \omega M I_{{1,\mathrm{{rms}}}},
\end{{equation}}
where
\begin{{equation}}
M = k\sqrt{{L_1L_2}}.
\end{{equation}}
The maximum power delivered to a matched load is the Thevenin limit
\begin{{equation}}
P_{{\max}} = \frac{{V_{{2,\mathrm{{oc}}}}^2}}{{4R_2}}.
\end{{equation}}

\resizebox{{\textwidth}}{{!}}{{%
{transfer_table}
}}

{fig_metglas_sweep}

\section{{Near-10 kW Orthogonal Paraformer Design Point}}
The latest optimized orthogonal design point is summarized in
Table~\ref{{tab:orthopoint}}.  The selected winding uses \SI{{12}} turns per
Metglas side.  Each turn is made from four parallel AWG10-equivalent Litz
bundles.  With a \SI{{0.85}}{{m}} mean turn length, one parallel bundle requires
\SI{{10.20}}{{m}} active length per winding.  Four bundles therefore require
\SI{{40.80}}{{m}} active conductor per winding, and the procurement value with
\SI{{15}}{{\percent}} reserve is \SI{{46.92}}{{m}} per winding or
\SI{{93.84}}{{m}} for the two orthogonal windings.

\begin{{table}}[H]
\centering
\caption{{Near-\SI{{10}}{{kW}} orthogonal AMCC-1000 design point.}}
\label{{tab:orthopoint}}
{ortho_table}
\end{{table}}

The price of this point is high voltage and high reactive power.  The inductive
reactive power is
\begin{{equation}}
Q_L = I^2 X_L =
(\SI{{55.917}}{{A}})^2(\SI{{166.573}}{{\ohm}})
\approx \SI{{520.8}}{{kVAR}}.
\end{{equation}}
The resonant capacitor carries the same magnitude with opposite sign.  The
external source sees the matched real transfer, but the local tank hardware must
survive the circulating energy.

{fig_ortho_bars}

\section{{B-Side Energy Extraction with SiC Diodes}}
Energy should be extracted from the B side at the B4 pickup/focus region, not by
shorting the entire B ladder.  Electrically, the safest model is a dedicated
B-side pickup winding or tap that sees the orthogonal Metglas Thevenin source
and then drives a matched rectifier network.  The rectifier must be part of the
impedance match: a bare capacitor-input bridge directly across a high-Q RF node
will detune the standing wave, collapse Q, and create very high diode current
pulses.

\subsection{{Thevenin and Rectifier Design Numbers}}
The orthogonal calculation gives an open-circuit secondary voltage of
\SI{{{n(vac_open, 2)}}}{{V_{{rms}}}}.  For a matched load, the load receives half
the Thevenin voltage, so
\begin{{equation}}
V_{{\mathrm{{RF,load}}}} \approx \frac{{V_{{\mathrm{{oc}}}}}}{{2}} =
\SI{{{n(vac_load, 2)}}}{{V_{{rms}}}}.
\end{{equation}}
The corresponding RF current is
\begin{{equation}}
I_{{\mathrm{{RF}}}} = \frac{{V_{{\mathrm{{RF,load}}}}}}{{R_s}}
= \frac{{\SI{{{n(vac_load, 2)}}}{{V}}}}{{\SI{{{n(rs, 3)}}}{{\ohm}}}}
\approx \SI{{{n(iac, 2)}}}{{A_{{rms}}}}.
\end{{equation}}
For a full-wave bridge and capacitor-input DC link,
\begin{{equation}}
V_{{\mathrm{{DC,nom}}}}\approx \sqrt{{2}}V_{{\mathrm{{RF,load}}}}
\approx \SI{{{n(vdc_nom, 1)}}}{{V}},
\end{{equation}}
while the unloaded bridge can rise toward
\begin{{equation}}
V_{{\mathrm{{DC,no-load}}}}\approx \sqrt{{2}}V_{{\mathrm{{oc}}}}
\approx \SI{{{n(vdc_noload, 1)}}}{{V}}.
\end{{equation}}
The hardware should be rated against the no-load and transient value, not only
against the nominal loaded value.

\resizebox{{\textwidth}}{{!}}{{%
{diode_table}
}}

\subsection{{Recommended Rectifier Architecture}}
The preferred B-side extraction block is:
\begin{{enumerate}}
\item B4 pickup winding or tap with RF voltage probe access.
\item Optional RF matching transformer or L-match so the rectifier/DC load
reflects \SI{{{n(rs, 3)}}}{{\ohm}} to the pickup port.
\item Four-position SiC full bridge.  For each bridge position use either one
\SI{{1700}}{{V}} high-current SiC diode or two series \SI{{1200}}{{V}} SiC
diodes with balancing and snubbing.
\item RC snubber across each bridge position, initially
\SIrange{{100}}{{470}}{{pF}} C0G/film at \SI{{2}}{{kV}} or higher and
\SIrange{{10}}{{47}}{{\ohm}} non-inductive, tuned by measured ringing.
\item If series diodes are used, add static equalizers of
\SIrange{{2}}{{5}}{{M\ohm}} across each diode and keep the physical diode
layout symmetric.
\item DC-link pulse film capacitor bank.  The first-order capacitance estimate is
\begin{{equation}}
C_{{\mathrm{{dc}}}}\geq \frac{{I_{{\mathrm{{dc}}}}}}{{2f\Delta V}},
\end{{equation}}
which gives approximately \SI{{{n(c_20v*1e6, 2)}}}{{uF}} for \SI{{20}}{{Vpp}}
ripple or \SI{{{n(c_50v*1e6, 2)}}}{{uF}} for \SI{{50}}{{Vpp}} ripple at
\SI{{10}}{{kW}}.  Use low-ESL polypropylene pulse capacitors close to the bridge,
then a downstream storage/filter stage after a choke or damping network.
\item A bleeder and discharge system sized for the no-load DC value; use a
series HV resistor chain rather than one ordinary resistor.
\end{{enumerate}}

For the diode class, use fast SiC Schottky or SiC MPS devices, not ordinary
silicon rectifiers.  Candidate device families include \SI{{1200}}{{V}},
\SI{{40}}{{A}} parts such as Wolfspeed C4D40120H and Infineon IDW40G120C5B, and
\SI{{1700}}{{V}} high-voltage parts such as Microchip MSC050SDA170B.  The
article does not lock procurement to one device because package, cooling, and
availability must be checked at build time; the electrical class is the important
design constraint.

\subsection{{Why the Diode Load Must Be Matched}}
At the matched point, the DC load equivalent near the capacitor bus is
\begin{{equation}}
R_{{\mathrm{{DC}}}} \approx \frac{{V_{{\mathrm{{DC,nom}}}}^2}}{{P}}
\approx \SI{{{n(rdc_nom, 2)}}}{{\ohm}}.
\end{{equation}}
The RF source wants approximately \SI{{{n(rs, 3)}}}{{\ohm}}.  A transformer or
matching network with impedance ratio about \({n(match_ratio, 3)}\) and turns
ratio about \({n(turns_ratio, 3)}\) brings the DC load back to the desired RF
load.  Without this match, the rectifier will either underload the node and draw
little real power, or overload it and destroy the intended standing-wave
condition.

\section{{Measurement and Tuning Sequence}}
\begin{{enumerate}}
\item Measure every coil branch with an LCR meter at low level.  Record actual
L, C, ESR, and self-resonant frequency.
\item Use a VNA to measure the A1--A4 and B4--B1 ladder with the rectifier
disconnected.  Trim branch capacitors until each stage lands at its target
octave frequency.
\item Measure the AMCC orthogonal center alone.  Determine the real coupling
coefficient \(k\), loaded Q, and core-loss resistance at \SI{{128}}{{kHz}}.
\item Connect the B-side rectifier through a current-limited RF source and dummy
load.  Verify bridge waveforms, diode temperature, and DC ripple before coupling
to the full ladder.
\item Bring the MOSFET drive up in small bus-voltage steps.  At each step record
RF current, RF voltage, DC-link voltage, DC load current, spectrum, core
temperature, winding temperature, and any corona or partial-discharge signature.
\item Stop increasing power if \(k\), Q, temperature, diode ringing, or
insulation behavior deviates from the model.
\end{{enumerate}}

\section{{Interpretation of the Latest Results}}
The A/B coil ladder is internally consistent: the octave frequencies are
\SI{{16}}{{kHz}}, \SI{{32}}{{kHz}}, \SI{{64}}{{kHz}}, and \SI{{128}}{{kHz}};
the stage impedance is held at \SI{{50}}{{\ohm}} by changing per-branch L/C;
the cable occupancy matches the corrected C1--C8 rule; and the bobbin fill
values are mechanically plausible.  The Metglas center is the limiting element.
With \(k=0.08\) and \SI{{50}}{{mT}}, the matched transfer is only about
\SI{{71}}{{W}}.  A \SI{{10}}{{kW}} matched transfer at the same weak coupling
requires a \SI{{0.593}}{{T}} peak flux swing, \SI{{12}} turns, and much larger
local voltage.  Therefore the build should be developed experimentally from the
low-power, low-flux case upward; the \SI{{10}}{{kW}} point is an upper design
envelope, not a first energization point.

\section{{Conclusion}}
The latest design is a coherent modernized interpretation of the Russell
Optical Dynamo Generator drawing: eight mirrored coils, controlled cable
occupancy, constant external impedance, octave-related resonances, Litz
conductors, and an orthogonal AMCC-1000 center.  The calculations show exactly
where the difficulty lies.  The outer ladder is not copper-loss limited in the
model; the center is limited by weak orthogonal coupling, high required flux,
high voltage, core loss, and RF rectifier stress.  A successful hardware
implementation therefore depends less on adding arbitrary cable length and more
on measured coupling, matched loading, RF insulation geometry, diode snubbing,
and thermal validation.

\begin{{thebibliography}}{{9}}
\bibitem{{wolfspeed-c4d40120h}} Wolfspeed, ``C4D40120H 1200 V Silicon Carbide Schottky Diode,'' product and datasheet page, accessed 22 May 2026. \url{{https://www.wolfspeed.com/products/power/sic-schottky-diodes/1200v-silicon-carbide-schottky-diodes/c4d40120h/}}
\bibitem{{infineon-idw40g120c5b}} Infineon Technologies, ``IDW40G120C5B 1200 V CoolSiC Schottky diode,'' product page, accessed 22 May 2026. \url{{https://www.infineon.com/cms/en/product/power/diodes-thyristors/silicon-carbide-schottky-diodes/idw40g120c5b/}}
\bibitem{{microchip-msc050sda170b}} Microchip Technology, ``MSC050SDA170B 1700 V Silicon Carbide Schottky Barrier Diode,'' datasheet, accessed 22 May 2026. \url{{https://ww1.microchip.com/downloads/aemDocuments/documents/sic/ProductDocuments/DataSheets/MSC050SDA170B-SiC-Schottky-Diode-Datasheet.pdf}}
\bibitem{{st-stpsc40h12c}} STMicroelectronics, ``STPSC40H12C 1200 V power Schottky silicon carbide diode,'' datasheet/product reference, accessed 22 May 2026. \url{{https://www.st.com/en/diodes-and-rectifiers/stpsc40h12c.html}}
\end{{thebibliography}}

\end{{document}}
"""

    out = DOCS / "orthogonal_metglas_amcc1000_full_results_article_en.tex"
    out.write_text(article, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
