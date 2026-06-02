# Walter Russell Optical Dynamo / AMCC-1000 Paraformer Simulator

This repository contains a reproducible simulation package for the updated
Walter Russell Optical Dynamo Generator interpretation with an orthogonal
Metglas AMCC-1000 paraformer center.

The default experiment state is the latest updated-coil model:

- eight-stage A/B ladder: A1-A4 and B1-B4
- eight equal end-to-end C cables: C1-C8
- octave frequencies: 16, 32, 64 and 128 kHz
- external stage impedance held at 50 ohm
- orthogonal AMCC-1000 Metglas center at 128 kHz
- default weak orthogonal coupling: k = 0.08
- separate high-stress near-10 kW paraformer design point

The simulator is a conventional electromagnetic RLC/mutual-inductance model.
It does not assume a non-classical energy source. Reported watts, volt-amperes
and vars come from the coupled state equations, phasor extraction, RMS
post-processing and matched-load Thevenin transfer limits.

## Repository Layout

```text
dynamic_power_multilang_simulator/
  python/                         Python dynamic power simulator
  config/                         default simulation configuration
  outputs_updated_coils_20260531/ CSV outputs from the latest updated run
  figures_updated_coils_20260531/ PNG/GIF figures from the latest updated run

dynamic_standing_wave_simulator/
  src/                            shared standing-wave simulation support code
  config/                         standing-wave default configuration

generator/
  outputs/                        selected design CSVs used by the simulator

StateDependentParaformerSimulator/
  StateDependentParaformerSimulator.xcodeproj
  StateDependentParaformerSimulator/ Objective-C AppKit interactive simulator

scripts/
  run_python_experiment.sh        run latest Python experiment
  build_xcode_app.sh              build the Objective-C macOS simulator
  clean_generated_outputs.sh      remove local generated/cache files
```

## Quick Start: Python Experiment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_python_experiment.sh
```

The run writes updated CSV summaries and figures to:

```text
dynamic_power_multilang_simulator/outputs_updated_coils_20260531/
dynamic_power_multilang_simulator/figures_updated_coils_20260531/
```

Key files:

- `metglas_signal_summary.csv`
- `metglas_transformer_transfer_limit.csv`
- `orthogonal_paraformer_10kw_cable_plan.csv`
- `stage_rms_watts_amps_volts_summary.csv`
- `metglas_core_currents.png`
- `metglas_core_voltages.png`
- `metglas_input_output_signals.png`
- `metglas_transferred_power_time.png`

## Quick Start: Objective-C AppKit Simulator

Build from the repository root:

```bash
./scripts/build_xcode_app.sh
```

The script builds:

```text
StateDependentParaformerSimulator/.derivedData/Build/Products/Debug/StateDependentParaformerSimulator.app
```

The AppKit simulator starts from the same WR/AMCC-1000 default parameters and
provides interactive controls for:

- frequency
- coupling coefficient k
- drive voltage
- inductance
- capacitance
- dynamic resistance
- load resistance
- temperature
- turns
- gap
- permeability scale
- saturation flux density
- capacitance state term
- resistance temperature coefficient
- phase offset

Realtime plots show voltage, current, dynamic resistance and matched transfer
power.

## Important Current Numerical Reference

Default AMCC-1000 center:

| Quantity | Value |
|---|---:|
| Frequency | 128 kHz |
| Coupling | k = 0.08 |
| Core inductance | 92.051753 uH |
| Resonance capacitance | 16.795319 nF |
| Dynamic damping resistance | 6.169368 ohm |
| Mutual inductance | 7.364140 uH |
| Default dynamic U_A to U_B matched limit | 8.711158 W |
| 50 mT target-current U_A to U_B limit | 70.991223 W |

Near-10 kW orthogonal paraformer design point:

| Quantity | Value |
|---|---:|
| Frequency | 128 kHz |
| Coupling | k = 0.08 |
| Required peak flux density | 0.593428 T |
| Turns per winding | 12 |
| Primary current | 55.917426 Arms |
| Primary voltage | 9314.329475 Vrms |
| Secondary open-circuit voltage | 745.146358 Vrms |
| Matched secondary load | 13.881077 ohm |
| Matched secondary current | 26.840365 Arms |
| Matched secondary power | 10000 W |
| Circulating reactive power | 0.520833 MVAR |

## Safety Notice

This repository is for numerical simulation, documentation and low-power bench
planning. The near-10 kW design point involves high voltage, high RF current,
high circulating reactive power, insulation stress and potentially hazardous
thermal behavior. Do not build or energize hardware from this repository
without appropriate engineering review, current limiting, isolation,
instrumentation, shielding and safety procedures.

## License

See `LICENSE`.
