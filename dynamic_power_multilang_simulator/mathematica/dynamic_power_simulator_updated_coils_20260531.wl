(* Versioned Wolfram Language runner for the 2026-05-31 updated-coil design.

   The canonical Wolfram simulator reads the current Grover-solved coil tables
   and exports the same Metglas essentials as the Python and MATLAB versions:
   currents, voltages, input/output monitor signals, and transferred power.
   This wrapper preserves the canonical script and copies the resulting files
   into versioned output folders.
*)

ClearAll["Global`*"];

scriptDir = DirectoryName[$InputFileName];
rootDir = DirectoryName[scriptDir];
versionTag = "updated_coils_20260531";

Get[FileNameJoin[{scriptDir, "dynamic_power_simulator.wl"}]];

srcOut = FileNameJoin[{rootDir, "outputs_mathematica"}];
srcFig = FileNameJoin[{rootDir, "figures_mathematica"}];
dstOut = FileNameJoin[{rootDir, "outputs_mathematica_" <> versionTag}];
dstFig = FileNameJoin[{rootDir, "figures_mathematica_" <> versionTag}];

If[DirectoryQ[dstOut], DeleteDirectory[dstOut, DeleteContents -> True]];
If[DirectoryQ[dstFig], DeleteDirectory[dstFig, DeleteContents -> True]];
If[DirectoryQ[srcOut], CopyDirectory[srcOut, dstOut]];
If[DirectoryQ[srcFig], CopyDirectory[srcFig, dstFig]];

Print["Versioned Wolfram updated-coil outputs copied to ", dstOut];
Print["Versioned Wolfram updated-coil figures copied to ", dstFig];
