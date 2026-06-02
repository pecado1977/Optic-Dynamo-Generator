#!/usr/bin/env python3
"""Versioned dynamic simulator for the 2026-05-31 updated-coil design.

This runner uses the current canonical coil tables in
``walter_russell_optical_dynamo_generator/outputs``.  Those tables contain the
Grover-solved winding lengths and turns, equal end-to-end C1-C8 cable length,
constant 50 ohm A/B stage impedance, octave excitation, and the orthogonal
AMCC-1000 paraformer center.

The output is intentionally written to new versioned folders so older simulator
results remain available for comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamic_power_simulator import run  # noqa: E402


VERSION = "updated_coils_20260531"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "default_config.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / f"outputs_{VERSION}")
    parser.add_argument("--fig-dir", type=Path, default=ROOT / f"figures_{VERSION}")
    args = parser.parse_args()

    summary = run(args.config, args.out_dir, args.fig_dir)
    summary["simulator_version"] = VERSION
    summary["coil_source"] = str((ROOT.parent / "generator" / "outputs").resolve())
    (args.out_dir / "power_simulation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
