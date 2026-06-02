# WR / AMCC-1000 Model Assumptions

This repository uses the updated 2026-05-31 Walter Russell Optical Dynamo
Generator interpretation.

## A/B Ladder

- A-side stages: A1, A2, A3, A4
- B-side stages: B4, B3, B2, B1
- Octave stage frequencies: 16, 32, 64 and 128 kHz
- External stage impedance: 50 ohm
- Branch impedance rises with active branch count so that the parallel stage
  value remains 50 ohm.

## C Cable Rule

All C1-C8 cables have the same end-to-end active length:

```text
445.293167 m
```

Wound lengths differ by stage. The remainder is treated as non-inductive
equalizer length.

## AMCC-1000 Center

The Metglas center is simulated as two orthogonal U-core modes:

- U_A: X-axis
- U_B: Y-axis, rotated 90 degrees
- default coupling: k = 0.08
- default resonance: 128 kHz
- default L: 92.051753 uH
- default C: 16.795319 nF
- default dynamic R: 6.169368 ohm

## Near-10 kW Design Point

The near-10 kW point is a separate high-stress extrapolation, not the measured
or default full-ladder dynamic state. It requires high flux density and high
circulating reactive power.
