#!/usr/bin/env python3
"""Build new LaTeX article and Metglas experiment section for 2026-05-31 run."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
WR = REPO / "generator" / "outputs"
PWR = ROOT / "outputs_updated_coils_20260531"
DOCS = ROOT / "docs"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def tex(value: object) -> str:
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
    return "".join(repl.get(ch, ch) for ch in str(value))


def n(value: float | str, digits: int = 3) -> str:
    value = float(value)
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


def figure(path: str, caption: str, label: str, width: str = r"0.94\textwidth") -> str:
    return rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width={width}]{{{path}}}
\caption{{{caption}}}
\label{{{label}}}
\end{{figure}}
"""


def metric_map(signal_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["metric"]: row for row in signal_rows}


def first_case(rows_: list[dict[str, str]], case: str) -> dict[str, str]:
    return next(row for row in rows_ if row["case"] == case)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    summary = json.loads((PWR / "power_simulation_summary.json").read_text(encoding="utf-8"))
    cables = rows(WR / "cable_lengths.csv")
    bobbins = rows(WR / "bobbin_geometry_and_fill.csv")
    stage_imp = rows(WR / "stage_impedance_power.csv")
    segments = rows(WR / "cable_segment_lengths.csv")
    core_geom = rows(WR / "paraformer_u_core_geometry.csv")
    amcc = rows(WR / "amcc1000_128k_sweep.csv")
    signal_rows = rows(PWR / "metglas_signal_summary.csv")
    transfer = rows(PWR / "metglas_transformer_transfer_limit.csv")
    ortho = rows(PWR / "orthogonal_paraformer_10kw_cable_plan.csv")[0]
    core_dyn = rows(PWR / "core_dynamic_summary.csv")
    stage_dyn = rows(PWR / "stage_rms_watts_amps_volts_summary.csv")
    mode_rows = rows(PWR / "mode_rms_power_reactive_summary.csv")

    signals = metric_map(signal_rows)
    ua_to_ub = first_case(transfer, "dynamic_U_A_to_U_B")
    target_ua_to_ub = first_case(transfer, "target_50mT_U_A_to_U_B")
    amcc_ref = next(
        row for row in amcc
        if abs(f(row, "gap_mm") - 2.0) < 1e-9 and abs(f(row, "B_limit_T") - 0.05) < 1e-9
    )

    cable_table = table(
        ["Cable", "End-to-end active (m)", "Wound total (m)", "Equalizer (m)", "Cut +3% (m)", "Wire"],
        [
            [
                c["cable"],
                n(c["active_total_m"], 6),
                n(c["wound_total_m"], 6),
                n(c["non_inductive_equalizing_length_m"], 6),
                n(c["cut_plus_3pct_m"], 6),
                c["wire"].replace("silk-covered ", ""),
            ]
            for c in cables
        ],
        "lrrrrl",
    )

    bobbin_table = table(
        ["Stage", "f (kHz)", "Active cables", "Lengths in bobbin (m)", "Turns by cable", "Physical L match (%)"],
        [
            [
                b["stage"],
                n(f(next(s for s in stage_imp if s["stage"] == b["stage"]), "frequency_Hz") / 1000.0, 3),
                b["active_cables"],
                b["cable_lengths_in_bobbin_m"],
                b["turns_by_cable"],
                n(b["physical_parallel_to_stage_target_percent"], 9),
            ]
            for b in bobbins
        ],
        "lrllll",
    )

    seg_compact_rows = []
    for row in segments:
        seg_compact_rows.append(
            [
                row["stage"],
                row["cable"],
                n(row["segment_length_m"], 6),
                n(row["turns_on_bobbin"], 6),
                n(row["solved_physical_L_uH"], 6),
            ]
        )
    segment_table = table(
        ["Stage", "Cable", "Length (m)", "Turns", "Grover L (uH)"],
        seg_compact_rows,
        "llrrr",
    )

    stage_table = table(
        ["Stage", "f (kHz)", "Branches", "Zbranch (ohm)", "Lstage (uH)", "Lbranch (uH)", "Cbranch (nF)"],
        [
            [
                s["stage"],
                n(f(s, "frequency_Hz") / 1000.0, 3),
                s["active_cable_count"],
                n(s["branch_target_impedance_ohm"], 3),
                n(s["target_L_uH"], 6),
                n(s["branch_target_L_uH"], 6),
                n(s["branch_target_C_nF"], 6),
            ]
            for s in stage_imp
        ],
        "lrrrrrr",
    )

    metglas_signal_table = table(
        ["Metric", "RMS/mean", "Peak/limit", "Unit"],
        [[r["metric"], n(r["rms_value"], 6), n(r["peak_value"], 6), r["unit"]] for r in signal_rows],
        "lrrl",
    )

    transfer_table = table(
        ["Case", "k", "M (uH)", "Ipri (Arms)", "Voc (Vrms)", "Pmax (W)"],
        [
            [
                r["case"],
                n(r["k"], 3),
                n(r["M_uH"], 6),
                n(r["primary_I_rms_A"], 6),
                n(r["secondary_open_circuit_V_rms"], 6),
                n(r["Pmax_matched_secondary_W"], 6),
            ]
            for r in transfer
        ],
        "lrrrrr",
    )

    core_geom_table = table(
        ["Part", "Orientation", "Flux axis", "Turns", "Gap (mm)", "Lself (mH)", "XL 128 kHz (ohm)"],
        [
            [
                r["part"],
                n(r["orientation_deg_about_optical_axis"], 1),
                r["flux_axis"],
                n(r["turns_reference"], 0),
                n(r["gap_mm"], 3),
                n(r["L_self_mH"], 6),
                n(r["X_L_at_128k_ohm"], 3),
            ]
            for r in core_geom
        ],
        "lrlrrrr",
    )

    core_dyn_table = table(
        ["Mode", "I rms (A)", "I pk (A)", "Vc rms (V)", "B rms (T)", "B pk (T)", "Damping W"],
        [
            [
                r["mode"],
                n(r["sim_I_rms_A"], 6),
                n(r["sim_I_peak_A"], 6),
                n(r["capacitor_V_rms_V"], 6),
                n(r["B_rms_T"], 6),
                n(r["B_peak_T"], 6),
                n(r["dynamic_damping_loss_W"], 6),
            ]
            for r in core_dyn
        ],
        "lrrrrrr",
    )

    ortho_table = table(
        ["Quantity", "Value"],
        [
            ("Required B peak", f"{n(ortho['required_B_peak_T'], 6)} T"),
            ("Selected turns per winding", ortho["selected_turns_per_winding"]),
            ("Primary winding current", f"{n(ortho['primary_winding_I_rms_A'], 6)} Arms"),
            ("Primary winding voltage", f"{n(ortho['primary_winding_V_rms_V'], 3)} Vrms"),
            ("Secondary open-circuit voltage", f"{n(ortho['secondary_open_circuit_V_rms'], 3)} Vrms"),
            ("Matched secondary resistance", f"{n(ortho['secondary_matched_load_R_ohm'], 6)} ohm"),
            ("Matched secondary current", f"{n(ortho['secondary_matched_load_I_rms_A'], 6)} Arms"),
            ("Matched secondary power", f"{n(ortho['Pmax_matched_secondary_W'], 3)} W"),
            ("L self", f"{n(ortho['L_self_mH'], 6)} mH"),
            ("M mutual", f"{n(ortho['M_mutual_uH'], 6)} uH"),
            ("Resonance C", f"{n(ortho['C_resonance_nF'], 6)} nF"),
            ("Circulating reactive power", f"{n(ortho['circulating_reactive_MVAR_abs'], 6)} MVAR"),
            ("Parallel AWG10-equivalent bundles", ortho["selected_parallel_AWG10_equiv_Litz_bundles"]),
            ("Procurement cable, two windings", f"{n(ortho['procurement_cable_two_windings_m'], 3)} m"),
        ],
        "lr",
    )

    stage_dyn_table = table(
        ["Stage", "f (kHz)", "Psource (W)", "Qsource (VAR)", "S (VA)", "Pcopper (W)", "Qnet (VAR)"],
        [
            [
                r["stage"],
                n(f(r, "frequency_Hz") / 1000.0, 3),
                n(r["P_source_W"], 3),
                n(r["Q_source_VAR"], 3),
                n(r["S_source_VA"], 3),
                n(r["P_copper_W"], 6),
                n(r["Q_lc_net_VAR"], 6),
            ]
            for r in stage_dyn
        ],
        "lrrrrrr",
    )

    fig_currents = figure(
        "../figures_updated_coils_20260531/metglas_core_currents.png",
        r"Updated-coil Metglas $U_A$ and $U_B$ resonant currents over the final eight cycles.",
        "fig:upd-metglas-currents",
    )
    fig_voltages = figure(
        "../figures_updated_coils_20260531/metglas_core_voltages.png",
        r"Updated-coil Metglas tank voltages and the direct $U_A$ to $U_B$ mutual voltage.",
        "fig:upd-metglas-voltages",
    )
    fig_io = figure(
        "../figures_updated_coils_20260531/metglas_input_output_signals.png",
        r"Input and output monitor voltages: A4 into $U_A$, $U_B$ into B4, and direct $U_A$ to $U_B$.",
        "fig:upd-metglas-io",
    )
    fig_power = figure(
        "../figures_updated_coils_20260531/metglas_transferred_power_time.png",
        "Instantaneous mutual power exchange and net directional power in the orthogonal Metglas pair.",
        "fig:upd-metglas-power-time",
    )
    fig_sweep = figure(
        "../figures_updated_coils_20260531/metglas_transfer_power_sweep.png",
        "Matched transferable power versus orthogonal coupling coefficient k.",
        "fig:upd-metglas-transfer-sweep",
    )
    fig_stage = figure(
        "../figures_updated_coils_20260531/stage_reactive_power.png",
        "Updated-coil branch-tank reactive-power balance by stage.",
        "fig:upd-stage-reactive",
    )

    article = rf"""\documentclass[11pt]{{article}}
\usepackage[a4paper,margin=22mm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,longtable,array,graphicx,float,hyperref,siunitx,xcolor,microtype}}
\hypersetup{{colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black}}
\sisetup{{detect-all=true,per-mode=symbol}}
\setlength{{\parskip}}{{0.55em}}
\setlength{{\parindent}}{{0pt}}
\title{{Updated-Coil Dynamic Simulation of the Orthogonal Metglas AMCC-1000 Walter Russell Optical Dynamo Generator}}
\author{{Generated from \texttt{{dynamic\_power\_simulator\_updated\_coils\_20260531.py}}}}
\date{{31 May 2026}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This article reports a new dynamic simulation version for the updated eight-coil
and eight-cable Walter Russell Optical Dynamo Generator interpretation.  The
coil data are not the earlier placeholder lengths: the windings now use the
Grover-solved conductor lengths and turns.  Every C1--C8 conductor has the same
end-to-end active length, \SI{{445.293167}}{{m}}, while the wound portion on
each bobbin is the exact length required to produce the target branch
inductance.  The A/B ladder remains a constant-\SI{{50}}{{\ohm}} stage system
at octave frequencies \SI{{16}}, \SI{{32}}, \SI{{64}}, and \SI{{128}}{{kHz}}.
The orthogonal AMCC-1000 paraformer center is simulated as a separately matched
resonant magnetic subsystem.  The new simulator exports the Metglas currents,
voltages, input/output monitor signals, instantaneous power transfer, and
matched Thevenin transfer limits.
\end{{abstract}}

\section{{Updated Coil Data Used by the Simulator}}
The current simulator reads the canonical coil design CSV files from
\texttt{{walter\_russell\_optical\_dynamo\_generator/outputs}}.  The equal
cable-length rule is enforced by non-inductive equalizer lengths outside the
bobbin windows.

\resizebox{{\textwidth}}{{!}}{{%
{cable_table}
}}

\resizebox{{\textwidth}}{{!}}{{%
{bobbin_table}
}}

\resizebox{{\textwidth}}{{!}}{{%
{segment_table}
}}

\section{{Octave Impedance Model}}
For a stage with \(N_b\) active cable branches,
\begin{{align}}
f_n &= \SI{{16}}{{kHz}}\,2^{{n-1}},\\
Z_b &= N_b Z_{{\rm stage}},\qquad Z_{{\rm stage}}=\SI{{50}}{{\ohm}},\\
L_b &= \frac{{Z_b}}{{2\pi f_n}},&
C_b &= \frac{{1}}{{2\pi f_n Z_b}}.
\end{{align}}
The branches therefore change impedance while the externally observed stage
impedance remains \SI{{50}}{{\ohm}}.

\resizebox{{\textwidth}}{{!}}{{%
{stage_table}
}}

\section{{Dynamic State-Space Simulation}}
The simulator solves the coupled resonant network in time domain:
\begin{{align}}
\mathbf{{L}}\frac{{d\mathbf{{i}}}}{{dt}} &=
\mathbf{{v}}_s(t)-\mathbf{{R}}\mathbf{{i}}-\mathbf{{v}}_C,\\
\frac{{d\mathbf{{v}}_C}}{{dt}} &= \mathbf{{C}}^{{-1}}\mathbf{{i}}.
\end{{align}}
Mutual inductances are inserted directly into \(\mathbf{{L}}\).  For two modes
with self-inductances \(L_i,L_j\), the coupling element is
\begin{{equation}}
M_{{ij}} = k_{{ij}}\sqrt{{L_iL_j}}.
\end{{equation}}

\resizebox{{\textwidth}}{{!}}{{%
{stage_dyn_table}
}}

{fig_stage}

\section{{Metglas AMCC-1000 Results}}
The orthogonal AMCC-1000 center is represented by U\_A and U\_B resonators.
At the reference \SI{{2}}{{mm}} gap the small-signal model gives the following
core geometry and dynamic response.

\resizebox{{0.92\textwidth}}{{!}}{{%
{core_geom_table}
}}

\resizebox{{\textwidth}}{{!}}{{%
{core_dyn_table}
}}

\resizebox{{\textwidth}}{{!}}{{%
{metglas_signal_table}
}}

{fig_currents}
{fig_voltages}
{fig_io}
{fig_power}

\section{{Transfer Limits and Near-10 kW Orthogonal Point}}
For a sinusoidal primary current \(I_1\), the open-circuit secondary voltage is
\begin{{equation}}
V_{{2,\mathrm{{oc}}}} = \omega M I_1,
\end{{equation}}
and the matched-load Thevenin limit is
\begin{{equation}}
P_{{\max}} = \frac{{V_{{2,\mathrm{{oc}}}}^2}}{{4R_2}}.
\end{{equation}}
With \(k=0.08\), the dynamic-current U\_A to U\_B matched limit is
\SI{{{n(ua_to_ub['Pmax_matched_secondary_W'], 6)}}}{{W}}, while the \SI{{50}}{{mT}}
target-current limit is \SI{{{n(target_ua_to_ub['Pmax_matched_secondary_W'], 6)}}}{{W}}.

\resizebox{{\textwidth}}{{!}}{{%
{transfer_table}
}}

{fig_sweep}

\resizebox{{0.88\textwidth}}{{!}}{{%
{ortho_table}
}}

\section{{Interpretation}}
The updated coil values remove the former inconsistency between cable length,
turn count, and branch inductance.  The A/B ladder is now internally consistent
at the level of the lumped finite-solenoid model.  The limiting problem remains
the orthogonal Metglas transfer.  Weak coupling at \(k=0.08\) gives only a small
matched transfer under the dynamic currents, while a near-\SI{{10}}{{kW}} point
requires \SI{{0.593428}}{{T}} peak flux density, \SI{{55.917}}{{A_{{rms}}}},
\SI{{9.314}}{{kV_{{rms}}}}, and about \SI{{0.521}}{{MVAR}} of circulating
reactive power.  These are not first-energization conditions; they define an
upper experimental envelope.

\begin{{thebibliography}}{{9}}
\bibitem{{grover}} F. W. Grover, \emph{{Inductance Calculations}}, Dover Publications.
\bibitem{{dowell1966}} P. L. Dowell, ``Effects of eddy currents in transformer windings,'' \emph{{Proceedings of the IEE}}, 1966.
\bibitem{{ferreira1992}} J. A. Ferreira, ``Analytical computation of AC resistance of round and rectangular litz wire windings,'' \emph{{IEE Proceedings B}}, 1992.
\bibitem{{metglas2605sa1}} Metglas Inc., ``2605SA1 Magnetic Alloy,'' product datasheet.
\bibitem{{amcc1000}} Hitachi Metals / Metglas, ``AMCC1000 product drawing Rev.07.''
\end{{thebibliography}}

\end{{document}}
"""

    experiment = rf"""\documentclass[11pt]{{article}}
\usepackage[a4paper,margin=22mm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,array,graphicx,float,hyperref,siunitx,xcolor,microtype}}
\hypersetup{{colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black}}
\sisetup{{detect-all=true,per-mode=symbol}}
\setlength{{\parskip}}{{0.58em}}
\setlength{{\parindent}}{{0pt}}
\title{{Metglas AMCC-1000 Orthogonal Paraformer Experiment Section for the Updated-Coil Simulator}}
\author{{Walter Russell optical dynamo updated-coil simulation package}}
\date{{31 May 2026}}

\begin{{document}}
\maketitle

\begin{{abstract}}
This experiment section specifies the Metglas AMCC-1000 orthogonal paraformer
measurement and simulation protocol used in the updated-coil dynamic simulator.
It combines the physical AMCC-1000 dimensions, material assumptions, lumped
magnetic equations, resonant state-space model, and simulated waveforms.  The
purpose is to separate measured, falsifiable Metglas behavior from speculative
interpretation: the experiment must determine real coupling \(k\), loaded Q,
core loss, winding capacitance, insulation margin, and B-side extraction
behavior before any high-power operation.
\end{{abstract}}

\section{{Core Dimensions and Material Parameters}}
The AMCC-1000 class core constants used by the model are
\[
A_e=\SI{{23.0}}{{cm^2}},\quad l_e=\SI{{42.7}}{{cm}},\quad
W_a=\SI{{42.0}}{{cm^2}},\quad A_p=\SI{{966}}{{cm^4}}.
\]
The Rev.07 drawing dimensions used in the technical drawing are
\[
a=\SI{{33}}{{mm}},\ b=\SI{{40}}{{mm}},\ c=\SI{{105}}{{mm}},\
d=\SI{{85}}{{mm}},\ e=\SI{{106}}{{mm}},\ f=\SI{{171}}{{mm}},
\]
with mass \SI{{7109}}{{g}} and nominal pack factor \SI{{82}}{{\percent}}.
The Metglas 2605SA1 material assumptions are \(B_s=\SI{{1.56}}{{T}}\), small
signal \(\mu_r\approx 45000\), ribbon thickness \SI{{23}}{{\micro m}}, and
resistivity \(\rho=\SI{{1.3e-6}}{{\ohm m}}\).

\resizebox{{0.92\textwidth}}{{!}}{{%
{core_geom_table}
}}

\section{{Magnetic Circuit and Resonance Equations}}
For an explicitly gapped core, the lumped reluctance approximation is
\begin{{equation}}
\mathcal{{R}} =
\frac{{l_e}}{{\mu_0\mu_r A_e}}+\frac{{g}}{{\mu_0 A_e}},
\end{{equation}}
and therefore
\begin{{equation}}
L(N,g)=\frac{{N^2}}{{\mathcal{{R}}}}
= \frac{{\mu_0N^2A_e}}{{l_e/\mu_r+g}}.
\end{{equation}}
At resonance,
\begin{{equation}}
C_0 = \frac{{1}}{{(2\pi f_0)^2L}},\qquad X_L=2\pi f_0L.
\end{{equation}}
For sinusoidal flux density with peak \(B_p\),
\begin{{equation}}
V_{{\rm rms}} = \frac{{2\pi f N A_e B_p}}{{\sqrt{{2}}}},
\qquad
B(t)=\frac{{L i(t)}}{{N A_e}}.
\end{{equation}}
The orthogonal transfer model is
\begin{{equation}}
M=k\sqrt{{L_A L_B}},
\qquad
v_B(t)=M\frac{{di_A}}{{dt}},
\qquad
p_{{A\rightarrow B}}(t)=v_B(t)i_B(t).
\end{{equation}}
The matched-load transfer limit follows from the Thevenin result:
\begin{{equation}}
P_{{\max}} = \frac{{(\omega M I_A)^2}}{{4R_B}}.
\end{{equation}}

\section{{Experimental Method}}
\begin{{enumerate}}
\item Measure U\_A and U\_B separately with an LCR meter over frequency to
obtain \(L\), ESR, self-resonant frequency, and loaded Q.
\item Use a VNA to measure \(S_{21}\) between U\_A and U\_B at low flux.  Fit
the mutual inductance and coupling coefficient \(k=M/\sqrt{{L_AL_B}}\).
\item Repeat the measurement at several gaps around \SI{{2}}{{mm}} and at
several winding positions to quantify mechanical sensitivity.
\item Drive U\_A at \SI{{128}}{{kHz}} through an isolated, current-limited
resonant source.  Measure \(i_A(t)\), \(v_A(t)\), induced \(v_B(t)\), and core
temperature.
\item Add the B4 pickup/load network only after low-power \(k\), Q, and loss are
known.  Verify that the B-side load does not detune the A-side ladder.
\item Increase flux in small steps while logging current, voltage, spectrum,
thermal rise, and any partial-discharge signature.
\end{{enumerate}}

\section{{Simulation Results from the Updated-Coil Run}}
The updated run used the solved A/B cable lengths, including equal
\SI{{445.293167}}{{m}} end-to-end active C1--C8 cable length.  The center
simulation at \SI{{128}}{{kHz}} produced:

\resizebox{{\textwidth}}{{!}}{{%
{metglas_signal_table}
}}

\resizebox{{\textwidth}}{{!}}{{%
{transfer_table}
}}

For the dynamic U\_A to U\_B case, \(k={n(ua_to_ub['k'], 3)}\),
\(M=\SI{{{n(ua_to_ub['M_uH'], 6)}}}{{\micro H}}\),
\(I_A=\SI{{{n(ua_to_ub['primary_I_rms_A'], 6)}}}{{A_{{rms}}}}\), and
\(P_{{\max}}=\SI{{{n(ua_to_ub['Pmax_matched_secondary_W'], 6)}}}{{W}}\).
At the \SI{{50}}{{mT}} target current, the same weak coupling gives only
\SI{{{n(target_ua_to_ub['Pmax_matched_secondary_W'], 6)}}}{{W}}.  The
near-\SI{{10}}{{kW}} orthogonal design point is therefore not achieved by the
low-flux small-signal center; it is an extrapolated high-flux matched-load
condition:

\resizebox{{0.88\textwidth}}{{!}}{{%
{ortho_table}
}}

{fig_currents}
{fig_voltages}
{fig_io}
{fig_power}

\section{{Acceptance Criteria}}
The experiment passes the low-power validation stage only if the measured
resonant frequency is within the capacitor trim range, the measured \(k\) agrees
with the fitted model within the experimental uncertainty, the measured core
temperature rise is stable, and the B-side load can be reflected into the pickup
without collapsing Q.  The high-power envelope is rejected if the required flux
density forces saturation, if inter-winding voltage exceeds insulation margin,
or if the measured \(P_{{\max}}\) does not scale approximately as \(k^2B^2\)
within the safe linear region.

\begin{{thebibliography}}{{9}}
\bibitem{{grover}} F. W. Grover, \emph{{Inductance Calculations}}, Dover Publications.
\bibitem{{dowell1966}} P. L. Dowell, ``Effects of eddy currents in transformer windings,'' \emph{{Proceedings of the IEE}}, 1966.
\bibitem{{metglas2605sa1}} Metglas Inc., ``2605SA1 Magnetic Alloy,'' product datasheet.
\bibitem{{amcc1000}} Hitachi Metals / Metglas, ``AMCC1000 product drawing Rev.07.''
\end{{thebibliography}}

\end{{document}}
"""

    article_path = DOCS / "orthogonal_metglas_amcc1000_updated_coils_20260531_article_en.tex"
    experiment_path = DOCS / "metglas_amcc1000_updated_coils_experiment_section_en.tex"
    article_path.write_text(article, encoding="utf-8")
    experiment_path.write_text(experiment, encoding="utf-8")
    print(article_path)
    print(experiment_path)


if __name__ == "__main__":
    main()
