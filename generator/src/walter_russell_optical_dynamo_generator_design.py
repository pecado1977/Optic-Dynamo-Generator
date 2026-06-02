#!/usr/bin/env python3
"""Walter Russell optical dynamo generator AMCC-1000 simulation package.

The model preserves eight original coil positions and eight named cable paths.
It is a physics/simulation and documentation generator, not a live high-power
MOSFET construction recipe. The 4-10 kW range is treated as a protected
resonant-inverter system envelope.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from scipy import special as scipy_special
except Exception:  # pragma: no cover - optional acceleration
    scipy_special = None

try:
    import numpy as np
except Exception:  # pragma: no cover - optional acceleration
    np = None


MU0 = 4 * math.pi * 1e-7
RHO_CU_20 = 1.724e-8
ALPHA_CU = 0.00393
INCH = 0.0254


@dataclass(frozen=True)
class Core:
    name: str
    Ae_m2: float
    le_m: float
    Wa_m2: float
    mass_kg: float
    Bs_T: float
    mur_small: float
    ribbon_thickness_m: float
    resistivity_ohm_m: float
    lamination_factor: float


@dataclass(frozen=True)
class WireSpec:
    cable: str
    historical_awg: int
    recommended_awg_equiv: int
    strand_awg: int
    role: str


@dataclass(frozen=True)
class BobbinSpec:
    family: str
    source_label: str
    axial_in: float
    inner_diameter_in: float
    mean_diameter_in: float
    material_note: str


AMCC1000 = Core(
    name="Metglas 2605SA1 AMCC-1000 class cut C-core",
    Ae_m2=23.0e-4,
    le_m=42.7e-2,
    Wa_m2=42.0e-4,
    mass_kg=7.109,
    Bs_T=1.56,
    mur_small=45_000.0,
    ribbon_thickness_m=23e-6,
    resistivity_ohm_m=130e-8,
    lamination_factor=0.84,
)


WIRE_SPECS = {
    "C1": WireSpec("C1", 14, 10, 36, "first heavy Russell path"),
    "C2": WireSpec("C2", 14, 10, 36, "second heavy Russell path"),
    "C3": WireSpec("C3", 18, 12, 36, "third-stage medium path"),
    "C4": WireSpec("C4", 18, 12, 36, "third-stage medium path"),
    "C5": WireSpec("C5", 22, 18, 36, "centre-adjacent fine path"),
    "C6": WireSpec("C6", 22, 18, 36, "centre-adjacent fine path"),
    "C7": WireSpec("C7", 22, 18, 36, "centre-adjacent fine path"),
    "C8": WireSpec("C8", 22, 18, 36, "centre-adjacent fine path"),
}


BOBBIN_SPECS = {
    "large": BobbinSpec(
        family="large",
        source_label='A1/A2/B2/B1 source envelope: 4 3/4 in x 19 in, 5 in hole',
        axial_in=19.0,
        inner_diameter_in=5.0,
        mean_diameter_in=7.4,
        material_note="G10/FR4, glass-filled nylon, Ultem, PEEK, or machined phenolic; avoid PLA for high RF voltage",
    ),
    "small": BobbinSpec(
        family="small",
        source_label='A3/A4/B4/B3 source envelope: 3 3/4 in x 14 in',
        axial_in=14.0,
        inner_diameter_in=4.0,
        mean_diameter_in=5.8,
        material_note="G10/FR4, glass-filled nylon, Ultem, PEEK, or machined phenolic; avoid PLA for high RF voltage",
    ),
}


def awg_diameter_m(awg: int) -> float:
    return 0.000127 * 92 ** ((36 - awg) / 39)


def awg_area_mm2(awg: int) -> float:
    d = awg_diameter_m(awg)
    return math.pi * (d / 2) ** 2 * 1e6


def equivalent_awg_from_area_mm2(area_mm2: float) -> float:
    d_m = math.sqrt(4 * area_mm2 * 1e-6 / math.pi)
    return 36 - 39 * math.log(d_m / 0.000127, 92)


def copper_resistivity(temp_c: float) -> float:
    return RHO_CU_20 * (1 + ALPHA_CU * (temp_c - 20.0))


def copper_rdc_ohm(length_m: float, area_mm2: float, temp_c: float = 60.0) -> float:
    return copper_resistivity(temp_c) * length_m / (area_mm2 * 1e-6)


def skin_depth_m(f_hz: float, rho: float = RHO_CU_20) -> float:
    return math.sqrt(rho / (math.pi * f_hz * MU0))


def litz_strands_for_equiv_awg(equiv_awg: int, strand_awg: int = 36) -> tuple[int, float]:
    target = awg_area_mm2(equiv_awg)
    strand = awg_area_mm2(strand_awg)
    return math.ceil(target / strand), strand


def litz_bundle_od_mm(equiv_awg: int, strand_awg: int = 36, packing_factor: float = 0.55, serving_factor: float = 1.15) -> float:
    copper_area = awg_area_mm2(equiv_awg)
    compact_diameter = 2 * math.sqrt(copper_area / (math.pi * packing_factor))
    return compact_diameter * serving_factor


def wheeler_single_layer_solenoid_h(radius_m: float, length_m: float, turns: float) -> float:
    """Wheeler air-core solenoid estimate with inches internally."""
    r_in = radius_m / INCH
    l_in = length_m / INCH
    if turns <= 0:
        return 0.0
    return ((r_in**2 * turns**2) / (9.0 * r_in + 10.0 * l_in)) * 1e-6


def _simpson_integral(fn, a: float = 0.0, b: float = math.pi / 2, n: int = 512) -> float:
    if n % 2:
        n += 1
    h = (b - a) / n
    total = fn(a) + fn(b)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * fn(a + i * h)
    return total * h / 3


def complete_elliptic_k_e(m: float) -> tuple[float, float]:
    """Complete elliptic integrals K(m), E(m) by numerical quadrature."""
    m = min(max(m, 0.0), 1.0 - 1e-12)
    if scipy_special is not None:
        return float(scipy_special.ellipk(m)), float(scipy_special.ellipe(m))
    k_val = _simpson_integral(lambda t: 1.0 / math.sqrt(1.0 - m * math.sin(t) ** 2))
    e_val = _simpson_integral(lambda t: math.sqrt(1.0 - m * math.sin(t) ** 2))
    return k_val, e_val


def loop_self_inductance_h(radius_m: float, conductor_radius_m: float) -> float:
    conductor_radius_m = max(conductor_radius_m, 1e-6)
    return MU0 * radius_m * (math.log(8.0 * radius_m / conductor_radius_m) - 2.0)


def coaxial_loop_mutual_inductance_h(radius_a_m: float, radius_b_m: float, separation_m: float) -> float:
    m = 4.0 * radius_a_m * radius_b_m / ((radius_a_m + radius_b_m) ** 2 + separation_m**2)
    k = math.sqrt(min(max(m, 1e-15), 1.0 - 1e-12))
    K, E = complete_elliptic_k_e(m)
    return MU0 * math.sqrt(radius_a_m * radius_b_m) * (((2.0 - m) / k) * K - (2.0 / k) * E)


def grover_loop_array_solenoid_h(radius_m: float, length_m: float, turns: float, conductor_od_m: float) -> float:
    """Finite single-layer solenoid inductance from coaxial-loop summation."""
    if turns <= 0:
        return 0.0
    n_loops = max(1, math.ceil(turns))
    weight = turns / n_loops
    conductor_radius_m = conductor_od_m / 2.0
    self_l = loop_self_inductance_h(radius_m, conductor_radius_m)
    if np is not None and scipy_special is not None and n_loops > 1:
        positions = np.linspace(-length_m / 2.0, length_m / 2.0, n_loops)
        dz = np.abs(positions[:, None] - positions[None, :])
        m = 4.0 * radius_m * radius_m / ((2.0 * radius_m) ** 2 + dz**2)
        m = np.clip(m, 1e-15, 1.0 - 1e-12)
        np.fill_diagonal(m, 0.5)
        k = np.sqrt(m)
        mutual = MU0 * radius_m * (((2.0 - m) / k) * scipy_special.ellipk(m) - (2.0 / k) * scipy_special.ellipe(m))
        np.fill_diagonal(mutual, self_l)
        return float(weight * weight * np.sum(mutual))
    if n_loops == 1:
        positions = [0.0]
    else:
        pitch = length_m / (n_loops - 1)
        positions = [(-length_m / 2.0) + i * pitch for i in range(n_loops)]
    total = 0.0
    for i, zi in enumerate(positions):
        for j, zj in enumerate(positions):
            if i == j:
                mij = self_l
            else:
                mij = coaxial_loop_mutual_inductance_h(radius_m, radius_m, abs(zi - zj))
            total += weight * weight * mij
    return total


def inductance_h(core: Core, turns: float, gap_m: float, fringing_factor: float = 1.0) -> float:
    return MU0 * turns**2 * core.Ae_m2 / (core.le_m / core.mur_small + gap_m / fringing_factor)


def cap_for_resonance_f(f_hz: float, L_h: float) -> float:
    return 1 / ((2 * math.pi * f_hz) ** 2 * L_h)


def v_rms_for_b(core: Core, turns: float, f_hz: float, b_t: float) -> float:
    return 2 * math.pi * f_hz * turns * core.Ae_m2 * b_t / math.sqrt(2)


def i_peak_for_b(core: Core, turns: float, b_t: float, gap_m: float) -> float:
    return b_t * (core.le_m / core.mur_small + gap_m) / (MU0 * turns)


def full_bridge_fundamental_rms(v_bus: float) -> float:
    return 2.0 * math.sqrt(2.0) * v_bus / math.pi


def half_bridge_fundamental_rms(v_bus: float) -> float:
    return math.sqrt(2.0) * v_bus / math.pi


def parallel_resistance(resistances: list[float]) -> float:
    return 1.0 / sum(1.0 / r for r in resistances if r > 0)


def parallel_inductance(inductances_h: list[float]) -> float:
    valid = [l for l in inductances_h if l > 0]
    if not valid:
        return 0.0
    return 1.0 / sum(1.0 / l for l in valid)


def scaled_length_for_target_l(current_length_m: float, current_l_h: float, target_l_h: float) -> float:
    """First-order same-bobbin length estimate using L proportional to N^2."""
    if current_length_m <= 0 or current_l_h <= 0 or target_l_h <= 0:
        return 0.0
    return current_length_m * math.sqrt(target_l_h / current_l_h)


def solve_air_core_length_for_l(
    target_l_h: float,
    radius_m: float,
    axial_m: float,
    conductor_od_m: float,
    mean_turn_length_m: float,
    rel_tol: float = 5e-7,
) -> tuple[float, float, float]:
    """Solve wound cable length for a target finite-solenoid inductance."""
    if target_l_h <= 0 or mean_turn_length_m <= 0:
        return 0.0, 0.0, 0.0

    def inductance_for_length(length_m: float) -> float:
        turns = length_m / mean_turn_length_m
        return grover_loop_array_solenoid_h(radius_m, axial_m, turns, conductor_od_m)

    low = 0.0
    high = mean_turn_length_m
    l_high = inductance_for_length(high)
    best_length = high
    best_l = l_high
    best_err = abs(l_high - target_l_h)
    while l_high < target_l_h:
        high *= 1.7
        l_high = inductance_for_length(high)
        err = abs(l_high - target_l_h)
        if err < best_err:
            best_length = high
            best_l = l_high
            best_err = err
        if high > 1500.0:
            raise ValueError(f"Could not bracket air-core length for target L={target_l_h} H")

    for _ in range(70):
        mid = 0.5 * (low + high)
        l_mid = inductance_for_length(mid)
        err = abs(l_mid - target_l_h)
        if err < best_err:
            best_length = mid
            best_l = l_mid
            best_err = err
        if l_mid < target_l_h:
            low = mid
        else:
            high = mid
        if (high - low) <= max(1e-10, 1e-8 * mean_turn_length_m):
            break

    candidates = [low, high, 0.5 * (low + high), best_length]
    turns_best = max(1.0, best_length / mean_turn_length_m)
    # The loop-array model uses ceil(turns), so integer-turn boundaries are
    # legitimate discontinuities. Evaluate both sides of nearby boundaries and
    # keep the length that minimizes the actual inductance error used later.
    for k in range(max(1, int(math.floor(turns_best)) - 4), int(math.ceil(turns_best)) + 5):
        boundary = k * mean_turn_length_m
        eps = max(1e-9, 1e-9 * boundary)
        candidates.extend([boundary, boundary + eps, max(0.0, boundary - eps)])
    for candidate in candidates:
        if candidate <= 0:
            continue
        l_candidate = inductance_for_length(candidate)
        err = abs(l_candidate - target_l_h)
        if err < best_err:
            best_length = candidate
            best_l = l_candidate
            best_err = err

    length_m = best_length
    turns = length_m / mean_turn_length_m
    return length_m, turns, best_l


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def design(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    f_metglas = 128_000.0
    f_base = f_metglas / 8.0
    z_ab = 50.0
    power_min = 4_000.0
    power_max = 10_000.0

    lead_allowance_m = 1.0
    reserve = 0.03
    rac_factor_litz = 1.15
    litz_packing_factor = 0.55
    litz_serving_factor = 1.15

    # Updated routing: the first two heavy paths C1/C2 now also pass through
    # A3/B3. Stage 3 therefore has four active branches; A4/B4 still carry
    # all eight paths. The B side mirrors A.
    stage_cables = {
        "A1": ["C1", "C2"],
        "A2": ["C1", "C2"],
        "A3": ["C1", "C2", "C3", "C4"],
        "A4": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"],
        "B4": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"],
        "B3": ["C1", "C2", "C3", "C4"],
        "B2": ["C1", "C2"],
        "B1": ["C1", "C2"],
    }
    stage_frequency = {
        "A1": f_base,
        "A2": 2 * f_base,
        "A3": 4 * f_base,
        "A4": 8 * f_base,
        "B4": 8 * f_base,
        "B3": 4 * f_base,
        "B2": 2 * f_base,
        "B1": f_base,
    }
    stage_order = ["A1", "A2", "A3", "A4", "B4", "B3", "B2", "B1"]
    stage_bobbin_family = {
        "A1": "large",
        "A2": "large",
        "A3": "small",
        "A4": "small",
        "B4": "small",
        "B3": "small",
        "B2": "large",
        "B1": "large",
    }

    cable_ids = [f"C{i}" for i in range(1, 9)]
    cable_visits = {cid: [s for s in stage_order if cid in stage_cables[s]] for cid in cable_ids}
    segment_length: dict[tuple[str, str], float] = {}
    segment_turns_solution: dict[tuple[str, str], float] = {}
    segment_l_solution: dict[tuple[str, str], float] = {}

    wire_rows = []
    wire_by_cable = {}
    skin_128_mm = skin_depth_m(f_metglas) * 1e3
    for cid in cable_ids:
        spec = WIRE_SPECS[cid]
        strands, strand_area = litz_strands_for_equiv_awg(spec.recommended_awg_equiv, spec.strand_awg)
        copper_area = awg_area_mm2(spec.recommended_awg_equiv)
        litz_od = litz_bundle_od_mm(spec.recommended_awg_equiv, spec.strand_awg, litz_packing_factor, litz_serving_factor)
        rdc_per_m_60 = copper_rdc_ohm(1.0, copper_area, 60.0)
        row = {
            "cable": cid,
            "historical_awg_from_russell_text": spec.historical_awg,
            "recommended_modern_awg_equivalent": spec.recommended_awg_equiv,
            "strand_count": strands,
            "strand_awg": spec.strand_awg,
            "copper_area_mm2": copper_area,
            "strand_area_mm2": strand_area,
            "estimated_silk_litz_od_mm": litz_od,
            "skin_depth_128kHz_mm": skin_128_mm,
            "strand_diameter_mm": awg_diameter_m(spec.strand_awg) * 1e3,
            "rdc_ohm_per_m_60C": rdc_per_m_60,
            "rac_model_factor": rac_factor_litz,
            "role": spec.role,
            "note": "Historical solid AWG is recorded only as source lineage; modern design uses RF Litz/parallel bundle at 128 kHz.",
        }
        wire_rows.append(row)
        wire_by_cable[cid] = row
    write_csv(out_dir / "wire_awg_litz_plan.csv", wire_rows)

    # Physical consistency rule: every active branch uses the actual wound
    # length that makes its Grover finite-solenoid inductance equal to the
    # branch L target. All C cables are then made the same end-to-end length by
    # adding non-inductive equalizing length outside the coil windows.
    air_core_solution_cache: dict[tuple[str, int, float], tuple[float, float, float]] = {}
    for stage in stage_order:
        f = stage_frequency[stage]
        active = stage_cables[stage]
        branch_target_z = z_ab * len(active)
        branch_target_l = branch_target_z / (2 * math.pi * f)
        bobbin = BOBBIN_SPECS[stage_bobbin_family[stage]]
        mean_turn_length_m = math.pi * bobbin.mean_diameter_in * INCH
        axial_m = bobbin.axial_in * INCH
        mean_radius_m = bobbin.mean_diameter_in * INCH / 2.0
        for cid in active:
            od_m = wire_by_cable[cid]["estimated_silk_litz_od_mm"] / 1e3
            cache_key = (bobbin.family, int(wire_by_cable[cid]["wire_recommended_awg_equiv"] if "wire_recommended_awg_equiv" in wire_by_cable[cid] else wire_by_cable[cid]["recommended_modern_awg_equivalent"]), round(branch_target_l, 12))
            if cache_key not in air_core_solution_cache:
                air_core_solution_cache[cache_key] = solve_air_core_length_for_l(
                    branch_target_l,
                    mean_radius_m,
                    axial_m,
                    od_m,
                    mean_turn_length_m,
                )
            length_m, turns, solved_l = air_core_solution_cache[cache_key]
            segment_length[(cid, stage)] = length_m
            segment_turns_solution[(cid, stage)] = turns
            segment_l_solution[(cid, stage)] = solved_l

    cable_wound_total_m = {
        cid: sum(segment_length[(cid, stage)] for stage in cable_visits[cid])
        for cid in cable_ids
    }
    common_active_length_m = max(cable_wound_total_m.values())
    cable_equalizing_length_m = {
        cid: common_active_length_m - cable_wound_total_m[cid]
        for cid in cable_ids
    }

    cable_rows = []
    for cid in cable_ids:
        wire = wire_by_cable[cid]
        cable_rows.append(
            {
                "cable": cid,
                "active_total_m": common_active_length_m,
                "wound_total_m": cable_wound_total_m[cid],
                "non_inductive_equalizing_length_m": cable_equalizing_length_m[cid],
                "lead_allowance_total_m": lead_allowance_m,
                "cut_length_m": common_active_length_m + lead_allowance_m,
                "cut_plus_3pct_m": (common_active_length_m + lead_allowance_m) * (1 + reserve),
                "wire": f"silk-covered AWG{wire['recommended_modern_awg_equivalent']}-equivalent RF Litz, {wire['strand_count']} x AWG{wire['strand_awg']}",
                "visited_stages": " -> ".join(cable_visits[cid]),
                "connection_note": "same magnetic polarity within each active coil; extra length is routed as low-inductance non-coil equalizer so every C cable has the same end-to-end length",
            }
        )
    write_csv(out_dir / "cable_lengths.csv", cable_rows)

    segment_rows = []
    for cid in cable_ids:
        for stage in cable_visits[cid]:
            bobbin = BOBBIN_SPECS[stage_bobbin_family[stage]]
            mean_turn_length_m = math.pi * bobbin.mean_diameter_in * INCH
            segment_rows.append(
                {
                    "cable": cid,
                    "stage": stage,
                    "segment_length_m": segment_length[(cid, stage)],
                    "bobbin_family": bobbin.family,
                    "mean_turn_length_m": mean_turn_length_m,
                    "turns_on_bobbin": segment_length[(cid, stage)] / mean_turn_length_m,
                    "solved_physical_L_uH": segment_l_solution[(cid, stage)] * 1e6,
                    "frequency_Hz": stage_frequency[stage],
                    "frequency_kHz": stage_frequency[stage] / 1e3,
                    "stage_active_cables": " ".join(stage_cables[stage]),
                    "wire": f"AWG{wire_by_cable[cid]['recommended_modern_awg_equivalent']}-equiv Litz, {wire_by_cable[cid]['strand_count']} x AWG{wire_by_cable[cid]['strand_awg']}",
                }
            )
    write_csv(out_dir / "cable_segment_lengths.csv", segment_rows)

    stage_rows = []
    branch_rows = []
    bobbin_rows = []
    for stage in stage_order:
        f = stage_frequency[stage]
        active = stage_cables[stage]
        target_l = z_ab / (2 * math.pi * f)
        target_c = 1 / (2 * math.pi * f * z_ab)
        seg_lengths = [segment_length[(cid, stage)] for cid in active]
        seg_rac = [
            copper_rdc_ohm(length, wire_by_cable[cid]["copper_area_mm2"], 60.0) * rac_factor_litz
            for cid, length in zip(active, seg_lengths)
        ]
        r_eq = parallel_resistance(seg_rac)
        i_min = math.sqrt(power_min / z_ab)
        i_max = math.sqrt(power_max / z_ab)
        branch_i_min = i_min / len(active)
        branch_i_max = i_max / len(active)
        branch_target_z = z_ab * len(active)
        branch_target_l = branch_target_z / (2 * math.pi * f)
        branch_target_c = 1 / (2 * math.pi * f * branch_target_z)
        loss_min = i_min**2 * r_eq
        loss_max = i_max**2 * r_eq
        loss_min_equalized = sum(branch_i_min**2 * r for r in seg_rac)
        loss_max_equalized = sum(branch_i_max**2 * r for r in seg_rac)
        # Current sharing estimate if the active cable segments are paralleled without individual ballast.
        g_sum = sum(1 / r for r in seg_rac)
        max_share = max((1 / r) / g_sum for r in seg_rac)
        min_share = min((1 / r) / g_sum for r in seg_rac)
        bobbin = BOBBIN_SPECS[stage_bobbin_family[stage]]
        mean_turn_length_m = math.pi * bobbin.mean_diameter_in * INCH
        axial_mm = bobbin.axial_in * INCH * 1e3
        inner_diameter_mm = bobbin.inner_diameter_in * INCH * 1e3
        mean_diameter_mm = bobbin.mean_diameter_in * INCH * 1e3
        radial_depth_mm = (bobbin.mean_diameter_in - bobbin.inner_diameter_in) * INCH * 1e3
        outer_diameter_mm = inner_diameter_mm + 2 * radial_depth_mm
        window_cross_section_mm2 = axial_mm * radial_depth_mm
        turns_by_cable = [segment_length[(cid, stage)] / mean_turn_length_m for cid in active]
        insulated_area_turns_mm2 = [
            turns * math.pi * (wire_by_cable[cid]["estimated_silk_litz_od_mm"] / 2) ** 2
            for cid, turns in zip(active, turns_by_cable)
        ]
        pack_cross_section_mm2 = sum(insulated_area_turns_mm2)
        fill_percent = 100 * pack_cross_section_mm2 / window_cross_section_mm2
        required_radial_depth_mm = max(
            max(wire_by_cable[cid]["estimated_silk_litz_od_mm"] for cid in active),
            1.25 * pack_cross_section_mm2 / axial_mm,
        )
        wheeler_l_each_branch = []
        grover_l_each_branch = []
        for cid, turns in zip(active, turns_by_cable):
            radius_m = mean_diameter_mm / 2e3
            length_m = axial_mm / 1e3
            od_m = wire_by_cable[cid]["estimated_silk_litz_od_mm"] / 1e3
            wheeler_l_each_branch.append(wheeler_single_layer_solenoid_h(radius_m, length_m, turns))
            grover_l_each_branch.append(grover_loop_array_solenoid_h(radius_m, length_m, turns, od_m))
        branch_required_lengths = [
            scaled_length_for_target_l(length, l_air, branch_target_l)
            for length, l_air in zip(seg_lengths, grover_l_each_branch)
        ]
        branch_required_turns = [
            req_len / mean_turn_length_m if mean_turn_length_m > 0 else 0.0
            for req_len in branch_required_lengths
        ]
        branch_extra_lengths = [
            max(0.0, req_len - length)
            for req_len, length in zip(branch_required_lengths, seg_lengths)
        ]
        physical_parallel_l = parallel_inductance(grover_l_each_branch)
        physical_to_target_pct = 100.0 * physical_parallel_l / target_l if target_l > 0 else 0.0
        bobbin_rows.append(
            {
                "stage": stage,
                "bobbin_family": bobbin.family,
                "source_label": bobbin.source_label,
                "axial_length_mm": axial_mm,
                "inner_diameter_mm": inner_diameter_mm,
                "mean_diameter_mm": mean_diameter_mm,
                "outer_diameter_mm": outer_diameter_mm,
                "radial_depth_capacity_mm": radial_depth_mm,
                "mean_turn_length_m": mean_turn_length_m,
                "active_cables": " ".join(active),
                "cable_lengths_in_bobbin_m": " ".join(f"{cid}:{segment_length[(cid, stage)]:.6f}" for cid in active),
                "turns_by_cable": " ".join(f"{cid}:{turns:.6f}" for cid, turns in zip(active, turns_by_cable)),
                "total_cable_length_in_bobbin_m": sum(seg_lengths),
                "total_cable_turns_sum": sum(turns_by_cable),
                "estimated_insulated_pack_area_mm2": pack_cross_section_mm2,
                "available_window_area_mm2": window_cross_section_mm2,
                "fill_percent_of_source_window": fill_percent,
                "required_radial_depth_mm_from_pack": required_radial_depth_mm,
                "max_litz_od_mm": max(wire_by_cable[cid]["estimated_silk_litz_od_mm"] for cid in active),
                "estimated_air_core_L_uH_by_branch": " ".join(f"{cid}:{L*1e6:.6f}" for cid, L in zip(active, grover_l_each_branch)),
                "grover_loop_array_L_uH_by_branch": " ".join(f"{cid}:{L*1e6:.6f}" for cid, L in zip(active, grover_l_each_branch)),
                "wheeler_single_layer_L_uH_by_branch": " ".join(f"{cid}:{L*1e6:.6f}" for cid, L in zip(active, wheeler_l_each_branch)),
                "uncoupled_physical_parallel_L_uH": physical_parallel_l * 1e6,
                "physical_parallel_to_stage_target_percent": physical_to_target_pct,
                "branch_target_L_uH": branch_target_l * 1e6,
                "series_trim_L_uH_by_branch_if_using_current_length": " ".join(
                    f"{cid}:{max(0.0, branch_target_l - L)*1e6:.6f}" for cid, L in zip(active, grover_l_each_branch)
                ),
                "required_length_for_branch_target_air_core_m": " ".join(
                    f"{cid}:{length:.6f}" for cid, length in zip(active, branch_required_lengths)
                ),
                "required_turns_for_branch_target_air_core": " ".join(
                    f"{cid}:{turns:.6f}" for cid, turns in zip(active, branch_required_turns)
                ),
                "material_note": bobbin.material_note,
            }
        )
        for cid, length, rac, turns, l_air, l_wheeler, req_len, req_turns, extra_len in zip(
            active,
            seg_lengths,
            seg_rac,
            turns_by_cable,
            grover_l_each_branch,
            wheeler_l_each_branch,
            branch_required_lengths,
            branch_required_turns,
            branch_extra_lengths,
        ):
            wire = wire_by_cable[cid]
            branch_rows.append(
                {
                    "stage": stage,
                    "cable": cid,
                    "frequency_Hz": f,
                    "frequency_kHz": f / 1e3,
                    "stage_equivalent_impedance_ohm": z_ab,
                    "active_branch_count": len(active),
                    "branch_target_impedance_ohm": branch_target_z,
                    "branch_target_L_uH": branch_target_l * 1e6,
                    "branch_target_C_nF": branch_target_c * 1e9,
                    "segment_length_m": length,
                    "bobbin_family": bobbin.family,
                    "mean_turn_length_m": mean_turn_length_m,
                    "turns_on_bobbin": turns,
                    "estimated_air_core_L_uH": l_air * 1e6,
                    "grover_loop_array_L_uH": l_air * 1e6,
                    "wheeler_single_layer_L_uH": l_wheeler * 1e6,
                    "series_trim_L_uH_if_needed": max(0.0, branch_target_l - l_air) * 1e6,
                    "physical_minus_target_L_uH": (l_air - branch_target_l) * 1e6,
                    "physical_to_target_L_percent": 100.0 * l_air / branch_target_l if branch_target_l > 0 else 0.0,
                    "physical_air_core_to_branch_target_percent": 100.0 * l_air / branch_target_l if branch_target_l > 0 else 0.0,
                    "required_turns_for_branch_target_air_core": req_turns,
                    "required_length_for_branch_target_air_core_m": req_len,
                    "required_extra_length_for_branch_target_air_core_m": extra_len,
                    "wire_historical_awg": wire["historical_awg_from_russell_text"],
                    "wire_recommended_awg_equiv": wire["recommended_modern_awg_equivalent"],
                    "wire_litz": f"{wire['strand_count']} x AWG{wire['strand_awg']}",
                    "estimated_litz_od_mm": wire["estimated_silk_litz_od_mm"],
                    "copper_area_mm2": wire["copper_area_mm2"],
                    "Rac_60C_ohm": rac,
                    "equal_share_current_4kW_Arms": branch_i_min,
                    "equal_share_current_10kW_Arms": branch_i_max,
                    "current_density_10kW_A_per_mm2": branch_i_max / wire["copper_area_mm2"],
                    "note": "Physical wound length is solved so the Grover air-core inductance matches the branch L target; C is then selected for the octave resonance and branch impedance.",
                }
            )
        stage_rows.append(
            {
                "stage": stage,
                "mirror_pair": {"A1": "B1", "A2": "B2", "A3": "B3", "A4": "B4", "B4": "A4", "B3": "A3", "B2": "A2", "B1": "A1"}[stage],
                "frequency_Hz": f,
                "frequency_kHz": f / 1e3,
                "target_impedance_ohm": z_ab,
                "target_L_uH": target_l * 1e6,
                "target_C_nF": target_c * 1e9,
                "branch_target_impedance_ohm": branch_target_z,
                "branch_target_L_uH": branch_target_l * 1e6,
                "branch_target_C_nF": branch_target_c * 1e9,
                "active_cables": " ".join(active),
                "active_cable_count": len(active),
                "total_copper_length_in_stage_m": sum(seg_lengths),
                "segment_lengths_m": " ".join(f"{x:.6f}" for x in seg_lengths),
                "uncoupled_physical_parallel_L_uH": physical_parallel_l * 1e6,
                "physical_parallel_to_target_L_percent": physical_to_target_pct,
                "max_physical_branch_L_uH": max(grover_l_each_branch) * 1e6,
                "max_branch_required_length_for_target_air_core_m": max(branch_required_lengths),
                "estimated_parallel_Rac_60C_ohm": r_eq,
                "estimated_Q_Z_over_Rac": z_ab / r_eq,
                "current_4kW_Arms": i_min,
                "current_10kW_Arms": i_max,
                "equal_share_branch_current_4kW_Arms": branch_i_min,
                "equal_share_branch_current_10kW_Arms": branch_i_max,
                "loss_4kW_W": loss_min,
                "loss_10kW_W": loss_max,
                "equalized_branch_loss_4kW_W": loss_min_equalized,
                "equalized_branch_loss_10kW_W": loss_max_equalized,
                "min_current_share_if_unballasted": min_share,
                "max_current_share_if_unballasted": max_share,
                "note": "Stage impedance is held by equalized physical air-core branch inductances and capacitors; all C cables use the same end-to-end length with non-inductive equalizing sections.",
            }
        )
    write_csv(out_dir / "stage_impedance_power.csv", stage_rows)
    write_csv(out_dir / "branch_lc_tuning_plan.csv", branch_rows)
    write_csv(out_dir / "bobbin_geometry_and_fill.csv", bobbin_rows)

    response_rows = []
    q_loaded = 20.0
    for row in stage_rows:
        L = row["target_L_uH"] * 1e-6
        C = row["target_C_nF"] * 1e-9
        r_loaded = z_ab / q_loaded
        for ratio in [0.5, 0.70710678, 0.9, 1.0, 1.1, 1.41421356, 2.0]:
            f = row["frequency_Hz"] * ratio
            w = 2 * math.pi * f
            x_l = w * L
            x_c = 1 / (w * C)
            x_net = x_l - x_c
            response_rows.append(
                {
                    "stage": row["stage"],
                    "target_frequency_Hz": row["frequency_Hz"],
                    "frequency_ratio": ratio,
                    "frequency_Hz": f,
                    "target_impedance_ohm": z_ab,
                    "loaded_Q_assumption": q_loaded,
                    "R_loaded_series_ohm": r_loaded,
                    "X_L_ohm": x_l,
                    "X_C_ohm": x_c,
                    "X_net_ohm": x_net,
                    "Z_abs_loaded_series_ohm": math.hypot(r_loaded, x_net),
                    "phase_deg": math.degrees(math.atan2(x_net, r_loaded)),
                }
            )
    write_csv(out_dir / "ab_frequency_response.csv", response_rows)

    e1_turns = 8.0
    gaps = [1e-3, 2e-3, 5e-3, 10e-3]
    b_limits = [0.025, 0.05, 0.10]
    amcc_rows = []
    for gap in gaps:
        L = inductance_h(AMCC1000, e1_turns, gap)
        for b_lim in b_limits:
            amcc_rows.append(
                {
                    "gap_mm": gap * 1e3,
                    "frequency_Hz": f_metglas,
                    "frequency_kHz": f_metglas / 1e3,
                    "turns_E1_reference": e1_turns,
                    "L_mH": L * 1e3,
                    "X_L_ohm": 2 * math.pi * f_metglas * L,
                    "C_resonance_nF": cap_for_resonance_f(f_metglas, L) * 1e9,
                    "B_limit_T": b_lim,
                    "Vrms_at_B_limit": v_rms_for_b(AMCC1000, e1_turns, f_metglas, b_lim),
                    "Irms_magnetizing_at_B_limit": i_peak_for_b(AMCC1000, e1_turns, b_lim, gap) / math.sqrt(2),
                }
            )
    write_csv(out_dir / "amcc1000_128k_sweep.csv", amcc_rows)

    # Orthogonal paraformer centre: two AMCC-1000 U/C-core halves, one rotated
    # 90 degrees. This is a lumped geometry/coupling model; final coupling must
    # be measured or extracted with FEMM/COMSOL/Ansys Maxwell.
    paraformer_gap_m = 2e-3
    paraformer_turns = 8.0
    paraformer_l = inductance_h(AMCC1000, paraformer_turns, paraformer_gap_m)
    paraformer_k_orthogonal = 0.08
    paraformer_m = paraformer_k_orthogonal * paraformer_l
    paraformer_rows = [
        {
            "part": "U_A",
            "core": "AMCC-1000 half / U-core equivalent",
            "orientation_deg_about_optical_axis": 0,
            "flux_axis": "X",
            "winding": "E1_A",
            "turns_reference": paraformer_turns,
            "gap_mm": paraformer_gap_m * 1e3,
            "L_self_mH": paraformer_l * 1e3,
            "X_L_at_128k_ohm": 2 * math.pi * f_metglas * paraformer_l,
            "note": "first U side of orthogonal paraformer centre",
        },
        {
            "part": "U_B",
            "core": "AMCC-1000 half / U-core equivalent",
            "orientation_deg_about_optical_axis": 90,
            "flux_axis": "Y",
            "winding": "E1_B",
            "turns_reference": paraformer_turns,
            "gap_mm": paraformer_gap_m * 1e3,
            "L_self_mH": paraformer_l * 1e3,
            "X_L_at_128k_ohm": 2 * math.pi * f_metglas * paraformer_l,
            "note": "second U side rotated 90 degrees; not closed as an ordinary transformer pair",
        },
    ]
    paraformer_coupling_rows = [
        {
            "from": "U_A",
            "to": "U_B",
            "angle_deg": 90,
            "assumed_k": paraformer_k_orthogonal,
            "M_mH": paraformer_m * 1e3,
            "coupling_note": "orthogonal paraformer estimate; tune and measure with VNA/LCR because this is not a scalar closed-core transformer",
        }
    ]
    write_csv(out_dir / "paraformer_u_core_geometry.csv", paraformer_rows)
    write_csv(out_dir / "paraformer_coupling_matrix.csv", paraformer_coupling_rows)

    bus_rows = []
    for topology, fn in [("half_bridge", half_bridge_fundamental_rms), ("full_bridge", full_bridge_fundamental_rms)]:
        for vbus in [400, 500, 600, 700, 800, 900]:
            v1 = fn(vbus)
            p = v1**2 / z_ab
            bus_rows.append(
                {
                    "topology": topology,
                    "dc_bus_V": vbus,
                    "fundamental_Vrms": v1,
                    "power_into_50ohm_W": p,
                    "current_into_50ohm_Arms": v1 / z_ab,
                    "in_4_to_10kW_window": power_min <= p <= power_max,
                    "safety_note": "Use only a protected isolated resonant inverter with interlocks and current limiting.",
                }
            )
    write_csv(out_dir / "power_bus_envelope.csv", bus_rows)

    summary = {
        "machine_readable_name": "walter_russell_optical_dynamo_generator",
        "core": asdict(AMCC1000),
        "power_window_W": [power_min, power_max],
        "target_ab_impedance_ohm": z_ab,
        "metglas_frequency_Hz": f_metglas,
        "ab_octave_frequencies_Hz": {
            "A1_B1": f_base,
            "A2_B2": 2 * f_base,
            "A3_B3": 4 * f_base,
            "A4_B4": 8 * f_base,
        },
        "common_end_to_end_active_length_each_cable_m": common_active_length_m,
        "wound_length_by_cable_m": cable_wound_total_m,
        "non_inductive_equalizing_length_by_cable_m": cable_equalizing_length_m,
        "cable_count": 8,
        "total_active_cable_m": common_active_length_m * len(cable_ids),
        "total_cut_plus_3pct_m": (common_active_length_m + lead_allowance_m) * (1 + reserve) * len(cable_ids),
        "wire_recommendation": {
            "C1_C2": "silk-covered AWG10-equivalent RF Litz, 416 x AWG36",
            "C3_C4": "silk-covered AWG12-equivalent RF Litz, 262 x AWG36",
            "C5_C8": "silk-covered AWG18-equivalent RF Litz, 65 x AWG36",
        },
        "historical_awg_lineage": "Russell source text: two AWG14, two AWG18, four AWG22; modern RF design upsizes C1-C2/C3-C4/C5-C8 for 4-10 kW.",
        "bobbin_geometry": {
            "large": asdict(BOBBIN_SPECS["large"]),
            "small": asdict(BOBBIN_SPECS["small"]),
        },
        "paraformer_centre": {
            "core": "two AMCC-1000 U/C-core halves in orthogonal paraformer layout",
            "orientation": "U_A at 0 degrees, U_B rotated 90 degrees about the central optical/wave axis",
            "assumed_orthogonal_coupling_k": paraformer_k_orthogonal,
            "gap_mm": paraformer_gap_m * 1e3,
        },
        "latest_note_interpretation": "A1/A2 and B1/B2 use C1-C2; A3/B3 use C1-C4; A4/B4 use C1-C8.",
        "inductance_model": "single-layer finite-solenoid Grover coaxial-loop summation with loop self-inductance; Wheeler is retained as a comparison column",
        "quarter_wave_note": "40 m is not a quarter-wave at 128 kHz; this design uses lumped L/C tuning.",
        "important_inductance_note": "The design now solves every wound segment length from the Grover finite-solenoid inductance model. The earlier 5 m A1 segment is not used as a physical-inductance solution.",
        "equal_length_rule": "C1-C8 have the same end-to-end active length; cables whose wound coil sum is shorter receive non-inductive equalizing length outside the bobbins.",
        "references": [
            "https://metglas.com/magnetic-materials/",
            "https://metglas.com/wp-content/uploads/2021/06/2605SA1-Magnetic-Alloy-Updated.pdf",
            "https://www.hilltech.com/pdf/amor_cores/AMCC1000%2C%20rev.07.pdf",
        ],
        "safety_boundary": "4-10 kW is a protected system envelope, not a bare MOSFET gate-driver build.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    design(Path(__file__).resolve().parent / "outputs")


if __name__ == "__main__":
    main()
