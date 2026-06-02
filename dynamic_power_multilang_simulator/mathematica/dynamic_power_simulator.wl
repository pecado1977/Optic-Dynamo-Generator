(* Dynamic RMS/W/VAR simulator for walter_russell_optical_dynamo_generator.
   Mathematica/Wolfram Language reference implementation.
   It reads the same current CSV design files and solves:
   Lmatrix.i'[t] = Vsource[t] - R.i[t] - Vc[t]
   Vc'[t] = C^-1.i[t]
*)

ClearAll["Global`*"];

scriptDir = DirectoryName[$InputFileName];
rootDir = DirectoryName[scriptDir];
repoRoot = DirectoryName[rootDir];
inputDir = FileNameJoin[{repoRoot, "walter_russell_optical_dynamo_generator", "outputs"}];
outDir = FileNameJoin[{rootDir, "outputs_mathematica"}];
figDir = FileNameJoin[{rootDir, "figures_mathematica"}];
CreateDirectory[outDir, CreateIntermediateDirectories -> True];
CreateDirectory[figDir, CreateIntermediateDirectories -> True];

powerW = 10000.;
zStage = 50.;
baseHz = 16000.;
maxHz = 128000.;
loadedQ = 20.;
coreLoadedQ = 12.;
stepsPer128k = 64;
cyclesAt16k = 72;
sampleStride = 4;
rampCyclesAt16k = 8;

stageOrder = {"A1", "A2", "A3", "A4", "B4", "B3", "B2", "B1"};
stagePosition = <|"A1" -> -3.5, "A2" -> -2.5, "A3" -> -1.5, "A4" -> -0.5,
  "B4" -> 0.5, "B3" -> 1.5, "B2" -> 2.5, "B1" -> 3.5|>;
mirror = <|"A1" -> "B1", "A2" -> "B2", "A3" -> "B3", "A4" -> "B4",
  "B4" -> "A4", "B3" -> "A3", "B2" -> "A2", "B1" -> "A1"|>;

csvAssoc[file_] := Module[{raw, head, rows},
  raw = Import[file, "CSV"];
  head = ToString /@ First[raw];
  rows = Rest[raw];
  AssociationThread[head, #] & /@ rows
];

num[x_] := Quiet@Check[ToExpression[x], 0.];
stagePhase[stage_, fhz_] := Module[{xs, xnorm, mode},
  xs = Values[stagePosition];
  xnorm = (stagePosition[stage] - Min[xs])/(Max[xs] - Min[xs]);
  mode = Max[1, Round[fhz/baseHz]];
  mode*Pi*xnorm
];

branch = csvAssoc[FileNameJoin[{inputDir, "branch_lc_tuning_plan.csv"}]];
core = csvAssoc[FileNameJoin[{inputDir, "paraformer_u_core_geometry.csv"}]];
amcc = csvAssoc[FileNameJoin[{inputDir, "amcc1000_128k_sweep.csv"}]];

names = {}; kinds = {}; stages = {}; cables = {};
f = {}; lvals = {}; cvals = {}; rcu = {}; rdyn = {}; targetI = {}; zbranch = {};
driveV = {}; phase = {}; turns = {}; ae = {};
stageI = Sqrt[powerW/zStage];

Do[
  st = row["stage"]; cab = row["cable"]; fhz = num[row["frequency_Hz"]];
  active = num[row["active_branch_count"]];
  zbr = num[row["branch_target_impedance_ohm"]];
  Lh = num[row["branch_target_L_uH"]]*10^-6;
  Cf = num[row["branch_target_C_nF"]]*10^-9;
  R = num[row["Rac_60C_ohm"]];
  Rload = Max[zbr/loadedQ, 5 R];
  It = stageI/active;
  AppendTo[names, st <> "_" <> cab]; AppendTo[kinds, "branch"];
  AppendTo[stages, st]; AppendTo[cables, cab]; AppendTo[f, fhz];
  AppendTo[lvals, Lh]; AppendTo[cvals, Cf]; AppendTo[rcu, R]; AppendTo[rdyn, Rload];
  AppendTo[targetI, It]; AppendTo[zbranch, zbr]; AppendTo[driveV, Sqrt[2] It Rload];
  AppendTo[phase, stagePhase[st, fhz]]; AppendTo[turns, 0.]; AppendTo[ae, 0.],
  {row, branch}
];

coreRef = SelectFirst[amcc, Abs[num[#["gap_mm"]] - 2.] < 10^-9 && Abs[num[#["B_limit_T"]] - 0.05] < 10^-9 &, First[amcc]];
Do[
  part = row["part"]; fhz = maxHz;
  Lh = num[row["L_self_mH"]]*10^-3;
  Cf = 1/((2 Pi fhz)^2 Lh);
  xL = 2 Pi fhz Lh;
  AppendTo[names, part]; AppendTo[kinds, "core"]; AppendTo[stages, part]; AppendTo[cables, "E1"];
  AppendTo[f, fhz]; AppendTo[lvals, Lh]; AppendTo[cvals, Cf]; AppendTo[rcu, 0.]; AppendTo[rdyn, xL/coreLoadedQ];
  AppendTo[targetI, num[coreRef["Irms_magnetizing_at_B_limit"]]]; AppendTo[zbranch, xL];
  AppendTo[driveV, 0.]; AppendTo[phase, If[part == "U_B", Pi/2, 0.]];
  AppendTo[turns, num[row["turns_reference"]]]; AppendTo[ae, 23.0*10^-4],
  {row, core}
];

n = Length[names];
lmat = DiagonalMatrix[lvals];
couplingRows = {};
addCoupling[i_, j_, k_, typ_] := Module[{m},
  If[i == j || k == 0, Return[]];
  m = k*Sqrt[lvals[[i]] lvals[[j]]];
  lmat[[i, j]] += m; lmat[[j, i]] += m;
  AppendTo[couplingRows, {names[[i]], names[[j]], k, m*10^6, typ}]
];

Do[
  idx = Flatten@Position[MapThread[#1 == "branch" && #2 == cab &, {kinds, cables}], True];
  idx = SortBy[idx, First@Flatten@Position[stageOrder, stages[[#]]] &];
  Do[addCoupling[idx[[p]], idx[[p + 1]], 0.008, "same cable adjacent stage"], {p, Length[idx] - 1}],
  {cab, DeleteDuplicates[Pick[cables, kinds, "branch"]]}
];

Do[
  idx = Flatten@Position[MapThread[#1 == "branch" && #2 == st &, {kinds, stages}], True];
  Do[If[a < b, addCoupling[idx[[a]], idx[[b]], 0.0025, "co-located stage"]], {a, Length[idx]}, {b, Length[idx]}],
  {st, stageOrder}
];

Do[
  other = mirror[st];
  cabs = DeleteDuplicates[Pick[cables, MapThread[#1 == "branch" && #2 == st &, {kinds, stages}]]];
  Do[
    a = FirstPosition[MapThread[#1 == st && #2 == cab &, {stages, cables}], True, Missing[]];
    b = FirstPosition[MapThread[#1 == other && #2 == cab &, {stages, cables}], True, Missing[]];
    If[ListQ[a] && ListQ[b], addCoupling[First[a], First[b], If[st == "A4", 0.020, 0.004], "mirror or center pair"]],
    {cab, cabs}],
  {st, {"A1", "A2", "A3", "A4"}}
];

ua = First@Flatten@Position[names, "U_A"]; ub = First@Flatten@Position[names, "U_B"];
Do[addCoupling[ua, idx, 0.012, "U_A to A4"], {idx, Flatten@Position[stages, "A4"]}];
Do[addCoupling[ub, idx, 0.012, "U_B to B4"], {idx, Flatten@Position[stages, "B4"]}];
addCoupling[ua, ub, 0.080, "orthogonal U_A/U_B core"];

dt = 1/(maxHz*stepsPer128k);
duration = cyclesAt16k/baseHz;
rampS = rampCyclesAt16k/baseHz;
steps = Ceiling[duration/dt];
linv = Inverse[lmat];
cInv = 1/cvals;

sourceVec[t_] := Module[{ramp},
  ramp = If[rampS <= 0, 1, Min[1, t/rampS]];
  If[ramp < 1, ramp = 0.5 - 0.5 Cos[Pi ramp]];
  Table[ramp*driveV[[i]]*Sin[2 Pi f[[i]] t + phase[[i]]], {i, n}]
];

rhs[t_, y_] := Module[{ii, vc, di, dvc},
  ii = y[[1 ;; n]]; vc = y[[n + 1 ;; 2 n]];
  di = linv.(sourceVec[t] - rdyn*ii - vc);
  dvc = cInv*ii;
  Join[di, dvc]
];

y = ConstantArray[0., 2 n]; ts = {}; isamp = {}; vcsamp = {};
Do[
  t = step*dt;
  If[Mod[step, sampleStride] == 0, AppendTo[ts, t]; AppendTo[isamp, y[[1 ;; n]]]; AppendTo[vcsamp, y[[n + 1 ;; 2 n]]]];
  k1 = rhs[t, y]; k2 = rhs[t + dt/2, y + dt*k1/2]; k3 = rhs[t + dt/2, y + dt*k2/2]; k4 = rhs[t + dt, y + dt*k3];
  y = y + dt/6 (k1 + 2 k2 + 2 k3 + k4),
  {step, 0, steps}
];

ss = Range[Floor[Length[ts]/2], Length[ts]];
tss = ts[[ss]]; iss = isamp[[ss]]; vcss = vcsamp[[ss]];
phasorRms[x_, fhz_] := 2/Length[tss] Total[x*Exp[-I*2 Pi fhz*tss]]/Sqrt[2];

modeRows = Table[
  Iph = phasorRms[iss[[All, i]], f[[i]]];
  Vcph = phasorRms[vcss[[All, i]], f[[i]]];
  Vsph = phasorRms[Table[sourceVec[tss[[q]]][[i]], {q, Length[tss]}], f[[i]]];
  w = 2 Pi f[[i]]; xL = w*lvals[[i]]; xC = 1/(w*cvals[[i]]);
  Ssrc = Vsph*Conjugate[Iph];
  {names[[i]], kinds[[i]], stages[[i]], cables[[i]], f[[i]], Abs[Iph], Abs[Vsph], Abs[Vcph], Abs[Iph]*xL,
   Re[Ssrc], Im[Ssrc], Abs[Ssrc], Abs[Iph]^2 rdyn[[i]], Abs[Iph]^2 rcu[[i]], Abs[Iph]^2 xL, -Abs[Iph]^2 xC},
  {i, n}
];
modeHead = {"mode","kind","stage","cable","frequency_Hz","I_rms_A","V_source_rms_V","V_capacitor_rms_V","V_inductor_rms_V","P_source_W","Q_source_VAR","S_source_VA","P_dynamic_damping_W","P_copper_W","Q_inductor_VAR","Q_capacitor_VAR"};
Export[FileNameJoin[{outDir, "mathematica_mode_rms_power_reactive_summary.csv"}], Prepend[modeRows, modeHead]];

stageRows = Table[
  idx = Flatten@Position[MapThread[#1 == "branch" && #2 == st &, {kinds, stages}], True];
  p = Total[modeRows[[idx, 10]]]; q = Total[modeRows[[idx, 11]]]; s = Sqrt[p^2 + q^2]; vbus = Sqrt[powerW zStage];
  {st, f[[First[idx]]], Length[idx], vbus, s/vbus, p, q, s, Total[modeRows[[idx, 13]]], Total[modeRows[[idx, 14]]],
   Total[modeRows[[idx, 15]]], Total[modeRows[[idx, 16]]], Total[modeRows[[idx, 15]]] + Total[modeRows[[idx, 16]]]},
  {st, stageOrder}
];
stageHead = {"stage","frequency_Hz","active_branch_count","bus_V_rms_50ohm_V","stage_I_rms_from_source_power_A","P_source_W","Q_source_VAR","S_source_VA","P_dynamic_damping_W","P_copper_W","Q_inductor_VAR_sum","Q_capacitor_VAR_sum","Q_lc_net_VAR"};
Export[FileNameJoin[{outDir, "mathematica_stage_rms_watts_amps_volts_summary.csv"}], Prepend[stageRows, stageHead]];

Iua = modeRows[[ua, 6]]; Itarget = targetI[[ua]]; M = lmat[[ua, ub]]; w = 2 Pi maxHz;
Pdyn = (w Abs[M] Iua)^2/(4 rdyn[[ub]]);
Ptgt = (w Abs[M] Itarget)^2/(4 rdyn[[ub]]);
transferRows = {{"k","M_uH","dynamic_UA_I_rms_A","target_50mT_I_rms_A","Pmax_dynamic_W","Pmax_target_50mT_W"},
  {0.08, M*10^6, Iua, Itarget, Pdyn, Ptgt}};
Export[FileNameJoin[{outDir, "mathematica_metglas_transformer_transfer_limit.csv"}], transferRows];

targetP = 10000.; kOrtho = 0.08; bRef = 0.05; vRef = 523.1938947975291; nRef = turns[[ua]];
lRef = lvals[[ua]]; rRef = rdyn[[ua]]; iRef = targetI[[ua]];
targetMaxI = 60.; jTarget = 3.; mtl = 0.85; reserve = 0.15; awg10Area = 5.261154954510373;
bRequired = bRef Sqrt[targetP/Ptgt];
nSelected = Ceiling[nRef*iRef*(bRequired/bRef)/targetMaxI];
iPrimary = iRef*(bRequired/bRef)*(nRef/nSelected);
vPrimary = vRef*(bRequired/bRef)*(nSelected/nRef);
lSelected = lRef*(nSelected/nRef)^2;
rSelected = rRef*(nSelected/nRef)^2;
xSelected = 2 Pi maxHz lSelected;
cSelected = 1/((2 Pi maxHz)^2 lSelected);
mSelected = kOrtho*lSelected;
vSecondary = 2 Pi maxHz*mSelected*iPrimary;
pmaxSelected = vSecondary^2/(4 rSelected);
areaNeeded = iPrimary/jTarget;
parallelBundles = Ceiling[areaNeeded/awg10Area];
copperArea = parallelBundles*awg10Area;
cablePerParallel = nSelected*mtl;
cablePerWindingBuy = cablePerParallel*parallelBundles*(1 + reserve);
orthoPlanRows = {
  {"target_power_W","assumed_k","required_B_peak_T","selected_turns_per_winding","primary_winding_I_rms_A","primary_winding_V_rms_V","secondary_open_circuit_V_rms","secondary_matched_load_R_ohm","Pmax_matched_secondary_W","L_self_mH","M_mutual_uH","X_L_ohm","C_resonance_nF","Q_inductor_VAR","selected_parallel_AWG10_equiv_Litz_bundles","selected_copper_area_mm2","actual_current_density_A_per_mm2","active_cable_per_parallel_bundle_m","procurement_cable_per_winding_m","procurement_cable_two_windings_m"},
  {targetP, kOrtho, bRequired, nSelected, iPrimary, vPrimary, vSecondary, rSelected, pmaxSelected, lSelected*10^3, mSelected*10^6, xSelected, cSelected*10^9, iPrimary^2*xSelected, parallelBundles, copperArea, iPrimary/copperArea, cablePerParallel, cablePerWindingBuy, 2 cablePerWindingBuy}
};
Export[FileNameJoin[{outDir, "mathematica_orthogonal_paraformer_10kw_cable_plan.csv"}], orthoPlanRows];

derivative[x_, tt_] := Module[{d},
  d = Differences[x]/Differences[tt];
  Join[{First[d]}, d]
];
di = Transpose@Table[derivative[iss[[All, i]], tss], {i, n}];
mUAUB = lmat[[ua, ub]];
vUBfromUA = mUAUB*di[[All, ua]];
vUAfromUB = mUAUB*di[[All, ub]];
a4Idx = Flatten@Position[MapThread[#1 == "branch" && #2 == "A4" &, {kinds, stages}], True];
b4Idx = Flatten@Position[MapThread[#1 == "branch" && #2 == "B4" &, {kinds, stages}], True];
vInputA4toUA = If[Length[a4Idx] > 0,
  Table[Total[Table[lmat[[ua, j]] di[[q, j]], {j, a4Idx}]], {q, Length[tss]}],
  ConstantArray[0., Length[tss]]
];
vOutputUBtoB4 = If[Length[b4Idx] > 0, Total[lmat[[b4Idx, ub]]] di[[All, ub]], ConstantArray[0., Length[tss]]];
pUAtoUB = vUBfromUA*iss[[All, ub]];
pUBtoUA = vUAfromUB*iss[[All, ua]];
pNetUAtoUB = pUAtoUB - pUBtoUA;
maskIdx = Flatten@Position[Map[# >= Last[tss] - 8/maxHz &, tss], True];
tRelUs = (tss[[maskIdx]] - First[tss[[maskIdx]]])*10^6;
metglasWaveformHead = {"time_s","time_us_relative","I_U_A_A","I_U_B_A","V_cap_U_A_V","V_cap_U_B_V",
  "V_direct_U_B_from_U_A_V","V_direct_U_A_from_U_B_V","V_input_A4_to_U_A_V","V_output_U_B_to_B4_V",
  "P_inst_U_A_to_U_B_W","P_inst_U_B_to_U_A_W","P_inst_net_U_A_to_U_B_W"};
metglasWaveformRows = Transpose[{tss[[maskIdx]], tRelUs, iss[[maskIdx, ua]], iss[[maskIdx, ub]],
  vcss[[maskIdx, ua]], vcss[[maskIdx, ub]], vUBfromUA[[maskIdx]], vUAfromUB[[maskIdx]],
  vInputA4toUA[[maskIdx]], vOutputUBtoB4[[maskIdx]], pUAtoUB[[maskIdx]], pUBtoUA[[maskIdx]], pNetUAtoUB[[maskIdx]]}];
Export[FileNameJoin[{outDir, "mathematica_metglas_dynamic_waveforms.csv"}], Prepend[metglasWaveformRows, metglasWaveformHead]];

rmsWin[x_] := Sqrt[Mean[x[[maskIdx]]^2]];
bUA = lvals[[ua]] iss[[All, ua]]/Max[turns[[ua]]*23.0*10^-4, $MinMachineNumber];
bUB = lvals[[ub]] iss[[All, ub]]/Max[turns[[ub]]*23.0*10^-4, $MinMachineNumber];
metglasSummaryRows = {
  {"U_A_core_current", maxHz, rmsWin[iss[[All, ua]]], Max[Abs[iss[[maskIdx, ua]]]], "A", "Simulated U_A Metglas resonant-mode current."},
  {"U_B_core_current", maxHz, rmsWin[iss[[All, ub]]], Max[Abs[iss[[maskIdx, ub]]]], "A", "Simulated U_B Metglas resonant-mode current."},
  {"U_A_capacitor_voltage", maxHz, rmsWin[vcss[[All, ua]]], Max[Abs[vcss[[maskIdx, ua]]]], "V", "Modal resonant capacitor voltage in the U_A tank."},
  {"U_B_capacitor_voltage", maxHz, rmsWin[vcss[[All, ub]]], Max[Abs[vcss[[maskIdx, ub]]]], "V", "Modal resonant capacitor voltage in the U_B tank."},
  {"U_A_flux_density", maxHz, rmsWin[bUA], Max[Abs[bUA[[maskIdx]]]], "T", "B=L*I/(N*Ae), Ae=23.0 cm^2."},
  {"U_B_flux_density", maxHz, rmsWin[bUB], Max[Abs[bUB[[maskIdx]]]], "T", "B=L*I/(N*Ae), Ae=23.0 cm^2."},
  {"direct_U_A_to_U_B_mutual_voltage", maxHz, rmsWin[vUBfromUA], Max[Abs[vUBfromUA[[maskIdx]]]], "V", "v_UB<-UA = M_UAUB*dI_UA/dt."},
  {"input_A4_to_U_A_mutual_voltage", maxHz, rmsWin[vInputA4toUA], Max[Abs[vInputA4toUA[[maskIdx]]]], "V", "Summed A4 branch mutual voltage into U_A."},
  {"output_U_B_to_B4_mutual_voltage", maxHz, rmsWin[vOutputUBtoB4], Max[Abs[vOutputUBtoB4[[maskIdx]]]], "V", "Summed induced voltage from U_B into the B4 branch set."},
  {"actual_average_U_A_to_U_B_power", maxHz, Mean[pUAtoUB[[maskIdx]]], Max[Abs[pUAtoUB[[maskIdx]]]], "W", "Average of v_UB<-UA(t)*i_UB(t)."},
  {"actual_average_net_U_A_to_U_B_power", maxHz, Mean[pNetUAtoUB[[maskIdx]]], Max[Abs[pNetUAtoUB[[maskIdx]]]], "W", "Average of p_UA->UB - p_UB->UA."},
  {"matched_thevenin_U_A_to_U_B_limit", maxHz, Pdyn, Ptgt, "W", "Dynamic-current limit in rms_value; 50 mT target-current limit in peak_value."}
};
Export[FileNameJoin[{outDir, "mathematica_metglas_signal_summary.csv"}],
  Prepend[metglasSummaryRows, {"metric","frequency_Hz","rms_value","peak_value","unit","note"}]];

Export[FileNameJoin[{figDir, "mathematica_metglas_core_currents.png"}],
  ListLinePlot[{Transpose[{tRelUs, iss[[maskIdx, ua]]}], Transpose[{tRelUs, iss[[maskIdx, ub]]}]},
    PlotLegends -> {"U_A current","U_B current"}, Frame -> True, ImageSize -> 1100,
    FrameLabel -> {"time (us)","current (A)"}, PlotLabel -> "Mathematica Metglas AMCC-1000 core currents"]];
Export[FileNameJoin[{figDir, "mathematica_metglas_core_voltages.png"}],
  ListLinePlot[{Transpose[{tRelUs, vcss[[maskIdx, ua]]}], Transpose[{tRelUs, vcss[[maskIdx, ub]]}], Transpose[{tRelUs, vUBfromUA[[maskIdx]]}]},
    PlotLegends -> {"U_A tank","U_B tank","U_B from U_A"}, Frame -> True, ImageSize -> 1100,
    FrameLabel -> {"time (us)","voltage (V)"}, PlotLabel -> "Mathematica Metglas tank and mutual voltages"]];
Export[FileNameJoin[{figDir, "mathematica_metglas_input_output_signals.png"}],
  ListLinePlot[{Transpose[{tRelUs, vInputA4toUA[[maskIdx]]}], Transpose[{tRelUs, vOutputUBtoB4[[maskIdx]]}], Transpose[{tRelUs, vUBfromUA[[maskIdx]]}]},
    PlotLegends -> {"input A4 -> U_A","output U_B -> B4","direct U_A -> U_B"}, Frame -> True, ImageSize -> 1100,
    FrameLabel -> {"time (us)","voltage (V)"}, PlotLabel -> "Mathematica Metglas input/output induced-voltage monitor signals"]];
Export[FileNameJoin[{figDir, "mathematica_metglas_transferred_power_time.png"}],
  ListLinePlot[{Transpose[{tRelUs, pUAtoUB[[maskIdx]]}], Transpose[{tRelUs, pUBtoUA[[maskIdx]]}], Transpose[{tRelUs, pNetUAtoUB[[maskIdx]]}]},
    PlotLegends -> {"U_A -> U_B","U_B -> U_A","net U_A -> U_B"}, Frame -> True, ImageSize -> 1100,
    FrameLabel -> {"time (us)","power (W)"}, PlotLabel -> "Mathematica Metglas instantaneous mutual power exchange"]];

Export[FileNameJoin[{figDir, "mathematica_stage_real_power.png"}],
  BarChart[stageRows[[All, {6,9,10}]], ChartLegends -> {"P source W","P damping W","P copper W"},
    ChartLabels -> stageOrder, ImageSize -> 1100, PlotLabel -> "Mathematica RMS real power by stage"]];
Export[FileNameJoin[{figDir, "mathematica_stage_reactive_power.png"}],
  BarChart[stageRows[[All, {11,12,13}]]/1000, ChartLegends -> {"Q L kVAR","Q C kVAR","Q net kVAR"},
    ChartLabels -> stageOrder, ImageSize -> 1100, PlotLabel -> "Mathematica reactive power by stage"]];

Print["Mathematica dynamic power simulation complete. Pmax dynamic U_A->U_B = ", Pdyn, " W; target 50 mT = ", Ptgt, " W."];
