% Versioned MATLAB runner for the 2026-05-31 updated-coil design.
%
% The canonical MATLAB simulator already reads the current Grover-solved coil
% tables and writes the Metglas plots:
%   - core currents
%   - tank and mutual voltages
%   - input/output induced signals
%   - instantaneous transferred power
%
% This wrapper keeps the original MATLAB simulator intact, then copies its
% outputs into versioned folders so the new results do not overwrite earlier
% runs.

clear; clc;

scriptDir = fileparts(mfilename('fullpath'));
rootDir = fileparts(scriptDir);
versionTag = 'updated_coils_20260531';

run(fullfile(scriptDir, 'dynamic_power_simulator.m'));

srcOut = fullfile(rootDir, 'outputs_matlab');
srcFig = fullfile(rootDir, 'figures_matlab');
dstOut = fullfile(rootDir, ['outputs_matlab_' versionTag]);
dstFig = fullfile(rootDir, ['figures_matlab_' versionTag]);

if exist(dstOut, 'dir'), rmdir(dstOut, 's'); end
if exist(dstFig, 'dir'), rmdir(dstFig, 's'); end
copyfile(srcOut, dstOut);
copyfile(srcFig, dstFig);

fprintf('Versioned MATLAB updated-coil outputs copied to %s\n', dstOut);
fprintf('Versioned MATLAB updated-coil figures copied to %s\n', dstFig);
