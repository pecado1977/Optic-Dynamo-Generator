% Dynamic RMS/W/VAR simulator for walter_russell_optical_dynamo_generator.
% This MATLAB version mirrors the Python model:
% L_matrix*dI/dt = Vsource(t) - R*I - Vc, dVc/dt = C^-1*I.
% It reads the current CSV design files and writes RMS, W, VA, VAR and
% Metglas transfer-power estimates.

clear; clc;

scriptDir = fileparts(mfilename('fullpath'));
rootDir = fileparts(scriptDir);
repoRoot = fileparts(rootDir);
inputDir = fullfile(repoRoot, 'walter_russell_optical_dynamo_generator', 'outputs');
outDir = fullfile(rootDir, 'outputs_matlab');
figDir = fullfile(rootDir, 'figures_matlab');
if ~exist(outDir, 'dir'), mkdir(outDir); end
if ~exist(figDir, 'dir'), mkdir(figDir); end

powerW = 10000.0;
zStage = 50.0;
baseHz = 16000.0;
maxHz = 128000.0;
loadedQ = 20.0;
coreLoadedQ = 12.0;
stepsPer128k = 64;
cyclesAt16k = 72;
sampleStride = 4;
rampCyclesAt16k = 8;

stageOrder = ["A1","A2","A3","A4","B4","B3","B2","B1"];
stagePosition = containers.Map( ...
    {'A1','A2','A3','A4','B4','B3','B2','B1'}, ...
    {-3.5,-2.5,-1.5,-0.5,0.5,1.5,2.5,3.5});
mirror = containers.Map( ...
    {'A1','A2','A3','A4','B4','B3','B2','B1'}, ...
    {'B1','B2','B3','B4','A4','A3','A2','A1'});

branch = readtable(fullfile(inputDir, 'branch_lc_tuning_plan.csv'), 'TextType', 'string');
core = readtable(fullfile(inputDir, 'paraformer_u_core_geometry.csv'), 'TextType', 'string');
amcc = readtable(fullfile(inputDir, 'amcc1000_128k_sweep.csv'), 'TextType', 'string');

names = strings(0,1); kinds = strings(0,1); stages = strings(0,1); cables = strings(0,1);
f = []; L = []; C = []; Rcu = []; Rdyn = []; targetI = []; zBranch = []; driveV = []; phase = []; turns = []; Ae = [];
stageI = sqrt(powerW / zStage);

for r = 1:height(branch)
    st = branch.stage(r);
    cab = branch.cable(r);
    fhz = branch.frequency_Hz(r);
    activeCount = branch.active_branch_count(r);
    zbr = branch.branch_target_impedance_ohm(r);
    Lh = branch.branch_target_L_uH(r) * 1e-6;
    Cf = branch.branch_target_C_nF(r) * 1e-9;
    R = branch.Rac_60C_ohm(r);
    Rload = max(zbr / loadedQ, 5.0 * R);
    Itarget = stageI / activeCount;
    Vdrive = sqrt(2) * Itarget * Rload;
    names(end+1,1) = st + "_" + cab;
    kinds(end+1,1) = "branch";
    stages(end+1,1) = st;
    cables(end+1,1) = cab;
    f(end+1,1) = fhz;
    L(end+1,1) = Lh;
    C(end+1,1) = Cf;
    Rcu(end+1,1) = R;
    Rdyn(end+1,1) = Rload;
    targetI(end+1,1) = Itarget;
    zBranch(end+1,1) = zbr;
    driveV(end+1,1) = Vdrive;
    phase(end+1,1) = stagePhase(st, fhz, baseHz, stagePosition);
    turns(end+1,1) = 0;
    Ae(end+1,1) = 0;
end

coreRow = amcc(abs(amcc.gap_mm - 2.0) < 1e-9 & abs(amcc.B_limit_T - 0.05) < 1e-9, :);
if height(coreRow) == 0, coreRow = amcc(1,:); end
for r = 1:height(core)
    part = core.part(r);
    fhz = maxHz;
    Lh = core.L_self_mH(r) * 1e-3;
    Cf = 1 / ((2*pi*fhz)^2 * Lh);
    xL = 2*pi*fhz*Lh;
    names(end+1,1) = part;
    kinds(end+1,1) = "core";
    stages(end+1,1) = part;
    cables(end+1,1) = "E1";
    f(end+1,1) = fhz;
    L(end+1,1) = Lh;
    C(end+1,1) = Cf;
    Rcu(end+1,1) = 0;
    Rdyn(end+1,1) = xL / coreLoadedQ;
    targetI(end+1,1) = coreRow.Irms_magnetizing_at_B_limit(1);
    zBranch(end+1,1) = xL;
    driveV(end+1,1) = 0;
    phase(end+1,1) = double(part == "U_B") * pi/2;
    turns(end+1,1) = core.turns_reference(r);
    Ae(end+1,1) = 23.0e-4;
end

n = numel(names);
Lmat = diag(L);
couplingRows = table(strings(0,1), strings(0,1), [], [], strings(0,1), ...
    'VariableNames', {'from','to','k','M_uH','type'});

for ci = unique(cables(kinds == "branch"))'
    idx = find(kinds == "branch" & cables == ci);
    [~, orderIdx] = sort(arrayfun(@(x) find(stageOrder == stages(x), 1), idx));
    idx = idx(orderIdx);
    for p = 1:numel(idx)-1
        [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, idx(p), idx(p+1), 0.008, "same cable adjacent stage");
    end
end

for st = stageOrder
    idx = find(kinds == "branch" & stages == st);
    for a = 1:numel(idx)
        for b = a+1:numel(idx)
            [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, idx(a), idx(b), 0.0025, "co-located stage");
        end
    end
end

for st = ["A1","A2","A3","A4"]
    other = string(mirror(char(st)));
    cabs = unique(cables(kinds == "branch" & stages == st));
    for ci = cabs'
        a = find(stages == st & cables == ci, 1);
        b = find(stages == other & cables == ci, 1);
        if ~isempty(a) && ~isempty(b)
            kval = 0.004;
            if st == "A4", kval = 0.020; end
            [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, a, b, kval, "mirror or center pair");
        end
    end
end

ua = find(names == "U_A", 1);
ub = find(names == "U_B", 1);
for cidx = find(stages == "A4")'
    [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, ua, cidx, 0.012, "U_A to A4");
end
for cidx = find(stages == "B4")'
    [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, ub, cidx, 0.012, "U_B to B4");
end
[Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, ua, ub, 0.080, "orthogonal U_A/U_B core");

dt = 1 / (maxHz * stepsPer128k);
duration = cyclesAt16k / baseHz;
rampS = rampCyclesAt16k / baseHz;
steps = ceil(duration / dt);
y = zeros(2*n, 1);
Rvec = Rdyn;
Cinv = 1 ./ C;
Linv = inv(Lmat);
ts = []; isamp = []; vcsamp = [];

for step = 0:steps
    t = step * dt;
    if mod(step, sampleStride) == 0
        ts(end+1,1) = t;
        isamp(end+1,:) = y(1:n).';
        vcsamp(end+1,:) = y(n+1:end).';
    end
    k1 = rhs(t, y);
    k2 = rhs(t + dt/2, y + dt*k1/2);
    k3 = rhs(t + dt/2, y + dt*k2/2);
    k4 = rhs(t + dt, y + dt*k3);
    y = y + dt/6 * (k1 + 2*k2 + 2*k3 + k4);
end

ss = floor(numel(ts)/2):numel(ts);
tss = ts(ss);
iss = isamp(ss,:);
vcss = vcsamp(ss,:);

modeRows = table();
Iph = zeros(n,1);
VsrcPh = zeros(n,1);
for i = 1:n
    I = phasorRms(tss, iss(:,i), f(i));
    Vc = phasorRms(tss, vcss(:,i), f(i));
    Vs = phasorRms(tss, arrayfun(@(tt) sourceOne(tt, i, 0), tss), f(i));
    Iph(i) = I;
    VsrcPh(i) = Vs;
    w = 2*pi*f(i);
    XL = w*L(i);
    XC = 1/(w*C(i));
    S = Vs * conj(I);
    modeRows(i,:) = table(names(i), kinds(i), stages(i), cables(i), f(i), abs(I), abs(Vs), abs(Vc), abs(I)*XL, ...
        real(S), imag(S), abs(S), abs(I)^2*Rdyn(i), abs(I)^2*Rcu(i), abs(I)^2*XL, -abs(I)^2*XC, ...
        'VariableNames', {'mode','kind','stage','cable','frequency_Hz','I_rms_A','V_source_rms_V','V_capacitor_rms_V','V_inductor_rms_V','P_source_W','Q_source_VAR','S_source_VA','P_dynamic_damping_W','P_copper_W','Q_inductor_VAR','Q_capacitor_VAR'});
end
writetable(modeRows, fullfile(outDir, 'matlab_mode_rms_power_reactive_summary.csv'));

stageRows = table();
for si = 1:numel(stageOrder)
    st = stageOrder(si);
    idx = find(kinds == "branch" & stages == st);
    p = sum(modeRows.P_source_W(idx));
    q = sum(modeRows.Q_source_VAR(idx));
    s = hypot(p,q);
    vbus = sqrt(powerW*zStage);
    stageRows(si,:) = table(st, f(idx(1)), numel(idx), vbus, s/vbus, p, q, s, ...
        sum(modeRows.P_dynamic_damping_W(idx)), sum(modeRows.P_copper_W(idx)), ...
        sum(modeRows.Q_inductor_VAR(idx)), sum(modeRows.Q_capacitor_VAR(idx)), ...
        'VariableNames', {'stage','frequency_Hz','active_branch_count','bus_V_rms_50ohm_V','stage_I_rms_from_source_power_A','P_source_W','Q_source_VAR','S_source_VA','P_dynamic_damping_W','P_copper_W','Q_inductor_VAR_sum','Q_capacitor_VAR_sum'});
end
stageRows.Q_lc_net_VAR = stageRows.Q_inductor_VAR_sum + stageRows.Q_capacitor_VAR_sum;
writetable(stageRows, fullfile(outDir, 'matlab_stage_rms_watts_amps_volts_summary.csv'));

M = Lmat(ua,ub);
w = 2*pi*maxHz;
Pdyn = (w*abs(M)*abs(Iph(ua)))^2/(4*Rdyn(ub));
Ptgt = (w*abs(M)*targetI(ua))^2/(4*Rdyn(ub));
transfer = table(0.08, M*1e6, abs(Iph(ua)), targetI(ua), Pdyn, Ptgt, ...
    'VariableNames', {'k','M_uH','dynamic_UA_I_rms_A','target_50mT_I_rms_A','Pmax_dynamic_W','Pmax_target_50mT_W'});
writetable(transfer, fullfile(outDir, 'matlab_metglas_transformer_transfer_limit.csv'));

targetP = 10000.0;
kOrtho = 0.08;
bRef = 0.05;
vRef = 523.1938947975291;
nRef = turns(ua);
lRef = L(ua);
rRef = Rdyn(ua);
iRef = targetI(ua);
targetMaxI = 60.0;
jTarget = 3.0;
mtl = 0.85;
reserve = 0.15;
awg10Area = 5.261154954510373;
bRequired = bRef * sqrt(targetP / Ptgt);
nSelected = ceil(nRef * iRef * (bRequired/bRef) / targetMaxI);
iPrimary = iRef * (bRequired/bRef) * (nRef/nSelected);
vPrimary = vRef * (bRequired/bRef) * (nSelected/nRef);
lSelected = lRef * (nSelected/nRef)^2;
rSelected = rRef * (nSelected/nRef)^2;
xSelected = 2*pi*maxHz*lSelected;
cSelected = 1 / ((2*pi*maxHz)^2*lSelected);
mSelected = kOrtho*lSelected;
vSecondary = 2*pi*maxHz*mSelected*iPrimary;
pmaxSelected = vSecondary^2/(4*rSelected);
areaNeeded = iPrimary/jTarget;
parallelBundles = ceil(areaNeeded/awg10Area);
copperArea = parallelBundles*awg10Area;
cablePerParallel = nSelected*mtl;
cablePerWindingBuy = cablePerParallel*parallelBundles*(1+reserve);
orthoPlan = table(targetP, kOrtho, bRequired, nSelected, iPrimary, vPrimary, vSecondary, rSelected, pmaxSelected, ...
    lSelected*1e3, mSelected*1e6, xSelected, cSelected*1e9, iPrimary^2*xSelected, parallelBundles, copperArea, ...
    iPrimary/copperArea, cablePerParallel, cablePerWindingBuy, 2*cablePerWindingBuy, ...
    'VariableNames', {'target_power_W','assumed_k','required_B_peak_T','selected_turns_per_winding','primary_winding_I_rms_A','primary_winding_V_rms_V','secondary_open_circuit_V_rms','secondary_matched_load_R_ohm','Pmax_matched_secondary_W','L_self_mH','M_mutual_uH','X_L_ohm','C_resonance_nF','Q_inductor_VAR','selected_parallel_AWG10_equiv_Litz_bundles','selected_copper_area_mm2','actual_current_density_A_per_mm2','active_cable_per_parallel_bundle_m','procurement_cable_per_winding_m','procurement_cable_two_windings_m'});
writetable(orthoPlan, fullfile(outDir, 'matlab_orthogonal_paraformer_10kw_cable_plan.csv'));

di = zeros(size(iss));
for col = 1:n
    di(:,col) = gradient(iss(:,col), tss);
end
mUAUB = Lmat(ua,ub);
vUBfromUA = mUAUB * di(:,ua);
vUAfromUB = mUAUB * di(:,ub);
a4idx = find(kinds == "branch" & stages == "A4");
b4idx = find(kinds == "branch" & stages == "B4");
if ~isempty(a4idx)
    vInputA4toUA = sum(di(:,a4idx) .* Lmat(ua,a4idx), 2);
else
    vInputA4toUA = zeros(size(tss));
end
if ~isempty(b4idx)
    vOutputUBtoB4 = sum(Lmat(b4idx,ub)) * di(:,ub);
else
    vOutputUBtoB4 = zeros(size(tss));
end
pUAtoUB = vUBfromUA .* iss(:,ub);
pUBtoUA = vUAfromUB .* iss(:,ua);
pNetUAtoUB = pUAtoUB - pUBtoUA;
mask = tss >= (tss(end) - 8/maxHz);
firstMask = find(mask, 1, 'first');
tRelUs = (tss(mask) - tss(firstMask)) * 1e6;
metglasWaveforms = table(tss(mask), tRelUs, iss(mask,ua), iss(mask,ub), vcss(mask,ua), vcss(mask,ub), ...
    vUBfromUA(mask), vUAfromUB(mask), vInputA4toUA(mask), vOutputUBtoB4(mask), ...
    pUAtoUB(mask), pUBtoUA(mask), pNetUAtoUB(mask), ...
    'VariableNames', {'time_s','time_us_relative','I_U_A_A','I_U_B_A','V_cap_U_A_V','V_cap_U_B_V', ...
    'V_direct_U_B_from_U_A_V','V_direct_U_A_from_U_B_V','V_input_A4_to_U_A_V','V_output_U_B_to_B4_V', ...
    'P_inst_U_A_to_U_B_W','P_inst_U_B_to_U_A_W','P_inst_net_U_A_to_U_B_W'});
writetable(metglasWaveforms, fullfile(outDir, 'matlab_metglas_dynamic_waveforms.csv'));

rmswin = @(x) sqrt(mean(x(mask).^2));
bUA = L(ua) * iss(:,ua) / max(turns(ua) * 23.0e-4, realmin);
bUB = L(ub) * iss(:,ub) / max(turns(ub) * 23.0e-4, realmin);
metglasMetrics = ["U_A_core_current"; "U_B_core_current"; "U_A_capacitor_voltage"; "U_B_capacitor_voltage"; ...
    "U_A_flux_density"; "U_B_flux_density"; "direct_U_A_to_U_B_mutual_voltage"; ...
    "input_A4_to_U_A_mutual_voltage"; "output_U_B_to_B4_mutual_voltage"; ...
    "actual_average_U_A_to_U_B_power"; "actual_average_net_U_A_to_U_B_power"; ...
    "matched_thevenin_U_A_to_U_B_limit"];
metglasFrequency = repmat(maxHz, numel(metglasMetrics), 1);
metglasRms = [rmswin(iss(:,ua)); rmswin(iss(:,ub)); rmswin(vcss(:,ua)); rmswin(vcss(:,ub)); ...
    rmswin(bUA); rmswin(bUB); rmswin(vUBfromUA); rmswin(vInputA4toUA); rmswin(vOutputUBtoB4); ...
    mean(pUAtoUB(mask)); mean(pNetUAtoUB(mask)); Pdyn];
metglasPeak = [max(abs(iss(mask,ua))); max(abs(iss(mask,ub))); max(abs(vcss(mask,ua))); max(abs(vcss(mask,ub))); ...
    max(abs(bUA(mask))); max(abs(bUB(mask))); max(abs(vUBfromUA(mask))); max(abs(vInputA4toUA(mask))); ...
    max(abs(vOutputUBtoB4(mask))); max(abs(pUAtoUB(mask))); max(abs(pNetUAtoUB(mask))); Ptgt];
metglasUnit = ["A"; "A"; "V"; "V"; "T"; "T"; "V"; "V"; "V"; "W"; "W"; "W"];
metglasNote = ["Simulated U_A Metglas resonant-mode current."; "Simulated U_B Metglas resonant-mode current."; ...
    "Modal resonant capacitor voltage in the U_A tank."; "Modal resonant capacitor voltage in the U_B tank."; ...
    "B=L*I/(N*Ae), Ae=23.0 cm^2."; "B=L*I/(N*Ae), Ae=23.0 cm^2."; ...
    "v_UB<-UA = M_UAUB*dI_UA/dt."; "Summed A4 branch mutual voltage into U_A."; ...
    "Summed induced voltage from U_B into the B4 branch set."; ...
    "Average of v_UB<-UA(t)*i_UB(t)."; "Average of p_UA->UB - p_UB->UA."; ...
    "Dynamic-current limit in rms_value; 50 mT target-current limit in peak_value."];
metglasSummary = table(metglasMetrics, metglasFrequency, metglasRms, metglasPeak, metglasUnit, metglasNote, ...
    'VariableNames', {'metric','frequency_Hz','rms_value','peak_value','unit','note'});
writetable(metglasSummary, fullfile(outDir, 'matlab_metglas_signal_summary.csv'));

figure('Visible','off'); plot(tRelUs, iss(mask,ua), 'LineWidth', 1.5); hold on; plot(tRelUs, iss(mask,ub), 'LineWidth', 1.5); grid on;
xlabel('time (\mus)'); ylabel('current (A)'); title('MATLAB Metglas AMCC-1000 core currents'); legend('U_A current','U_B current');
saveas(gcf, fullfile(figDir, 'matlab_metglas_core_currents.png'));

figure('Visible','off'); plot(tRelUs, vcss(mask,ua), 'LineWidth', 1.5); hold on; plot(tRelUs, vcss(mask,ub), 'LineWidth', 1.5); plot(tRelUs, vUBfromUA(mask), 'LineWidth', 1.5); grid on;
xlabel('time (\mus)'); ylabel('voltage (V)'); title('MATLAB Metglas tank and mutual voltages'); legend('U_A tank','U_B tank','U_B from U_A');
saveas(gcf, fullfile(figDir, 'matlab_metglas_core_voltages.png'));

figure('Visible','off'); plot(tRelUs, vInputA4toUA(mask), 'LineWidth', 1.5); hold on; plot(tRelUs, vOutputUBtoB4(mask), 'LineWidth', 1.5); plot(tRelUs, vUBfromUA(mask), 'LineWidth', 1.5); grid on;
xlabel('time (\mus)'); ylabel('voltage (V)'); title('MATLAB Metglas input/output induced-voltage monitor signals'); legend('input A4 -> U_A','output U_B -> B4','direct U_A -> U_B');
saveas(gcf, fullfile(figDir, 'matlab_metglas_input_output_signals.png'));

figure('Visible','off'); plot(tRelUs, pUAtoUB(mask), 'LineWidth', 1.5); hold on; plot(tRelUs, pUBtoUA(mask), 'LineWidth', 1.5); plot(tRelUs, pNetUAtoUB(mask), 'LineWidth', 1.5); grid on;
xlabel('time (\mus)'); ylabel('power (W)'); title('MATLAB Metglas instantaneous mutual power exchange'); legend('U_A -> U_B','U_B -> U_A','net U_A -> U_B');
saveas(gcf, fullfile(figDir, 'matlab_metglas_transferred_power_time.png'));

figure('Visible','off'); bar(categorical(stageRows.stage), [stageRows.P_source_W stageRows.P_dynamic_damping_W stageRows.P_copper_W]); grid on;
legend('P source W','P damping W','P copper W'); title('MATLAB RMS real power by stage');
saveas(gcf, fullfile(figDir, 'matlab_stage_real_power.png'));

figure('Visible','off'); bar(categorical(stageRows.stage), [stageRows.Q_inductor_VAR_sum/1000 stageRows.Q_capacitor_VAR_sum/1000 stageRows.Q_lc_net_VAR/1000]); grid on;
legend('Q L kVAR','Q C kVAR','Q net kVAR'); title('MATLAB reactive power by stage');
saveas(gcf, fullfile(figDir, 'matlab_stage_reactive_power.png'));

fprintf('MATLAB dynamic power simulation complete. Pmax dynamic U_A->U_B = %.6g W, target 50 mT = %.6g W\n', Pdyn, Ptgt);

function p = stagePhase(stage, fhz, baseHz, stagePosition)
    xs = cell2mat(values(stagePosition));
    xnorm = (stagePosition(char(stage)) - min(xs)) / (max(xs) - min(xs));
    mode = max(1, round(fhz/baseHz));
    p = mode*pi*xnorm;
end

function dy = rhs(t, y)
    nloc = evalin('base', 'n');
    LinvLoc = evalin('base', 'Linv');
    Rloc = evalin('base', 'Rvec');
    CinvLoc = evalin('base', 'Cinv');
    i = y(1:nloc);
    vc = y(nloc+1:end);
    v = arrayfun(@(idx) sourceOne(t, idx, evalin('base','rampS')), (1:nloc).');
    di = LinvLoc * (v - Rloc.*i - vc);
    dvc = CinvLoc .* i;
    dy = [di; dvc];
end

function v = sourceOne(t, idx, rampS)
    driveV = evalin('base','driveV');
    f = evalin('base','f');
    phase = evalin('base','phase');
    if rampS <= 0
        ramp = 1;
    else
        ramp = min(1, t/rampS);
        if ramp < 1, ramp = 0.5 - 0.5*cos(pi*ramp); end
    end
    v = ramp * driveV(idx) * sin(2*pi*f(idx)*t + phase(idx));
end

function ph = phasorRms(t, x, fhz)
    ph = 2/numel(t) * sum(x .* exp(-1i*2*pi*fhz*t)) / sqrt(2);
end

function [Lmat, couplingRows] = addCoupling(Lmat, couplingRows, L, names, i, j, k, typ)
    if i == j || k == 0
        return;
    end
    M = k * sqrt(L(i) * L(j));
    Lmat(i,j) = Lmat(i,j) + M;
    Lmat(j,i) = Lmat(j,i) + M;
    couplingRows(end+1,:) = {names(i), names(j), k, M*1e6, string(typ)};
end
