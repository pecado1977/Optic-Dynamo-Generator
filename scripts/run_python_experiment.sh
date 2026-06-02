#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 - <<'PY'
import importlib.util
missing = [name for name in ("numpy", "PIL") if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python dependencies:", ", ".join(missing))
    print("Install them with: pip install -r requirements.txt")
    raise SystemExit(1)
PY

python3 dynamic_power_multilang_simulator/python/dynamic_power_simulator_updated_coils_20260531.py

echo
echo "Experiment outputs:"
echo "  dynamic_power_multilang_simulator/outputs_updated_coils_20260531"
echo "  dynamic_power_multilang_simulator/figures_updated_coils_20260531"
