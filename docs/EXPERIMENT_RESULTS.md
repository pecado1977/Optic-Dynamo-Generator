# Experiment Results Map

The latest updated-coil experiment output lives in:

```text
dynamic_power_multilang_simulator/outputs_updated_coils_20260531/
```

Important CSV files:

| File | Purpose |
|---|---|
| `power_simulation_summary.json` | single-run top-level summary |
| `metglas_signal_summary.csv` | RMS/peak Metglas currents, voltages, flux and mutual power |
| `metglas_dynamic_waveforms.csv` | sampled time-domain Metglas waveforms |
| `metglas_transformer_transfer_limit.csv` | matched-load Thevenin limits |
| `metglas_transformer_transfer_sweep.csv` | transfer limit versus coupling k |
| `orthogonal_paraformer_10kw_cable_plan.csv` | near-10 kW orthogonal design point |
| `stage_rms_watts_amps_volts_summary.csv` | stage-level RMS W/A/V/VAR values |
| `mode_rms_power_reactive_summary.csv` | per-mode RMS and reactive-power values |
| `core_dynamic_summary.csv` | AMCC-1000 U_A/U_B dynamic state summary |

Important figures:

```text
dynamic_power_multilang_simulator/figures_updated_coils_20260531/metglas_core_currents.png
dynamic_power_multilang_simulator/figures_updated_coils_20260531/metglas_core_voltages.png
dynamic_power_multilang_simulator/figures_updated_coils_20260531/metglas_input_output_signals.png
dynamic_power_multilang_simulator/figures_updated_coils_20260531/metglas_transferred_power_time.png
dynamic_power_multilang_simulator/figures_updated_coils_20260531/metglas_transfer_power_sweep.png
dynamic_power_multilang_simulator/figures_updated_coils_20260531/orthogonal_paraformer_10kw_design.png
```

To regenerate:

```bash
./scripts/run_python_experiment.sh
```
