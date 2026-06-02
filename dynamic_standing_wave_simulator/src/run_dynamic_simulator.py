#!/usr/bin/env python3
"""Dynamic simulator for the AMCC-1000 Walter Russell optical dynamo model.

The simulator is intentionally conservative: it uses coupled RLC modes,
measured/design CSV values, explicit mutual inductance coefficients, and a
distributed-line standing-wave postprocessor. It does not assume any nonstandard
energy source.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


C0 = 299_792_458.0
MU0 = 4.0 * math.pi * 1e-7
ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_CONFIG = ROOT / "config" / "default_config.json"

STAGE_ORDER = ["A1", "A2", "A3", "A4", "B4", "B3", "B2", "B1"]
STAGE_POSITION = {
    "A1": -3.5,
    "A2": -2.5,
    "A3": -1.5,
    "A4": -0.5,
    "B4": 0.5,
    "B3": 1.5,
    "B2": 2.5,
    "B1": 3.5,
}
MIRROR = {"A1": "B1", "A2": "B2", "A3": "B3", "A4": "B4", "B4": "A4", "B3": "A3", "B2": "A2", "B1": "A1"}


@dataclass
class Mode:
    name: str
    kind: str
    stage: str
    cable: str
    f_hz: float
    omega: float
    L_h: float
    C_f: float
    R_copper_ohm: float
    R_dynamic_ohm: float
    target_i_rms: float
    z_branch_ohm: float
    drive_v_peak: float
    drive_phase_rad: float
    turns: float = 0.0
    ae_m2: float = 0.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fnum(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw is None or raw == "":
        return default
    return float(raw)


def stage_drive_phase(stage: str, frequency_hz: float, base_hz: float) -> float:
    """Spatial standing-wave phase for the octave ladder across the device."""
    x_min = min(STAGE_POSITION.values())
    x_max = max(STAGE_POSITION.values())
    x_norm = (STAGE_POSITION[stage] - x_min) / (x_max - x_min)
    mode = max(1, int(round(frequency_hz / base_hz)))
    return mode * math.pi * x_norm


def build_modes(cfg: dict[str, Any], input_dir: Path) -> list[Mode]:
    branch_rows = read_csv_rows(input_dir / "branch_lc_tuning_plan.csv")
    core_rows = read_csv_rows(input_dir / "paraformer_u_core_geometry.csv")
    amcc_rows = read_csv_rows(input_dir / "amcc1000_128k_sweep.csv")

    power_w = float(cfg["power_w"])
    z_stage = float(cfg["stage_impedance_ohm"])
    base_hz = float(cfg["base_frequency_hz"])
    loaded_q = float(cfg["loaded_q"])
    drive_mode = str(cfg["drive_mode"])
    stage_i_rms = math.sqrt(power_w / z_stage)

    modes: list[Mode] = []
    for row in branch_rows:
        stage = row["stage"]
        cable = row["cable"]
        f_hz = fnum(row, "frequency_Hz")
        active_count = int(fnum(row, "active_branch_count", 1.0))
        z_branch = fnum(row, "branch_target_impedance_ohm")
        L_h = fnum(row, "branch_target_L_uH") * 1e-6
        C_f = fnum(row, "branch_target_C_nF") * 1e-9
        R_cu = fnum(row, "Rac_60C_ohm")

        # The matching network maps the 50 ohm power bus into a higher-Q tank.
        # R_dynamic is the loaded damping seen by the modal equation; copper
        # loss remains separately computable from R_copper.
        R_dynamic = max(z_branch / loaded_q, 5.0 * R_cu)
        target_i_rms = stage_i_rms / active_count
        target_i_peak = math.sqrt(2.0) * target_i_rms
        drive_v_peak = target_i_peak * R_dynamic

        if drive_mode == "a1_only":
            if stage != "A1":
                drive_v_peak = 0.0
        elif drive_mode == "a1_with_octave_synthesis":
            octave = max(1.0, f_hz / base_hz)
            if stage == "A1":
                drive_v_peak *= 1.0
            elif stage.startswith("A"):
                drive_v_peak *= 0.35 / math.sqrt(octave)
            else:
                drive_v_peak *= 0.18 / math.sqrt(octave)
        elif drive_mode != "matched_octave_ladder":
            raise ValueError(f"Unknown drive_mode: {drive_mode}")

        modes.append(
            Mode(
                name=f"{stage}_{cable}",
                kind="branch",
                stage=stage,
                cable=cable,
                f_hz=f_hz,
                omega=2.0 * math.pi * f_hz,
                L_h=L_h,
                C_f=C_f,
                R_copper_ohm=R_cu,
                R_dynamic_ohm=R_dynamic,
                target_i_rms=target_i_rms,
                z_branch_ohm=z_branch,
                drive_v_peak=drive_v_peak,
                drive_phase_rad=stage_drive_phase(stage, f_hz, base_hz),
            )
        )

    # Use the AMCC 2 mm gap, 50 mT row as the core reference.
    core_ref = None
    for row in amcc_rows:
        if abs(fnum(row, "gap_mm") - 2.0) < 1e-9 and abs(fnum(row, "B_limit_T") - 0.05) < 1e-9:
            core_ref = row
            break
    if core_ref is None:
        core_ref = amcc_rows[0]

    ae_m2 = 23.0e-4
    core_q = float(cfg["core_loaded_q"])
    for row in core_rows:
        f_hz = float(cfg["max_frequency_hz"])
        L_h = fnum(row, "L_self_mH") * 1e-3
        C_f = 1.0 / ((2.0 * math.pi * f_hz) ** 2 * L_h)
        x_l = 2.0 * math.pi * f_hz * L_h
        modes.append(
            Mode(
                name=row["part"],
                kind="core",
                stage=row["part"],
                cable="E1",
                f_hz=f_hz,
                omega=2.0 * math.pi * f_hz,
                L_h=L_h,
                C_f=C_f,
                R_copper_ohm=0.0,
                R_dynamic_ohm=x_l / core_q,
                target_i_rms=fnum(core_ref, "Irms_magnetizing_at_B_limit"),
                z_branch_ohm=x_l,
                drive_v_peak=0.0,
                drive_phase_rad=0.0 if row["part"] == "U_A" else math.pi / 2.0,
                turns=fnum(row, "turns_reference"),
                ae_m2=ae_m2,
            )
        )

    return modes


def build_coupling_matrix(modes: list[Mode], cfg: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]], float]:
    kcfg = cfg["coupling"]
    n = len(modes)
    L = np.diag([m.L_h for m in modes]).astype(float)
    coupling_rows: list[dict[str, Any]] = []
    by_name = {m.name: i for i, m in enumerate(modes)}
    by_stage_cable = {(m.stage, m.cable): i for i, m in enumerate(modes) if m.kind == "branch"}
    by_stage: dict[str, list[int]] = {}
    by_cable: dict[str, list[int]] = {}
    for i, m in enumerate(modes):
        if m.kind != "branch":
            continue
        by_stage.setdefault(m.stage, []).append(i)
        by_cable.setdefault(m.cable, []).append(i)

    def add(i: int, j: int, k: float, label: str) -> None:
        if i == j or k == 0.0:
            return
        M = k * math.sqrt(modes[i].L_h * modes[j].L_h)
        L[i, j] += M
        L[j, i] += M
        coupling_rows.append(
            {
                "from": modes[i].name,
                "to": modes[j].name,
                "k": k,
                "M_uH": M * 1e6,
                "type": label,
            }
        )

    # Adjacent coil locations on the same physical cable path.
    for cable, idxs in by_cable.items():
        ordered = sorted(idxs, key=lambda idx: STAGE_ORDER.index(modes[idx].stage))
        for a, b in zip(ordered[:-1], ordered[1:]):
            add(a, b, float(kcfg["same_cable_adjacent_stage_k"]), f"same cable {cable}, adjacent stage")

    # Small co-located coupling between branches on the same bobbin.
    for stage, idxs in by_stage.items():
        for pos, i in enumerate(idxs):
            for j in idxs[pos + 1 :]:
                add(i, j, float(kcfg["same_stage_colocated_k"]), f"co-located on {stage}")

    # Mirror-pair coupling and the stronger A4/B4 center interaction.
    for stage in ["A1", "A2", "A3", "A4"]:
        other = MIRROR[stage]
        for cable in sorted({m.cable for m in modes if m.kind == "branch" and m.stage == stage}):
            a = by_stage_cable.get((stage, cable))
            b = by_stage_cable.get((other, cable))
            if a is None or b is None:
                continue
            k = float(kcfg["a4_b4_center_same_cable_k"]) if stage == "A4" else float(kcfg["mirror_pair_same_cable_k"])
            add(a, b, k, f"mirror pair {stage}/{other}")

    # Orthogonal AMCC-1000 paraformer center.
    ua = by_name.get("U_A")
    ub = by_name.get("U_B")
    if ua is not None:
        for i in by_stage.get("A4", []):
            add(ua, i, float(kcfg["core_to_a4_branch_k"]), "U_A to A4 branch")
    if ub is not None:
        for i in by_stage.get("B4", []):
            add(ub, i, float(kcfg["core_to_b4_branch_k"]), "U_B to B4 branch")
    if ua is not None and ub is not None:
        add(ua, ub, float(kcfg["orthogonal_core_k"]), "orthogonal U_A/U_B core")

    # Guard against impossible coupling choices by scaling only off-diagonal M.
    diag = np.diag(np.diag(L))
    off = L - diag
    scale = 1.0
    for _ in range(20):
        candidate = diag + scale * off
        eig_min = float(np.linalg.eigvalsh(candidate).min())
        if eig_min > 1e-12:
            L = candidate
            break
        scale *= 0.8
    if scale < 1.0:
        for row in coupling_rows:
            row["k"] *= scale
            row["M_uH"] *= scale
            row["type"] += " (scaled for positive-definite L matrix)"

    return L, coupling_rows, scale


def source_vector(t: float, modes: list[Mode], ramp_s: float) -> np.ndarray:
    ramp = 1.0 if ramp_s <= 0 else min(1.0, t / ramp_s)
    if ramp < 1.0:
        ramp = 0.5 - 0.5 * math.cos(math.pi * ramp)
    return np.array(
        [ramp * m.drive_v_peak * math.sin(m.omega * t + m.drive_phase_rad) for m in modes],
        dtype=float,
    )


def integrate(modes: list[Mode], L_matrix: np.ndarray, cfg: dict[str, Any]) -> dict[str, np.ndarray]:
    max_f = float(cfg["max_frequency_hz"])
    base_f = float(cfg["base_frequency_hz"])
    dt = 1.0 / (max_f * float(cfg["steps_per_128k_period"]))
    duration = float(cfg["cycles_at_16k"]) / base_f
    ramp_s = float(cfg["source_ramp_cycles_at_16k"]) / base_f
    steps = int(math.ceil(duration / dt))
    stride = int(cfg["sample_stride"])

    n = len(modes)
    y = np.zeros(2 * n, dtype=float)
    L_inv = np.linalg.inv(L_matrix)
    R = np.array([m.R_dynamic_ohm for m in modes], dtype=float)
    C_inv = np.array([1.0 / m.C_f for m in modes], dtype=float)

    def rhs(t: float, state: np.ndarray) -> np.ndarray:
        i = state[:n]
        vc = state[n:]
        di = L_inv @ (source_vector(t, modes, ramp_s) - R * i - vc)
        dvc = C_inv * i
        return np.concatenate([di, dvc])

    times: list[float] = []
    currents: list[np.ndarray] = []
    caps: list[np.ndarray] = []

    t = 0.0
    for step in range(steps + 1):
        if step % stride == 0:
            times.append(t)
            currents.append(y[:n].copy())
            caps.append(y[n:].copy())
        k1 = rhs(t, y)
        k2 = rhs(t + dt / 2.0, y + dt * k1 / 2.0)
        k3 = rhs(t + dt / 2.0, y + dt * k2 / 2.0)
        k4 = rhs(t + dt, y + dt * k3)
        y += (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        t += dt

    return {
        "t": np.array(times),
        "i": np.vstack(currents),
        "vc": np.vstack(caps),
        "dt_internal": np.array([dt]),
        "duration_s": np.array([duration]),
    }


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def dft_phasor_peak(t: np.ndarray, x: np.ndarray, f_hz: float) -> complex:
    z = np.exp(-1j * 2.0 * math.pi * f_hz * t)
    return 2.0 * np.mean(x * z)


def summarize(
    modes: list[Mode],
    sim: dict[str, np.ndarray],
    L_matrix: np.ndarray,
    out_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    t = sim["t"]
    i = sim["i"]
    vc = sim["vc"]
    start = len(t) // 2
    t_ss = t[start:]
    i_ss = i[start:, :]
    vc_ss = vc[start:, :]

    branch_rows: list[dict[str, Any]] = []
    core_rows: list[dict[str, Any]] = []
    for idx, m in enumerate(modes):
        ir = rms(i_ss[:, idx])
        ip = float(np.max(np.abs(i_ss[:, idx])))
        vc_r = rms(vc_ss[:, idx])
        e_l_mean = 0.5 * m.L_h * float(np.mean(i_ss[:, idx] ** 2))
        e_c_mean = 0.5 * m.C_f * float(np.mean(vc_ss[:, idx] ** 2))
        common = {
            "mode": m.name,
            "kind": m.kind,
            "stage": m.stage,
            "cable": m.cable,
            "frequency_Hz": m.f_hz,
            "L_uH": m.L_h * 1e6,
            "C_nF": m.C_f * 1e9,
            "R_dynamic_ohm": m.R_dynamic_ohm,
            "R_copper_ohm": m.R_copper_ohm,
            "target_I_rms_A": m.target_i_rms,
            "sim_I_rms_A": ir,
            "sim_I_peak_A": ip,
            "capacitor_V_rms_V": vc_r,
            "drive_V_peak_V": m.drive_v_peak,
            "copper_loss_W": ir * ir * m.R_copper_ohm,
            "dynamic_damping_loss_W": ir * ir * m.R_dynamic_ohm,
            "mean_L_energy_J": e_l_mean,
            "mean_C_energy_J": e_c_mean,
            "frequency_error_ppm": (1.0 / (2.0 * math.pi * math.sqrt(m.L_h * m.C_f)) - m.f_hz) / m.f_hz * 1e6,
        }
        if m.kind == "core":
            b = m.L_h * i_ss[:, idx] / max(m.turns * m.ae_m2, 1e-30)
            common.update(
                {
                    "B_rms_T": rms(b),
                    "B_peak_T": float(np.max(np.abs(b))),
                    "turns": m.turns,
                    "Ae_m2": m.ae_m2,
                }
            )
            core_rows.append(common)
        else:
            branch_rows.append(common)

    write_csv(out_dir / "branch_dynamic_summary.csv", branch_rows)
    write_csv(out_dir / "core_dynamic_summary.csv", core_rows)

    stage_rows: list[dict[str, Any]] = []
    z_stage = float(cfg["stage_impedance_ohm"])
    power_w = float(cfg["power_w"])
    target_stage_i = math.sqrt(power_w / z_stage)
    for stage in STAGE_ORDER:
        idxs = [idx for idx, m in enumerate(modes) if m.kind == "branch" and m.stage == stage]
        if not idxs:
            continue
        sig = np.sum(i_ss[:, idxs], axis=1)
        f_hz = modes[idxs[0]].f_hz
        stage_rows.append(
            {
                "stage": stage,
                "frequency_Hz": f_hz,
                "active_branch_count": len(idxs),
                "target_stage_I_rms_A": target_stage_i,
                "sim_stage_I_rms_A": rms(sig),
                "sim_stage_I_peak_A": float(np.max(np.abs(sig))),
                "target_stage_voltage_rms_V_for_50ohm": math.sqrt(power_w * z_stage),
                "effective_stage_impedance_from_target_power_ohm": math.sqrt(power_w * z_stage) / max(rms(sig), 1e-30),
                "total_copper_loss_W": sum(branch_rows[idx]["copper_loss_W"] for idx, m in enumerate([m for m in modes if m.kind == "branch"]) if m.stage == stage),
                "dominant_phasor_I_rms_A": abs(dft_phasor_peak(t_ss, sig, f_hz)) / math.sqrt(2.0),
                "dominant_phase_deg": math.degrees(math.atan2(dft_phasor_peak(t_ss, sig, f_hz).imag, dft_phasor_peak(t_ss, sig, f_hz).real)),
            }
        )
    write_csv(out_dir / "stage_dynamic_summary.csv", stage_rows)

    # Spectrum at the four octave frequencies.
    spectrum_rows: list[dict[str, Any]] = []
    freqs = [float(cfg["base_frequency_hz"]) * x for x in [1, 2, 4, 8]]
    signals: dict[str, np.ndarray] = {}
    for stage in STAGE_ORDER:
        idxs = [idx for idx, m in enumerate(modes) if m.kind == "branch" and m.stage == stage]
        signals[stage] = np.sum(i_ss[:, idxs], axis=1)
    for core in ["U_A", "U_B"]:
        idx = next((idx for idx, m in enumerate(modes) if m.name == core), None)
        if idx is not None:
            signals[core] = i_ss[:, idx]
    for name, sig in signals.items():
        for f in freqs:
            ph = dft_phasor_peak(t_ss, sig, f)
            spectrum_rows.append(
                {
                    "signal": name,
                    "frequency_Hz": f,
                    "I_rms_at_frequency_A": abs(ph) / math.sqrt(2.0),
                    "phase_deg": math.degrees(math.atan2(ph.imag, ph.real)),
                }
            )
    write_csv(out_dir / "harmonic_spectrum.csv", spectrum_rows)

    # Coupled magnetic energy from the full L matrix.
    magnetic_energy = np.einsum("ij,jk,ik->i", i_ss, L_matrix, i_ss) * 0.5
    total_cap_energy = np.sum(0.5 * np.array([m.C_f for m in modes]) * vc_ss**2, axis=1)

    summary = {
        "mode_count": len(modes),
        "branch_mode_count": len(branch_rows),
        "core_mode_count": len(core_rows),
        "duration_s": float(sim["duration_s"][0]),
        "internal_dt_s": float(sim["dt_internal"][0]),
        "sample_count": len(t),
        "steady_state_window_s": float(t_ss[-1] - t_ss[0]),
        "mean_total_magnetic_energy_J": float(np.mean(magnetic_energy)),
        "peak_total_magnetic_energy_J": float(np.max(magnetic_energy)),
        "mean_total_capacitor_energy_J": float(np.mean(total_cap_energy)),
        "peak_total_capacitor_energy_J": float(np.max(total_cap_energy)),
        "total_copper_loss_W": float(sum(row["copper_loss_W"] for row in branch_rows)),
        "total_dynamic_damping_loss_W": float(sum(row["dynamic_damping_loss_W"] for row in branch_rows)),
        "drive_mode": cfg["drive_mode"],
        "power_w": cfg["power_w"],
    }
    write_json(out_dir / "simulation_summary.json", summary)
    return {
        "branch_rows": branch_rows,
        "stage_rows": stage_rows,
        "core_rows": core_rows,
        "spectrum_rows": spectrum_rows,
        "summary": summary,
        "t_ss": t_ss,
        "i_ss": i_ss,
        "vc_ss": vc_ss,
    }


def standing_wave_rows(
    modes: list[Mode],
    result: dict[str, Any],
    cfg: dict[str, Any],
    out_dir: Path,
) -> list[dict[str, Any]]:
    t_ss: np.ndarray = result["t_ss"]
    i_ss: np.ndarray = result["i_ss"]
    z0 = float(cfg["line_characteristic_impedance_ohm"])
    vf = float(cfg["line_velocity_factor"])
    alpha_128 = float(cfg["line_attenuation_np_per_m_at_128k"])
    npos = int(cfg["standing_wave_positions"])
    length_m = float(cfg.get("standing_wave_length_m", 40.0))
    xs = np.linspace(0.0, length_m, npos)
    phase_samples = [0.0, 0.125, 0.25, 0.375, 0.5]
    rows: list[dict[str, Any]] = []

    for cable in [f"C{i}" for i in range(1, 9)]:
        cable_freqs = sorted({m.f_hz for m in modes if m.kind == "branch" and m.cable == cable})
        for f_hz in cable_freqs:
            idxs = [idx for idx, m in enumerate(modes) if m.kind == "branch" and m.cable == cable and abs(m.f_hz - f_hz) < 1e-6]
            if not idxs:
                continue
            i_rms = float(np.mean([rms(i_ss[:, idx]) for idx in idxs]))
            z_load = float(np.mean([modes[idx].z_branch_ohm for idx in idxs]))
            gamma_l = (z_load - z0) / (z_load + z0)
            gamma_abs = abs(gamma_l)
            swr = (1.0 + gamma_abs) / max(1.0 - gamma_abs, 1e-12)
            beta = 2.0 * math.pi * f_hz / (vf * C0)
            alpha = alpha_128 * math.sqrt(f_hz / 128_000.0)
            vplus_peak = math.sqrt(2.0) * i_rms * z0
            for phase in phase_samples:
                t_phase = phase / f_hz
                for x in xs:
                    forward = vplus_peak * np.exp(1j * (2.0 * math.pi * f_hz * t_phase - beta * x)) * math.exp(-alpha * x)
                    backward = gamma_l * vplus_peak * np.exp(1j * (2.0 * math.pi * f_hz * t_phase + beta * x)) * math.exp(-alpha * (length_m - x))
                    voltage = float(np.real(forward + backward))
                    current = float(np.real(forward / z0 - backward / z0))
                    rows.append(
                        {
                            "cable": cable,
                            "frequency_Hz": f_hz,
                            "phase_fraction": phase,
                            "x_m": float(x),
                            "voltage_V": voltage,
                            "current_A": current,
                            "gamma_load": gamma_l,
                            "SWR": swr,
                            "electrical_length_deg": math.degrees(beta * length_m),
                            "beta_rad_per_m": beta,
                            "alpha_np_per_m": alpha,
                        }
                    )
    write_csv(out_dir / "standing_wave_samples.csv", rows)
    return rows


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def draw_axes(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, xlab: str, ylab: str) -> None:
    font = load_font(16)
    small = load_font(12)
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=(30, 30, 30), width=2)
    draw.text((x0, 20), title, fill=(10, 35, 70), font=font)
    draw.text(((x0 + x1) // 2 - 40, y1 + 34), xlab, fill=(0, 0, 0), font=small)
    draw.text((14, (y0 + y1) // 2 - 10), ylab, fill=(0, 0, 0), font=small)


def map_point(x: float, y: float, xmin: float, xmax: float, ymin: float, ymax: float, box: tuple[int, int, int, int]) -> tuple[int, int]:
    x0, y0, x1, y1 = box
    px = x0 + (x - xmin) / max(xmax - xmin, 1e-30) * (x1 - x0)
    py = y1 - (y - ymin) / max(ymax - ymin, 1e-30) * (y1 - y0)
    return int(px), int(py)


def save_line_plot(
    path: Path,
    series: list[tuple[str, np.ndarray, np.ndarray, tuple[int, int, int]]],
    title: str,
    xlab: str,
    ylab: str,
    size: tuple[int, int] = (1280, 760),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    box = (90, 70, size[0] - 50, size[1] - 90)
    draw_axes(draw, box, title, xlab, ylab)
    xs_all = np.concatenate([s[1] for s in series])
    ys_all = np.concatenate([s[2] for s in series])
    xmin, xmax = float(xs_all.min()), float(xs_all.max())
    ymin, ymax = float(ys_all.min()), float(ys_all.max())
    pad = 0.08 * max(ymax - ymin, 1e-9)
    ymin -= pad
    ymax += pad
    for frac in np.linspace(0, 1, 6):
        y = box[1] + frac * (box[3] - box[1])
        draw.line((box[0], y, box[2], y), fill=(225, 225, 225))
    font = load_font(13)
    legend_x = box[0] + 12
    legend_y = box[1] + 12
    for label, xs, ys, color in series:
        points = [map_point(float(x), float(y), xmin, xmax, ymin, ymax, box) for x, y in zip(xs, ys)]
        if len(points) >= 2:
            draw.line(points, fill=color, width=3)
        draw.rectangle((legend_x, legend_y + 3, legend_x + 24, legend_y + 13), fill=color)
        draw.text((legend_x + 32, legend_y), label, fill=(0, 0, 0), font=font)
        legend_y += 22
    img.save(path)


def save_stage_bar_plot(path: Path, stage_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1280, 760), "white")
    draw = ImageDraw.Draw(img)
    box = (90, 70, 1230, 650)
    draw_axes(draw, box, "Stage RMS current, dynamic simulation", "stage", "Arms")
    font = load_font(13)
    max_y = max(max(float(r["sim_stage_I_rms_A"]), float(r["target_stage_I_rms_A"])) for r in stage_rows) * 1.15
    bar_w = (box[2] - box[0]) / (len(stage_rows) * 2.2)
    for idx, row in enumerate(stage_rows):
        center = box[0] + (idx + 0.6) * (box[2] - box[0]) / len(stage_rows)
        sim = float(row["sim_stage_I_rms_A"])
        target = float(row["target_stage_I_rms_A"])
        h_sim = sim / max_y * (box[3] - box[1])
        h_tar = target / max_y * (box[3] - box[1])
        draw.rectangle((center - bar_w, box[3] - h_sim, center, box[3]), fill=(40, 115, 185))
        draw.rectangle((center + 4, box[3] - h_tar, center + bar_w + 4, box[3]), fill=(220, 135, 45))
        draw.text((center - bar_w, box[3] + 10), str(row["stage"]), fill=(0, 0, 0), font=font)
    draw.rectangle((105, 92, 125, 108), fill=(40, 115, 185))
    draw.text((132, 88), "sim", fill=(0, 0, 0), font=font)
    draw.rectangle((190, 92, 210, 108), fill=(220, 135, 45))
    draw.text((218, 88), "target", fill=(0, 0, 0), font=font)
    img.save(path)


def save_spectrum_plot(path: Path, spectrum_rows: list[dict[str, Any]]) -> None:
    names = ["A1", "A2", "A3", "A4", "B4", "B3", "B2", "B1", "U_A", "U_B"]
    freqs = [16_000.0, 32_000.0, 64_000.0, 128_000.0]
    data = {(r["signal"], float(r["frequency_Hz"])): float(r["I_rms_at_frequency_A"]) for r in spectrum_rows}
    img = Image.new("RGB", (1280, 760), "white")
    draw = ImageDraw.Draw(img)
    box = (90, 70, 1230, 650)
    draw_axes(draw, box, "Octave harmonic current spectrum", "signal", "Arms")
    font = load_font(12)
    colors = [(35, 95, 170), (65, 160, 100), (205, 120, 40), (150, 70, 170)]
    max_y = max(data.values()) * 1.2 if data else 1.0
    group_w = (box[2] - box[0]) / len(names)
    bar_w = group_w / 5.5
    for gi, name in enumerate(names):
        x_base = box[0] + gi * group_w + group_w * 0.12
        for fi, f in enumerate(freqs):
            val = data.get((name, f), 0.0)
            h = val / max_y * (box[3] - box[1])
            x0 = x_base + fi * bar_w
            draw.rectangle((x0, box[3] - h, x0 + bar_w * 0.85, box[3]), fill=colors[fi])
        draw.text((x_base, box[3] + 10), name, fill=(0, 0, 0), font=font)
    lx = 105
    for fi, f in enumerate(freqs):
        draw.rectangle((lx, 94, lx + 18, 108), fill=colors[fi])
        draw.text((lx + 24, 88), f"{f/1000:.0f} kHz", fill=(0, 0, 0), font=font)
        lx += 110
    img.save(path)


def composite_cable_voltage(rows: list[dict[str, Any]], cable: str, phase_fraction: float) -> tuple[np.ndarray, np.ndarray]:
    subset = [r for r in rows if r["cable"] == cable and abs(float(r["phase_fraction"]) - phase_fraction) < 1e-12]
    xs = sorted({float(r["x_m"]) for r in subset})
    if not xs:
        return np.array([]), np.array([])
    y = np.zeros(len(xs))
    x_index = {x: idx for idx, x in enumerate(xs)}
    for r in subset:
        y[x_index[float(r["x_m"])]] += float(r["voltage_V"])
    scale = max(float(np.max(np.abs(y))), 1e-30)
    return np.array(xs), y / scale


def save_standing_wave_plot(path: Path, rows: list[dict[str, Any]]) -> None:
    colors = [(30, 105, 180), (210, 95, 45), (70, 150, 90), (130, 70, 170)]
    series = []
    for idx, cable in enumerate(["C1", "C3", "C5", "C8"]):
        x, y = composite_cable_voltage(rows, cable, 0.0)
        if len(x):
            series.append((f"{cable}, composite", x, y, colors[idx]))
    save_line_plot(path, series, "Distributed standing-wave voltage, phase 0", "cable coordinate x (m)", "normalized V")


def save_core_lissajous(path: Path, modes: list[Mode], result: dict[str, Any]) -> None:
    t_ss = result["t_ss"]
    i_ss = result["i_ss"]
    idx_a = next((idx for idx, m in enumerate(modes) if m.name == "U_A"), None)
    idx_b = next((idx for idx, m in enumerate(modes) if m.name == "U_B"), None)
    if idx_a is None or idx_b is None:
        return
    ma, mb = modes[idx_a], modes[idx_b]
    ba = ma.L_h * i_ss[:, idx_a] / max(ma.turns * ma.ae_m2, 1e-30)
    bb = mb.L_h * i_ss[:, idx_b] / max(mb.turns * mb.ae_m2, 1e-30)
    keep = t_ss > (t_ss[-1] - 4.0 / ma.f_hz)
    save_line_plot(
        path,
        [("U_A vs U_B trajectory", ba[keep], bb[keep], (40, 115, 185))],
        "AMCC-1000 orthogonal core flux trajectory",
        "B_U_A (T)",
        "B_U_B (T)",
    )


def save_standing_wave_gif(path: Path, rows: list[dict[str, Any]], cable: str = "C1", frames: int = 48) -> None:
    frame_images: list[Image.Image] = []
    phases = np.linspace(0.0, 1.0, frames, endpoint=False)
    # Regenerate intermediate frames from nearest stored harmonic rows.
    harmonic_rows = [r for r in rows if r["cable"] == cable]
    freqs = sorted({float(r["frequency_Hz"]) for r in harmonic_rows})
    xs = np.array(sorted({float(r["x_m"]) for r in harmonic_rows}))
    if not len(xs):
        return
    by_freq_x: dict[tuple[float, float], dict[str, float]] = {}
    for r in harmonic_rows:
        if abs(float(r["phase_fraction"])) < 1e-12:
            by_freq_x[(float(r["frequency_Hz"]), float(r["x_m"]))] = {
                "gamma_load": float(r["gamma_load"]),
                "beta": float(r["beta_rad_per_m"]),
                "alpha": float(r["alpha_np_per_m"]),
                "current_scale": abs(float(r["current_A"])) + 1e-9,
            }
    for phase in phases:
        y = np.zeros_like(xs)
        for f in freqs:
            omega = 2.0 * math.pi * f
            period = 1.0 / f
            t = phase / 128_000.0
            # Keep amplitude normalized from stored phase-0 values.
            stored = [r for r in harmonic_rows if abs(float(r["frequency_Hz"]) - f) < 1e-9 and abs(float(r["phase_fraction"])) < 1e-12]
            if not stored:
                continue
            vscale = max(abs(float(r["voltage_V"])) for r in stored)
            gamma_l = float(stored[0]["gamma_load"])
            beta = float(stored[0]["beta_rad_per_m"])
            alpha = float(stored[0]["alpha_np_per_m"])
            z0 = 50.0
            vplus = vscale / max(1.0 + abs(gamma_l), 1e-12)
            for xi, x in enumerate(xs):
                forward = vplus * np.exp(1j * (omega * t - beta * x)) * math.exp(-alpha * x)
                backward = gamma_l * vplus * np.exp(1j * (omega * t + beta * x)) * math.exp(-alpha * (40.0 - x))
                _ = z0
                y[xi] += float(np.real(forward + backward))
        scale = max(float(np.max(np.abs(y))), 1e-30)
        img = Image.new("RGB", (900, 520), "white")
        draw = ImageDraw.Draw(img)
        box = (80, 60, 850, 430)
        draw_axes(draw, box, f"{cable} standing-wave animation", "x (m)", "normalized V")
        points = [map_point(float(x), float(v / scale), 0.0, 40.0, -1.1, 1.1, box) for x, v in zip(xs, y)]
        draw.line(points, fill=(40, 115, 185), width=4)
        draw.text((80, 450), f"phase at 128 kHz period = {phase:.3f}", fill=(0, 0, 0), font=load_font(14))
        frame_images.append(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_images[0].save(path, save_all=True, append_images=frame_images[1:], duration=70, loop=0)


def write_dashboard(root: Path, summary: dict[str, Any]) -> None:
    cards = "".join(
        f"<div class='card'><b>{html.escape(str(k))}</b><span>{html.escape(str(v))}</span></div>"
        for k, v in summary.items()
        if isinstance(v, (int, float, str))
    )
    body = f"""<!doctype html>
<html lang="fi">
<meta charset="utf-8">
<title>Dynamic standing-wave simulator</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; margin: 32px; color: #111; }}
h1 {{ color: #173b63; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
.card {{ border: 1px solid #d0d7de; padding: 12px; border-radius: 6px; background: #f8fafc; }}
.card span {{ display: block; margin-top: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
img {{ max-width: 100%; border: 1px solid #d0d7de; margin: 16px 0; }}
code {{ background: #f1f5f9; padding: 2px 4px; border-radius: 3px; }}
</style>
<h1>Walter Russell optical dynamo, dynamic standing-wave simulator</h1>
<p>RLC + coupled-inductor + transmission-line model. This is a simulation dashboard, not a high-power operating instruction.</p>
<div class="grid">{cards}</div>
<h2>Figures</h2>
<img src="../figures/stage_currents.png" alt="stage currents">
<img src="../figures/standing_wave_map.png" alt="standing wave map">
<img src="../figures/harmonic_spectrum.png" alt="harmonic spectrum">
<img src="../figures/core_flux_lissajous.png" alt="core flux lissajous">
<p>Animation: <a href="../figures/standing_wave_animation.gif">standing_wave_animation.gif</a></p>
<h2>CSV outputs</h2>
<p>See <code>outputs/*.csv</code> for branch, stage, core, spectrum, coupling, and standing-wave samples.</p>
</html>
"""
    (root / "outputs" / "dashboard.html").write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--fig-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    cfg = read_json(args.config)
    input_dir = args.input_dir or (ROOT / cfg["input_outputs_dir"]).resolve()
    cable_lengths_path = input_dir / "cable_lengths.csv"
    if cable_lengths_path.exists():
        cable_rows = read_csv_rows(cable_lengths_path)
        cfg["standing_wave_length_m"] = max(fnum(row, "active_total_m") for row in cable_rows)
    out_dir = args.out_dir
    fig_dir = args.fig_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    modes = build_modes(cfg, input_dir)
    L_matrix, coupling_rows, coupling_scale = build_coupling_matrix(modes, cfg)
    write_csv(out_dir / "coupling_matrix.csv", coupling_rows)

    sim = integrate(modes, L_matrix, cfg)
    result = summarize(modes, sim, L_matrix, out_dir, cfg)
    sw_rows = standing_wave_rows(modes, result, cfg, out_dir)

    save_stage_bar_plot(fig_dir / "stage_currents.png", result["stage_rows"])
    save_standing_wave_plot(fig_dir / "standing_wave_map.png", sw_rows)
    save_spectrum_plot(fig_dir / "harmonic_spectrum.png", result["spectrum_rows"])
    save_core_lissajous(fig_dir / "core_flux_lissajous.png", modes, result)
    save_standing_wave_gif(fig_dir / "standing_wave_animation.gif", sw_rows, frames=int(cfg["gif_frames"]))

    result["summary"]["coupling_offdiagonal_scale"] = coupling_scale
    result["summary"]["input_dir"] = str(input_dir)
    write_json(out_dir / "simulation_summary.json", result["summary"])
    write_dashboard(ROOT, result["summary"])

    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
