#!/usr/bin/env python3
"""Power/RMS/VAR dynamic simulator for the current AMCC-1000 design.

Outputs:
- modal RMS voltage/current/real/reactive power
- stage RMS voltage/current/W/VA/VAR
- coupled mutual power flow
- AMCC-1000 U_A/U_B maximum transferable power estimate
- dynamic figures from the simulation
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
BASE_SIM_SRC = REPO_ROOT / "dynamic_standing_wave_simulator" / "src"
sys.path.insert(0, str(BASE_SIM_SRC))

import run_dynamic_simulator as base  # noqa: E402


STAGE_ORDER = base.STAGE_ORDER


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def phasor_rms(t: np.ndarray, x: np.ndarray, f_hz: float) -> complex:
    return base.dft_phasor_peak(t, x, f_hz) / math.sqrt(2.0)


def source_phasors_rms(t: np.ndarray, modes: list[base.Mode]) -> np.ndarray:
    values = np.vstack([base.source_vector(float(tt), modes, ramp_s=0.0) for tt in t])
    return np.array([phasor_rms(t, values[:, idx], modes[idx].f_hz) for idx in range(len(modes))])


def compute_mode_power(
    modes: list[base.Mode],
    sim_result: dict[str, Any],
    source_v: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, complex]]:
    t = sim_result["t_ss"]
    i_ss = sim_result["i_ss"]
    vc_ss = sim_result["vc_ss"]

    current_phasors: dict[str, complex] = {}
    rows: list[dict[str, Any]] = []
    for idx, m in enumerate(modes):
        I = phasor_rms(t, i_ss[:, idx], m.f_hz)
        Vc = phasor_rms(t, vc_ss[:, idx], m.f_hz)
        Vs = source_v[idx]
        w = 2.0 * math.pi * m.f_hz
        x_l = w * m.L_h
        x_c = 1.0 / (w * m.C_f)
        i_abs = abs(I)
        s_source = Vs * np.conj(I)
        q_l = i_abs * i_abs * x_l
        q_c = -i_abs * i_abs * x_c
        p_dynamic = i_abs * i_abs * m.R_dynamic_ohm
        p_copper = i_abs * i_abs * m.R_copper_ohm
        current_phasors[m.name] = I
        rows.append(
            {
                "mode": m.name,
                "kind": m.kind,
                "stage": m.stage,
                "cable": m.cable,
                "frequency_Hz": m.f_hz,
                "I_rms_A": i_abs,
                "V_source_rms_V": abs(Vs),
                "V_capacitor_rms_V": abs(Vc),
                "V_inductor_rms_V": i_abs * x_l,
                "V_resistor_dynamic_rms_V": i_abs * m.R_dynamic_ohm,
                "P_source_W": float(np.real(s_source)),
                "Q_source_VAR": float(np.imag(s_source)),
                "S_source_VA": abs(s_source),
                "P_dynamic_damping_W": p_dynamic,
                "P_copper_W": p_copper,
                "Q_inductor_VAR": q_l,
                "Q_capacitor_VAR": q_c,
                "Q_lc_net_VAR": q_l + q_c,
                "X_L_ohm": x_l,
                "X_C_ohm": x_c,
                "power_factor_source": float(np.real(s_source) / max(abs(s_source), 1e-30)),
            }
        )
    return rows, current_phasors


def compute_stage_power(mode_rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    z_stage = float(cfg["stage_impedance_ohm"])
    p_nom = float(cfg["power_w"])
    v_bus = math.sqrt(p_nom * z_stage)
    for stage in STAGE_ORDER:
        parts = [r for r in mode_rows if r["kind"] == "branch" and r["stage"] == stage]
        if not parts:
            continue
        f = parts[0]["frequency_Hz"]
        # Branches are in parallel at the same stage voltage, so power sums.
        p_source = sum(float(r["P_source_W"]) for r in parts)
        q_source = sum(float(r["Q_source_VAR"]) for r in parts)
        s_source = math.hypot(p_source, q_source)
        p_dyn = sum(float(r["P_dynamic_damping_W"]) for r in parts)
        p_cu = sum(float(r["P_copper_W"]) for r in parts)
        q_l = sum(float(r["Q_inductor_VAR"]) for r in parts)
        q_c = sum(float(r["Q_capacitor_VAR"]) for r in parts)
        # Current by apparent power over nominal 50 ohm bus voltage.
        i_from_s = s_source / max(v_bus, 1e-30)
        rows.append(
            {
                "stage": stage,
                "frequency_Hz": f,
                "active_branch_count": len(parts),
                "bus_V_rms_50ohm_V": v_bus,
                "stage_I_rms_from_source_power_A": i_from_s,
                "target_I_rms_10kW_50ohm_A": math.sqrt(p_nom / z_stage),
                "P_source_W": p_source,
                "Q_source_VAR": q_source,
                "S_source_VA": s_source,
                "P_dynamic_damping_W": p_dyn,
                "P_copper_W": p_cu,
                "Q_inductor_VAR_sum": q_l,
                "Q_capacitor_VAR_sum": q_c,
                "Q_lc_net_VAR": q_l + q_c,
                "power_factor_source": p_source / max(s_source, 1e-30),
                "equivalent_impedance_from_S_ohm": v_bus / max(i_from_s, 1e-30),
            }
        )
    return rows


def compute_coupled_power(
    modes: list[base.Mode],
    L_matrix: np.ndarray,
    current_phasors: dict[str, complex],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, mi in enumerate(modes):
        for j in range(i + 1, len(modes)):
            mj = modes[j]
            M = float(L_matrix[i, j])
            if abs(M) < 1e-12:
                continue
            same_frequency = abs(mi.f_hz - mj.f_hz) <= 1e-6
            if same_frequency:
                w = 2.0 * math.pi * mi.f_hz
                Ii = current_phasors[mi.name]
                Ij = current_phasors[mj.name]
                vj_from_i = 1j * w * M * Ii
                vi_from_j = 1j * w * M * Ij
                s_i_to_j = vj_from_i * np.conj(Ij)
                s_j_to_i = vi_from_j * np.conj(Ii)
                pmax_i_to_j = (w * abs(M) * abs(Ii)) ** 2 / max(4.0 * mj.R_dynamic_ohm, 1e-30)
                pmax_j_to_i = (w * abs(M) * abs(Ij)) ** 2 / max(4.0 * mi.R_dynamic_ohm, 1e-30)
            else:
                w = 0.0
                s_i_to_j = 0.0 + 0.0j
                s_j_to_i = 0.0 + 0.0j
                pmax_i_to_j = 0.0
                pmax_j_to_i = 0.0
            rows.append(
                {
                    "from": mi.name,
                    "to": mj.name,
                    "same_frequency": same_frequency,
                    "frequency_Hz": mi.f_hz if same_frequency else "",
                    "M_uH": M * 1e6,
                    "k_effective": M / math.sqrt(mi.L_h * mj.L_h),
                    "P_from_to_W": float(np.real(s_i_to_j)),
                    "Q_from_to_VAR": float(np.imag(s_i_to_j)),
                    "S_from_to_VA": abs(s_i_to_j),
                    "P_to_from_W": float(np.real(s_j_to_i)),
                    "Q_to_from_VAR": float(np.imag(s_j_to_i)),
                    "S_to_from_VA": abs(s_j_to_i),
                    "Pmax_matched_from_to_W": pmax_i_to_j,
                    "Pmax_matched_to_from_W": pmax_j_to_i,
                    "omega_rad_s": w,
                }
            )
    return rows


def compute_metglas_transfer(
    modes: list[base.Mode],
    L_matrix: np.ndarray,
    current_phasors: dict[str, complex],
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_name = {m.name: idx for idx, m in enumerate(modes)}
    ua = by_name["U_A"]
    ub = by_name["U_B"]
    ma = modes[ua]
    mb = modes[ub]
    w = 2.0 * math.pi * ma.f_hz
    M_actual = float(L_matrix[ua, ub])
    Ia = abs(current_phasors["U_A"])
    Ib = abs(current_phasors["U_B"])
    rows = []
    for label, src, dst, I_src, M in [
        ("dynamic_U_A_to_U_B", ma, mb, Ia, M_actual),
        ("dynamic_U_B_to_U_A", mb, ma, Ib, M_actual),
        ("target_50mT_U_A_to_U_B", ma, mb, ma.target_i_rms, M_actual),
        ("target_50mT_U_B_to_U_A", mb, ma, mb.target_i_rms, M_actual),
    ]:
        v_oc = w * abs(M) * I_src
        rows.append(
            {
                "case": label,
                "frequency_Hz": src.f_hz,
                "k": M / math.sqrt(src.L_h * dst.L_h),
                "M_uH": M * 1e6,
                "primary_I_rms_A": I_src,
                "secondary_open_circuit_V_rms": v_oc,
                "secondary_R_dynamic_ohm": dst.R_dynamic_ohm,
                "Pmax_matched_secondary_W": v_oc * v_oc / max(4.0 * dst.R_dynamic_ohm, 1e-30),
                "note": "Matched resonant-load Thevenin limit for the current orthogonal Metglas coupling.",
            }
        )

    sweep_rows = []
    for k in cfg["metglas_transfer_k_values"]:
        M = float(k) * math.sqrt(ma.L_h * mb.L_h)
        for current_label, I_src in [("dynamic_U_A_I", Ia), ("target_50mT_I", ma.target_i_rms)]:
            v_oc = w * M * I_src
            sweep_rows.append(
                {
                    "k": float(k),
                    "current_case": current_label,
                    "primary_I_rms_A": I_src,
                    "M_uH": M * 1e6,
                    "secondary_open_circuit_V_rms": v_oc,
                    "Pmax_matched_secondary_W": v_oc * v_oc / max(4.0 * mb.R_dynamic_ohm, 1e-30),
                }
            )
    return rows, sweep_rows


def compute_orthogonal_10kw_paraformer_plan(
    modes: list[base.Mode],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    pcfg = cfg["orthogonal_paraformer_10kw"]
    target_p = float(pcfg["target_power_w"])
    k = float(pcfg["assumed_orthogonal_k"])
    max_i = float(pcfg["target_max_winding_current_rms_A"])
    j_target = float(pcfg["target_current_density_A_per_mm2"])
    mtl = float(pcfg["mean_turn_length_m_estimate"])
    reserve = float(pcfg["procurement_reserve"])
    awg10_area = float(pcfg["parallel_litz_awg10_equiv_bundle_area_mm2"])

    ua = next(m for m in modes if m.name == "U_A")
    n_ref = ua.turns
    b_ref = 0.05
    i_ref = ua.target_i_rms
    v_ref = 523.1938947975291
    l_ref = ua.L_h
    r_ref = ua.R_dynamic_ohm
    f = ua.f_hz
    w = 2.0 * math.pi * f

    # Pmax scales as k^2*B^2 for a fixed gap/Q Metglas resonant pair.
    p_ref_at_k = cfg.get("_metglas_target_50mT_UA_to_UB_Pmax_W")
    if p_ref_at_k is None:
        p_ref_at_k = (w * (k * l_ref) * i_ref) ** 2 / (4.0 * r_ref)
    b_required = b_ref * math.sqrt(target_p / p_ref_at_k)

    n_min_for_current = n_ref * i_ref * (b_required / b_ref) / max_i
    n_selected = math.ceil(n_min_for_current)
    if n_selected < 1:
        n_selected = 1

    i_primary = i_ref * (b_required / b_ref) * (n_ref / n_selected)
    v_primary = v_ref * (b_required / b_ref) * (n_selected / n_ref)
    l_selected = l_ref * (n_selected / n_ref) ** 2
    r_dynamic = r_ref * (n_selected / n_ref) ** 2
    x_l = w * l_selected
    c_res = 1.0 / (w * w * l_selected)
    m_selected = k * l_selected
    v_secondary_oc = w * m_selected * i_primary
    pmax = v_secondary_oc * v_secondary_oc / (4.0 * r_dynamic)
    secondary_matched_r = r_dynamic
    secondary_load_current = v_secondary_oc / (2.0 * secondary_matched_r)
    q_l = i_primary * i_primary * x_l
    q_c = -q_l
    area_needed = i_primary / j_target
    parallel_bundles = math.ceil(area_needed / awg10_area)
    copper_area = parallel_bundles * awg10_area
    current_density = i_primary / copper_area
    cable_per_parallel = n_selected * mtl
    cable_per_winding_active = cable_per_parallel * parallel_bundles
    cable_per_winding_buy = cable_per_winding_active * (1.0 + reserve)
    total_two_windings_buy = 2.0 * cable_per_winding_buy
    matching_ratio_to_50 = 50.0 / secondary_matched_r
    matching_turns_ratio_to_50 = math.sqrt(matching_ratio_to_50)

    return [
        {
            "scenario": "orthogonal_k_0p08_near_10kW",
            "target_power_W": target_p,
            "frequency_Hz": f,
            "assumed_k": k,
            "gap_mm": pcfg["gap_mm"],
            "required_B_peak_T": b_required,
            "selected_turns_per_winding": n_selected,
            "primary_winding_I_rms_A": i_primary,
            "primary_winding_V_rms_V": v_primary,
            "secondary_open_circuit_V_rms": v_secondary_oc,
            "secondary_matched_load_R_ohm": secondary_matched_r,
            "secondary_matched_load_I_rms_A": secondary_load_current,
            "Pmax_matched_secondary_W": pmax,
            "L_self_mH": l_selected * 1e3,
            "M_mutual_uH": m_selected * 1e6,
            "X_L_ohm": x_l,
            "C_resonance_nF": c_res * 1e9,
            "Q_inductor_VAR": q_l,
            "Q_capacitor_VAR": q_c,
            "circulating_reactive_MVAR_abs": abs(q_l) / 1e6,
            "target_current_density_A_per_mm2": j_target,
            "required_copper_area_mm2": area_needed,
            "selected_parallel_AWG10_equiv_Litz_bundles": parallel_bundles,
            "selected_copper_area_mm2": copper_area,
            "actual_current_density_A_per_mm2": current_density,
            "mean_turn_length_m_estimate": mtl,
            "active_cable_per_parallel_bundle_m": cable_per_parallel,
            "active_cable_per_winding_all_parallel_m": cable_per_winding_active,
            "procurement_cable_per_winding_m": cable_per_winding_buy,
            "procurement_cable_two_windings_m": total_two_windings_buy,
            "matching_impedance_ratio_to_50ohm": matching_ratio_to_50,
            "matching_turns_ratio_to_50ohm": matching_turns_ratio_to_50,
            "warning": "Near-10 kW with orthogonal k=0.08 requires high B and very high circulating VAR; validate core loss and insulation before hardware.",
        }
    ]


def simple_bar_plot(path: Path, labels: list[str], series: list[tuple[str, list[float], tuple[int, int, int]]], title: str, y_label: str) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1400, 820), "white")
    draw = ImageDraw.Draw(img)
    font = base.load_font(14)
    title_font = base.load_font(18)
    box = (95, 80, 1340, 700)
    draw.rectangle(box, outline=(30, 30, 30), width=2)
    draw.text((95, 28), title, fill=(10, 35, 70), font=title_font)
    draw.text((20, 370), y_label, fill=(0, 0, 0), font=font)
    max_y = max(max(abs(v) for v in vals) for _, vals, _ in series) * 1.18
    min_y = min(0.0, min(min(v for v in vals) for _, vals, _ in series) * 1.18)
    span = max(max_y - min_y, 1e-9)
    group_w = (box[2] - box[0]) / len(labels)
    bar_w = group_w / (len(series) + 1.2)
    zero_y = box[3] - (0.0 - min_y) / span * (box[3] - box[1])
    draw.line((box[0], zero_y, box[2], zero_y), fill=(80, 80, 80), width=1)
    for gy in np.linspace(0, 1, 6):
        y = box[1] + gy * (box[3] - box[1])
        draw.line((box[0], y, box[2], y), fill=(226, 226, 226), width=1)
    for i, label in enumerate(labels):
        x_base = box[0] + i * group_w + group_w * 0.12
        for sidx, (_name, values, color) in enumerate(series):
            value = values[i]
            x0 = x_base + sidx * bar_w
            y = box[3] - (value - min_y) / span * (box[3] - box[1])
            draw.rectangle((x0, min(y, zero_y), x0 + bar_w * 0.85, max(y, zero_y)), fill=color)
        draw.text((x_base, box[3] + 12), label, fill=(0, 0, 0), font=font)
    lx = box[0] + 15
    for name, _values, color in series:
        draw.rectangle((lx, box[1] + 16, lx + 22, box[1] + 30), fill=color)
        draw.text((lx + 30, box[1] + 10), name, fill=(0, 0, 0), font=font)
        lx += 210
    img.save(path)


def metglas_line_plot(
    path: Path,
    series: list[tuple[str, np.ndarray, np.ndarray, tuple[int, int, int]]],
    title: str,
    xlab: str,
    ylab: str,
    size: tuple[int, int] = (1280, 760),
) -> None:
    """Line plot variant with numeric tick labels for measurement-grade Metglas figures."""

    from PIL import Image, ImageDraw

    def tick_text(value: float) -> str:
        if abs(value) < 1e-12:
            return "0"
        if abs(value) >= 10000.0 or abs(value) < 0.01:
            return f"{value:.2e}"
        if abs(value) >= 1000.0:
            return f"{value:.0f}"
        return f"{value:.3g}"

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = base.load_font(13)
    small = base.load_font(11)
    title_font = base.load_font(17)
    box = (118, 78, size[0] - 58, size[1] - 112)

    xs_all = np.concatenate([s[1] for s in series])
    ys_all = np.concatenate([s[2] for s in series])
    xmin, xmax = float(xs_all.min()), float(xs_all.max())
    ymin, ymax = float(ys_all.min()), float(ys_all.max())
    ypad = 0.08 * max(ymax - ymin, 1e-9)
    xpad = 0.015 * max(xmax - xmin, 1e-9)
    ymin -= ypad
    ymax += ypad
    xmin -= xpad
    xmax += xpad

    draw.rectangle(box, outline=(30, 30, 30), width=2)
    draw.text((box[0], 24), title, fill=(10, 35, 70), font=title_font)
    xlab_bbox = draw.textbbox((0, 0), xlab, font=font)
    draw.text(((box[0] + box[2] - (xlab_bbox[2] - xlab_bbox[0])) / 2, size[1] - 42), xlab, fill=(0, 0, 0), font=font)
    draw.text((16, (box[1] + box[3]) / 2 - 10), ylab, fill=(0, 0, 0), font=font)

    for frac in np.linspace(0.0, 1.0, 6):
        y = box[3] - frac * (box[3] - box[1])
        value = ymin + frac * (ymax - ymin)
        draw.line((box[0], y, box[2], y), fill=(226, 226, 226), width=1)
        label = tick_text(value)
        label_box = draw.textbbox((0, 0), label, font=small)
        draw.text((box[0] - 10 - (label_box[2] - label_box[0]), y - 7), label, fill=(0, 0, 0), font=small)
    for frac in np.linspace(0.0, 1.0, 6):
        x = box[0] + frac * (box[2] - box[0])
        value = xmin + frac * (xmax - xmin)
        draw.line((x, box[1], x, box[3]), fill=(238, 238, 238), width=1)
        label = tick_text(value)
        label_box = draw.textbbox((0, 0), label, font=small)
        draw.text((x - (label_box[2] - label_box[0]) / 2, box[3] + 10), label, fill=(0, 0, 0), font=small)

    legend_x = box[0] + 14
    legend_y = box[1] + 12
    for label, xs, ys, color in series:
        points = [base.map_point(float(x), float(y), xmin, xmax, ymin, ymax, box) for x, y in zip(xs, ys)]
        if len(points) >= 2:
            draw.line(points, fill=color, width=3)
        draw.rectangle((legend_x, legend_y + 3, legend_x + 24, legend_y + 13), fill=color)
        draw.text((legend_x + 32, legend_y), label, fill=(0, 0, 0), font=font)
        legend_y += 22

    img.save(path)


def metglas_dynamic_signals(
    modes: list[base.Mode],
    L_matrix: np.ndarray,
    result: dict[str, Any],
    transfer_rows: list[dict[str, Any]],
    out_dir: Path,
    fig_dir: Path,
    cycles: float = 8.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract Metglas-centered time-domain signals and power exchange.

    The modal equation is L*dI/dt = Vs - R*I - Vc.  For the orthogonal
    AMCC-1000 pair, the direct U_A/U_B induced voltages are computed from
    v = M*dI/dt.  A4->U_A and U_B->B4 are also reported as practical
    input/output monitor points for the center assembly.
    """

    by_name = {m.name: idx for idx, m in enumerate(modes)}
    ua = by_name["U_A"]
    ub = by_name["U_B"]
    t = np.asarray(result["t_ss"], dtype=float)
    currents = np.asarray(result["i_ss"], dtype=float)
    caps = np.asarray(result["vc_ss"], dtype=float)
    di_dt = np.gradient(currents, t, axis=0, edge_order=2)

    m_ua_ub = float(L_matrix[ua, ub])
    v_ub_from_ua = m_ua_ub * di_dt[:, ua]
    v_ua_from_ub = m_ua_ub * di_dt[:, ub]

    a4_idxs = [idx for idx, m in enumerate(modes) if m.kind == "branch" and m.stage == "A4"]
    b4_idxs = [idx for idx, m in enumerate(modes) if m.kind == "branch" and m.stage == "B4"]
    if a4_idxs:
        v_input_a4_to_ua = np.sum(L_matrix[ua, a4_idxs] * di_dt[:, a4_idxs], axis=1)
    else:
        v_input_a4_to_ua = np.zeros_like(t)
    if b4_idxs:
        v_output_ub_to_b4 = np.sum(L_matrix[b4_idxs, ub]) * di_dt[:, ub]
    else:
        v_output_ub_to_b4 = np.zeros_like(t)

    p_ua_to_ub = v_ub_from_ua * currents[:, ub]
    p_ub_to_ua = v_ua_from_ub * currents[:, ua]
    p_net_ua_to_ub = p_ua_to_ub - p_ub_to_ua

    f_core = modes[ua].f_hz
    t0 = t[-1] - cycles / f_core
    mask = t >= t0
    tw = t[mask]
    x_us = (tw - tw[0]) * 1e6

    waveform_rows: list[dict[str, Any]] = []
    for local_idx, global_idx in enumerate(np.flatnonzero(mask)):
        waveform_rows.append(
            {
                "time_s": float(t[global_idx]),
                "time_us_relative": float(x_us[local_idx]),
                "I_U_A_A": float(currents[global_idx, ua]),
                "I_U_B_A": float(currents[global_idx, ub]),
                "V_cap_U_A_V": float(caps[global_idx, ua]),
                "V_cap_U_B_V": float(caps[global_idx, ub]),
                "V_direct_U_B_from_U_A_V": float(v_ub_from_ua[global_idx]),
                "V_direct_U_A_from_U_B_V": float(v_ua_from_ub[global_idx]),
                "V_input_A4_to_U_A_V": float(v_input_a4_to_ua[global_idx]),
                "V_output_U_B_to_B4_V": float(v_output_ub_to_b4[global_idx]),
                "P_inst_U_A_to_U_B_W": float(p_ua_to_ub[global_idx]),
                "P_inst_U_B_to_U_A_W": float(p_ub_to_ua[global_idx]),
                "P_inst_net_U_A_to_U_B_W": float(p_net_ua_to_ub[global_idx]),
            }
        )

    def rms_window(x: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(x[mask]))))

    b_ua = modes[ua].L_h * currents[:, ua] / max(modes[ua].turns * modes[ua].ae_m2, 1e-30)
    b_ub = modes[ub].L_h * currents[:, ub] / max(modes[ub].turns * modes[ub].ae_m2, 1e-30)
    transfer_lookup = {r["case"]: r for r in transfer_rows}
    signal_rows = [
        {
            "metric": "U_A_core_current",
            "frequency_Hz": f_core,
            "rms_value": rms_window(currents[:, ua]),
            "peak_value": float(np.max(np.abs(currents[mask, ua]))),
            "unit": "A",
            "note": "Simulated U_A Metglas resonant-mode current.",
        },
        {
            "metric": "U_B_core_current",
            "frequency_Hz": f_core,
            "rms_value": rms_window(currents[:, ub]),
            "peak_value": float(np.max(np.abs(currents[mask, ub]))),
            "unit": "A",
            "note": "Simulated U_B Metglas resonant-mode current.",
        },
        {
            "metric": "U_A_capacitor_voltage",
            "frequency_Hz": f_core,
            "rms_value": rms_window(caps[:, ua]),
            "peak_value": float(np.max(np.abs(caps[mask, ua]))),
            "unit": "V",
            "note": "Modal resonant capacitor voltage in the U_A tank.",
        },
        {
            "metric": "U_B_capacitor_voltage",
            "frequency_Hz": f_core,
            "rms_value": rms_window(caps[:, ub]),
            "peak_value": float(np.max(np.abs(caps[mask, ub]))),
            "unit": "V",
            "note": "Modal resonant capacitor voltage in the U_B tank.",
        },
        {
            "metric": "U_A_flux_density",
            "frequency_Hz": f_core,
            "rms_value": rms_window(b_ua),
            "peak_value": float(np.max(np.abs(b_ua[mask]))),
            "unit": "T",
            "note": "Computed from B=L*I/(N*Ae) using Ae=23.0 cm^2 and the simulated current.",
        },
        {
            "metric": "U_B_flux_density",
            "frequency_Hz": f_core,
            "rms_value": rms_window(b_ub),
            "peak_value": float(np.max(np.abs(b_ub[mask]))),
            "unit": "T",
            "note": "Computed from B=L*I/(N*Ae) using Ae=23.0 cm^2 and the simulated current.",
        },
        {
            "metric": "direct_U_A_to_U_B_mutual_voltage",
            "frequency_Hz": f_core,
            "rms_value": rms_window(v_ub_from_ua),
            "peak_value": float(np.max(np.abs(v_ub_from_ua[mask]))),
            "unit": "V",
            "note": "v_UB<-UA = M_UAUB*dI_UA/dt.",
        },
        {
            "metric": "input_A4_to_U_A_mutual_voltage",
            "frequency_Hz": f_core,
            "rms_value": rms_window(v_input_a4_to_ua),
            "peak_value": float(np.max(np.abs(v_input_a4_to_ua[mask]))),
            "unit": "V",
            "note": "Summed A4 branch mutual voltage into U_A.",
        },
        {
            "metric": "output_U_B_to_B4_mutual_voltage",
            "frequency_Hz": f_core,
            "rms_value": rms_window(v_output_ub_to_b4),
            "peak_value": float(np.max(np.abs(v_output_ub_to_b4[mask]))),
            "unit": "V",
            "note": "Summed induced voltage from U_B into the B4 branch set.",
        },
        {
            "metric": "actual_average_U_A_to_U_B_power",
            "frequency_Hz": f_core,
            "rms_value": float(np.mean(p_ua_to_ub[mask])),
            "peak_value": float(np.max(np.abs(p_ua_to_ub[mask]))),
            "unit": "W",
            "note": "Time-average of v_UB<-UA(t)*i_UB(t) in the simulated dynamic state.",
        },
        {
            "metric": "actual_average_net_U_A_to_U_B_power",
            "frequency_Hz": f_core,
            "rms_value": float(np.mean(p_net_ua_to_ub[mask])),
            "peak_value": float(np.max(np.abs(p_net_ua_to_ub[mask]))),
            "unit": "W",
            "note": "Average directional imbalance p_UA->UB - p_UB->UA in the simulated dynamic state.",
        },
        {
            "metric": "matched_thevenin_U_A_to_U_B_limit",
            "frequency_Hz": f_core,
            "rms_value": float(transfer_lookup["dynamic_U_A_to_U_B"]["Pmax_matched_secondary_W"]),
            "peak_value": float(transfer_lookup["target_50mT_U_A_to_U_B"]["Pmax_matched_secondary_W"]),
            "unit": "W",
            "note": "RMS value is dynamic-current matched limit; peak_value column stores the 50 mT target-current matched limit.",
        },
    ]

    write_csv(out_dir / "metglas_dynamic_waveforms.csv", waveform_rows)
    write_csv(out_dir / "metglas_signal_summary.csv", signal_rows)

    fig_dir.mkdir(parents=True, exist_ok=True)
    metglas_line_plot(
        fig_dir / "metglas_core_currents.png",
        [
            ("U_A current", x_us, currents[mask, ua], (45, 115, 185)),
            ("U_B current", x_us, currents[mask, ub], (220, 135, 45)),
        ],
        "Metglas AMCC-1000 core currents, last 8 cycles at 128 kHz",
        "time (us)",
        "current (A)",
    )
    metglas_line_plot(
        fig_dir / "metglas_core_voltages.png",
        [
            ("U_A tank voltage", x_us, caps[mask, ua], (45, 115, 185)),
            ("U_B tank voltage", x_us, caps[mask, ub], (220, 135, 45)),
            ("U_B from U_A mutual", x_us, v_ub_from_ua[mask], (120, 80, 170)),
        ],
        "Metglas AMCC-1000 tank and mutual voltages",
        "time (us)",
        "voltage (V)",
    )
    metglas_line_plot(
        fig_dir / "metglas_input_output_signals.png",
        [
            ("input A4 -> U_A", x_us, v_input_a4_to_ua[mask], (45, 115, 185)),
            ("output U_B -> B4", x_us, v_output_ub_to_b4[mask], (220, 135, 45)),
            ("direct U_A -> U_B", x_us, v_ub_from_ua[mask], (85, 155, 90)),
        ],
        "Metglas input/output induced-voltage monitor signals",
        "time (us)",
        "voltage (V)",
    )
    metglas_line_plot(
        fig_dir / "metglas_transferred_power_time.png",
        [
            ("U_A -> U_B", x_us, p_ua_to_ub[mask], (45, 115, 185)),
            ("U_B -> U_A", x_us, p_ub_to_ua[mask], (220, 135, 45)),
            ("net U_A -> U_B", x_us, p_net_ua_to_ub[mask], (130, 80, 170)),
        ],
        "Metglas instantaneous mutual power exchange",
        "time (us)",
        "power (W)",
    )
    return waveform_rows, signal_rows


def make_figures(
    modes: list[base.Mode],
    L_matrix: np.ndarray,
    sim_base_result: dict[str, Any],
    result: dict[str, Any],
    mode_rows: list[dict[str, Any]],
    stage_rows: list[dict[str, Any]],
    transfer_rows: list[dict[str, Any]],
    sweep_rows: list[dict[str, Any]],
    paraformer_plan_rows: list[dict[str, Any]],
    out_dir: Path,
    fig_dir: Path,
    dyn_cfg: dict[str, Any],
) -> None:
    sw_rows = base.standing_wave_rows(modes, result, dyn_cfg, out_dir)
    base.save_stage_bar_plot(fig_dir / "dynamic_stage_currents.png", result["stage_rows"])
    base.save_standing_wave_plot(fig_dir / "dynamic_standing_wave_map.png", sw_rows)
    base.save_spectrum_plot(fig_dir / "dynamic_harmonic_spectrum.png", result["spectrum_rows"])
    base.save_core_lissajous(fig_dir / "dynamic_core_flux_lissajous.png", modes, result)
    base.save_standing_wave_gif(fig_dir / "dynamic_standing_wave_animation.gif", sw_rows, frames=int(dyn_cfg["gif_frames"]))

    labels = [r["stage"] for r in stage_rows]
    simple_bar_plot(
        fig_dir / "stage_rms_current_voltage.png",
        labels,
        [
            ("I rms A", [float(r["stage_I_rms_from_source_power_A"]) for r in stage_rows], (45, 115, 185)),
            ("V bus rms / 50", [float(r["bus_V_rms_50ohm_V"]) / 50.0 for r in stage_rows], (220, 135, 45)),
        ],
        "RMS current and bus voltage scale by stage",
        "A, V/50",
    )
    simple_bar_plot(
        fig_dir / "stage_real_power.png",
        labels,
        [
            ("P source W", [float(r["P_source_W"]) for r in stage_rows], (45, 115, 185)),
            ("P damping W", [float(r["P_dynamic_damping_W"]) for r in stage_rows], (85, 155, 90)),
            ("P copper W", [float(r["P_copper_W"]) for r in stage_rows], (210, 80, 65)),
        ],
        "RMS real power by stage",
        "W",
    )
    simple_bar_plot(
        fig_dir / "stage_reactive_power.png",
        labels,
        [
            ("Q L kVAR", [float(r["Q_inductor_VAR_sum"]) / 1000.0 for r in stage_rows], (45, 115, 185)),
            ("Q C kVAR", [float(r["Q_capacitor_VAR_sum"]) / 1000.0 for r in stage_rows], (220, 135, 45)),
            ("Q net kVAR", [float(r["Q_lc_net_VAR"]) / 1000.0 for r in stage_rows], (130, 80, 170)),
        ],
        "Reactive power by stage",
        "kVAR",
    )

    k_dyn = [float(r["k"]) for r in sweep_rows if r["current_case"] == "dynamic_U_A_I"]
    p_dyn = [float(r["Pmax_matched_secondary_W"]) for r in sweep_rows if r["current_case"] == "dynamic_U_A_I"]
    p_target = [float(r["Pmax_matched_secondary_W"]) for r in sweep_rows if r["current_case"] == "target_50mT_I"]
    base.save_line_plot(
        fig_dir / "metglas_transfer_power_sweep.png",
        [
            ("dynamic core current", np.array(k_dyn), np.array(p_dyn), (45, 115, 185)),
            ("50 mT target current", np.array(k_dyn), np.array(p_target), (220, 135, 45)),
        ],
        "AMCC-1000 maximum transferable matched power vs coupling k",
        "coupling k",
        "Pmax W",
    )

    if paraformer_plan_rows:
        p = paraformer_plan_rows[0]
        simple_bar_plot(
            fig_dir / "orthogonal_paraformer_10kw_design.png",
            ["B T", "I/100 A", "V/10kV", "Q/1MVAR", "cable/100m"],
            [
                (
                    "10 kW orthogonal design",
                    [
                        float(p["required_B_peak_T"]),
                        float(p["primary_winding_I_rms_A"]) / 100.0,
                        float(p["primary_winding_V_rms_V"]) / 10000.0,
                        float(p["circulating_reactive_MVAR_abs"]),
                        float(p["procurement_cable_two_windings_m"]) / 100.0,
                    ],
                    (45, 115, 185),
                )
            ],
            "Orthogonal Metglas k=0.08 paraformer near-10kW cable design",
            "scaled units",
        )


def run(config_path: Path, out_dir: Path, fig_dir: Path) -> dict[str, Any]:
    cfg = read_json(config_path)
    dyn_cfg = read_json((ROOT / cfg["base_dynamic_config"]).resolve())
    dyn_cfg["power_w"] = cfg["power_w"]
    dyn_cfg["stage_impedance_ohm"] = cfg["stage_impedance_ohm"]
    input_dir = (ROOT / cfg["input_outputs_dir"]).resolve()
    cable_lengths_path = input_dir / "cable_lengths.csv"
    if cable_lengths_path.exists():
        cable_rows = base.read_csv_rows(cable_lengths_path)
        dyn_cfg["standing_wave_length_m"] = max(base.fnum(row, "active_total_m") for row in cable_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    modes = base.build_modes(dyn_cfg, input_dir)
    L_matrix, coupling_rows, coupling_scale = base.build_coupling_matrix(modes, dyn_cfg)
    sim = base.integrate(modes, L_matrix, dyn_cfg)
    base_result = base.summarize(modes, sim, L_matrix, out_dir, dyn_cfg)

    t = base_result["t_ss"]
    source_v = source_phasors_rms(t, modes)
    mode_rows, current_phasors = compute_mode_power(modes, base_result, source_v)
    stage_rows = compute_stage_power(mode_rows, dyn_cfg)
    coupled_rows = compute_coupled_power(modes, L_matrix, current_phasors)
    transfer_rows, sweep_rows = compute_metglas_transfer(modes, L_matrix, current_phasors, cfg)
    cfg["_metglas_target_50mT_UA_to_UB_Pmax_W"] = transfer_rows[2]["Pmax_matched_secondary_W"]
    paraformer_plan_rows = compute_orthogonal_10kw_paraformer_plan(modes, cfg)
    metglas_waveform_rows, metglas_signal_rows = metglas_dynamic_signals(
        modes,
        L_matrix,
        base_result,
        transfer_rows,
        out_dir,
        fig_dir,
    )

    write_csv(out_dir / "mode_rms_power_reactive_summary.csv", mode_rows)
    write_csv(out_dir / "stage_rms_watts_amps_volts_summary.csv", stage_rows)
    write_csv(out_dir / "coupled_mutual_power_flow.csv", coupled_rows)
    write_csv(out_dir / "metglas_transformer_transfer_limit.csv", transfer_rows)
    write_csv(out_dir / "metglas_transformer_transfer_sweep.csv", sweep_rows)
    write_csv(out_dir / "orthogonal_paraformer_10kw_cable_plan.csv", paraformer_plan_rows)
    write_csv(out_dir / "coupling_matrix_used.csv", coupling_rows)

    make_figures(
        modes,
        L_matrix,
        sim,
        base_result,
        mode_rows,
        stage_rows,
        transfer_rows,
        sweep_rows,
        paraformer_plan_rows,
        out_dir,
        fig_dir,
        dyn_cfg,
    )

    summary = {
        "mode_count": len(modes),
        "power_w": cfg["power_w"],
        "coupling_offdiagonal_scale": coupling_scale,
        "metglas_dynamic_UA_to_UB_Pmax_W": transfer_rows[0]["Pmax_matched_secondary_W"],
        "metglas_target_50mT_UA_to_UB_Pmax_W": transfer_rows[2]["Pmax_matched_secondary_W"],
        "metglas_k_0p95_target_50mT_Pmax_W": next(
            r["Pmax_matched_secondary_W"]
            for r in sweep_rows
            if abs(r["k"] - 0.95) < 1e-12 and r["current_case"] == "target_50mT_I"
        ),
        "orthogonal_k_0p08_required_B_for_10kW_T": paraformer_plan_rows[0]["required_B_peak_T"],
        "orthogonal_k_0p08_selected_turns": paraformer_plan_rows[0]["selected_turns_per_winding"],
        "orthogonal_k_0p08_primary_I_rms_A": paraformer_plan_rows[0]["primary_winding_I_rms_A"],
        "orthogonal_k_0p08_primary_V_rms_V": paraformer_plan_rows[0]["primary_winding_V_rms_V"],
        "orthogonal_k_0p08_procurement_cable_two_windings_m": paraformer_plan_rows[0]["procurement_cable_two_windings_m"],
        "metglas_waveform_sample_count": len(metglas_waveform_rows),
        "metglas_signal_summary_count": len(metglas_signal_rows),
        "metglas_actual_average_UA_to_UB_power_W": next(
            r["rms_value"] for r in metglas_signal_rows if r["metric"] == "actual_average_U_A_to_U_B_power"
        ),
        "metglas_actual_average_net_UA_to_UB_power_W": next(
            r["rms_value"] for r in metglas_signal_rows if r["metric"] == "actual_average_net_U_A_to_U_B_power"
        ),
        "total_stage_source_W": sum(float(r["P_source_W"]) for r in stage_rows),
        "total_stage_copper_W": sum(float(r["P_copper_W"]) for r in stage_rows),
        "outputs_dir": str(out_dir),
        "figures_dir": str(fig_dir),
    }
    write_json(out_dir / "power_simulation_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "default_config.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--fig-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()
    summary = run(args.config, args.out_dir, args.fig_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
