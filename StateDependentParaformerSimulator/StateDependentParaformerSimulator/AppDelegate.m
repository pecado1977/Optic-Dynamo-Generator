#import "AppDelegate.h"
#import "SimulationView.h"
#import "PlotView.h"
#import <QuartzCore/QuartzCore.h>

static NSString * const kFrequencyHz = @"frequencyHz";
static NSString * const kCouplingK = @"couplingK";
static NSString * const kDriveVRMS = @"driveVRMS";
static NSString * const kInductanceUH = @"inductanceUH";
static NSString * const kCapacitanceNF = @"capacitanceNF";
static NSString * const kResistanceOhm = @"resistanceOhm";
static NSString * const kLoadOhm = @"loadOhm";
static NSString * const kTemperatureC = @"temperatureC";
static NSString * const kTurns = @"turns";
static NSString * const kGapMM = @"gapMM";
static NSString * const kMuScale = @"muScale";
static NSString * const kBSatT = @"bSatT";
static NSString * const kCapNonlinear = @"capNonlinear";
static NSString * const kResAlpha = @"resAlpha";
static NSString * const kPhaseOffset = @"phaseOffset";

@interface AppDelegate ()
@property (nonatomic) NSWindow *window;
@property (nonatomic) SimulationView *simulationView;
@property (nonatomic) NSView *controlContent;
@property (nonatomic) NSMutableDictionary<NSString *, NSNumber *> *params;
@property (nonatomic) NSMutableDictionary<NSString *, NSTextField *> *valueFields;
@property (nonatomic) NSMutableDictionary<NSString *, NSSlider *> *sliders;
@property (nonatomic) NSArray<PlotView *> *plots;
@property (nonatomic) PlotView *voltagePlot;
@property (nonatomic) PlotView *currentPlot;
@property (nonatomic) PlotView *resistancePlot;
@property (nonatomic) PlotView *powerPlot;
@property (nonatomic) NSTimer *timer;
@property (nonatomic) NSTimeInterval lastTick;
@property (nonatomic) double modelTime;
@property (nonatomic) BOOL running;
@property (nonatomic) NSString *activePresetName;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.params = [NSMutableDictionary dictionary];
    self.valueFields = [NSMutableDictionary dictionary];
    self.sliders = [NSMutableDictionary dictionary];
    self.running = YES;
    self.activePresetName = @"WR AMCC-1000 center";

    [self applyWRDefaultsWithoutRefreshingControls];
    [self buildWindow];
    [self refreshControlsFromParams];
    [self updateSimulationWithDelta:0.0];

    self.lastTick = CACurrentMediaTime();
    self.timer = [NSTimer scheduledTimerWithTimeInterval:1.0 / 60.0
                                                  target:self
                                                selector:@selector(tick:)
                                                userInfo:nil
                                                 repeats:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (void)buildWindow {
    NSRect frame = NSMakeRect(100, 80, 1500, 980);
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable)
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    self.window.title = @"Walter Russell Optical Dynamo - State-Dependent Paraformer Simulator";
    self.window.minSize = NSMakeSize(1180, 780);

    NSView *root = [[NSView alloc] initWithFrame:self.window.contentView.bounds];
    root.wantsLayer = YES;
    root.layer.backgroundColor = [[NSColor colorWithCalibratedRed:0.018 green:0.027 blue:0.040 alpha:1.0] CGColor];
    root.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.window.contentView = root;

    CGFloat controlsWidth = 420.0;
    NSRect simFrame = NSMakeRect(0, 0, root.bounds.size.width - controlsWidth, root.bounds.size.height);
    self.simulationView = [[SimulationView alloc] initWithFrame:simFrame];
    self.simulationView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    [root addSubview:self.simulationView];

    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(root.bounds.size.width - controlsWidth, 0, controlsWidth, root.bounds.size.height)];
    scroll.autoresizingMask = NSViewMinXMargin | NSViewHeightSizable;
    scroll.hasVerticalScroller = YES;
    scroll.borderType = NSNoBorder;
    scroll.drawsBackground = NO;
    scroll.wantsLayer = YES;
    scroll.layer.backgroundColor = [[NSColor colorWithCalibratedRed:0.025 green:0.037 blue:0.055 alpha:1.0] CGColor];
    [root addSubview:scroll];

    self.controlContent = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, controlsWidth, 1640)];
    self.controlContent.wantsLayer = YES;
    self.controlContent.layer.backgroundColor = [[NSColor colorWithCalibratedRed:0.025 green:0.037 blue:0.055 alpha:1.0] CGColor];
    scroll.documentView = self.controlContent;

    [self buildControlPanel];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)buildControlPanel {
    CGFloat y = self.controlContent.bounds.size.height - 34.0;
    NSDictionary *titleAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:17 weight:NSFontWeightBold],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.94 alpha:0.96]
    };
    NSTextField *title = [self label:@"WR Optical Dynamo Simulator" frame:NSMakeRect(18, y, 370, 24) attributes:titleAttrs];
    [self.controlContent addSubview:title];
    y -= 32.0;

    NSDictionary *smallAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:11 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.68 alpha:0.86]
    };
    NSTextField *source = [self label:@"Defaults: updated C1-C8 ladder + AMCC-1000 run, 2026-05-31" frame:NSMakeRect(18, y, 380, 34) attributes:smallAttrs];
    source.lineBreakMode = NSLineBreakByWordWrapping;
    [self.controlContent addSubview:source];
    y -= 50.0;

    NSSegmentedControl *preset = [[NSSegmentedControl alloc] initWithFrame:NSMakeRect(18, y, 380, 34)];
    preset.segmentCount = 3;
    [preset setLabel:@"Run" forSegment:0];
    [preset setLabel:@"Reset" forSegment:1];
    [preset setLabel:@"10 kW" forSegment:2];
    [preset setTarget:self];
    [preset setAction:@selector(presetSegment:)];
    [self.controlContent addSubview:preset];
    y -= 46.0;

    NSPopUpButton *stagePopup = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(18, y, 380, 28)];
    [stagePopup addItemsWithTitles:@[
        @"WR AMCC-1000 center",
        @"A1/B1 16 kHz branch",
        @"A2/B2 32 kHz branch",
        @"A3/B3 64 kHz branch",
        @"A4/B4 128 kHz branch",
        @"Orthogonal 10 kW paraformer"
    ]];
    [stagePopup setTarget:self];
    [stagePopup setAction:@selector(stagePresetChanged:)];
    [self.controlContent addSubview:stagePopup];
    y -= 48.0;

    self.voltagePlot = [[PlotView alloc] initWithTitle:@"tank voltage" unit:@"V" color:[NSColor colorWithCalibratedRed:0.42 green:0.86 blue:1.0 alpha:1.0]];
    self.currentPlot = [[PlotView alloc] initWithTitle:@"modal current" unit:@"A" color:[NSColor colorWithCalibratedRed:1.0 green:0.67 blue:0.32 alpha:1.0]];
    self.resistancePlot = [[PlotView alloc] initWithTitle:@"dynamic resistance" unit:@"ohm" color:[NSColor colorWithCalibratedRed:0.77 green:0.62 blue:1.0 alpha:1.0]];
    self.powerPlot = [[PlotView alloc] initWithTitle:@"matched transfer" unit:@"W" color:[NSColor colorWithCalibratedRed:0.47 green:1.0 blue:0.66 alpha:1.0]];
    self.plots = @[self.voltagePlot, self.currentPlot, self.resistancePlot, self.powerPlot];
    for (PlotView *plot in self.plots) {
        plot.frame = NSMakeRect(18, y - 112.0, 380, 104);
        [self.controlContent addSubview:plot];
        y -= 118.0;
    }

    y -= 8.0;
    y = [self addSliderWithTitle:@"frequency f0" key:kFrequencyHz min:16000 max:256000 unit:@"Hz" y:y];
    y = [self addSliderWithTitle:@"coupling k" key:kCouplingK min:0.02 max:0.95 unit:@"" y:y];
    y = [self addSliderWithTitle:@"drive voltage" key:kDriveVRMS min:1 max:10000 unit:@"Vrms" y:y];
    y = [self addSliderWithTitle:@"inductance L" key:kInductanceUH min:10 max:1200 unit:@"uH" y:y];
    y = [self addSliderWithTitle:@"capacitance C" key:kCapacitanceNF min:1 max:220 unit:@"nF" y:y];
    y = [self addSliderWithTitle:@"damping R" key:kResistanceOhm min:0.01 max:30 unit:@"ohm" y:y];
    y = [self addSliderWithTitle:@"load R" key:kLoadOhm min:0.1 max:100 unit:@"ohm" y:y];
    y = [self addSliderWithTitle:@"temperature" key:kTemperatureC min:-20 max:180 unit:@"C" y:y];
    y = [self addSliderWithTitle:@"turns N" key:kTurns min:1 max:64 unit:@"" y:y];
    y = [self addSliderWithTitle:@"gap" key:kGapMM min:0.1 max:10 unit:@"mm" y:y];
    y = [self addSliderWithTitle:@"mu scale" key:kMuScale min:0.15 max:2.5 unit:@"" y:y];
    y = [self addSliderWithTitle:@"B saturation" key:kBSatT min:0.05 max:1.8 unit:@"T" y:y];
    y = [self addSliderWithTitle:@"C state term" key:kCapNonlinear min:-1.0 max:1.0 unit:@"" y:y];
    y = [self addSliderWithTitle:@"R temp alpha" key:kResAlpha min:0.0 max:0.01 unit:@"/C" y:y];
    y = [self addSliderWithTitle:@"phase offset" key:kPhaseOffset min:-3.14159 max:3.14159 unit:@"rad" y:y];
}

- (NSTextField *)label:(NSString *)text frame:(NSRect)frame attributes:(NSDictionary *)attributes {
    NSTextField *label = [[NSTextField alloc] initWithFrame:frame];
    label.stringValue = text;
    label.bezeled = NO;
    label.editable = NO;
    label.selectable = NO;
    label.drawsBackground = NO;
    label.attributedStringValue = [[NSAttributedString alloc] initWithString:text attributes:attributes];
    return label;
}

- (CGFloat)addSliderWithTitle:(NSString *)title key:(NSString *)key min:(double)min max:(double)max unit:(NSString *)unit y:(CGFloat)y {
    NSDictionary *labelAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:12 weight:NSFontWeightMedium],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.83 alpha:0.92]
    };
    NSTextField *label = [self label:title frame:NSMakeRect(18, y, 180, 20) attributes:labelAttrs];
    [self.controlContent addSubview:label];

    NSTextField *value = [[NSTextField alloc] initWithFrame:NSMakeRect(228, y - 1, 170, 22)];
    value.bezeled = NO;
    value.editable = NO;
    value.selectable = NO;
    value.alignment = NSTextAlignmentRight;
    value.drawsBackground = NO;
    value.textColor = [NSColor colorWithCalibratedRed:0.70 green:0.91 blue:1.0 alpha:0.96];
    value.font = [NSFont monospacedDigitSystemFontOfSize:12 weight:NSFontWeightSemibold];
    value.identifier = unit;
    [self.controlContent addSubview:value];
    self.valueFields[key] = value;

    NSSlider *slider = [[NSSlider alloc] initWithFrame:NSMakeRect(18, y - 30, 380, 24)];
    slider.minValue = min;
    slider.maxValue = max;
    slider.doubleValue = self.params[key].doubleValue;
    slider.identifier = key;
    slider.target = self;
    slider.action = @selector(sliderChanged:);
    slider.continuous = YES;
    [self.controlContent addSubview:slider];
    self.sliders[key] = slider;

    return y - 66.0;
}

- (void)sliderChanged:(NSSlider *)sender {
    if (!sender.identifier) {
        return;
    }
    self.params[sender.identifier] = @(sender.doubleValue);
    [self refreshValueFieldForKey:sender.identifier];
    [self updateSimulationWithDelta:0.0];
}

- (void)presetSegment:(NSSegmentedControl *)sender {
    NSInteger segment = sender.selectedSegment;
    sender.selectedSegment = -1;
    if (segment == 0) {
        self.running = !self.running;
        self.simulationView.running = self.running;
    } else if (segment == 1) {
        [self applyWRDefaultsWithoutRefreshingControls];
        [self refreshControlsFromParams];
        [self clearPlots];
    } else if (segment == 2) {
        [self apply10kWDefaults];
        [self refreshControlsFromParams];
        [self clearPlots];
    }
}

- (void)stagePresetChanged:(NSPopUpButton *)sender {
    NSString *title = sender.titleOfSelectedItem;
    self.activePresetName = title;
    if ([title hasPrefix:@"A1/B1"]) {
        [self setFrequency:16000.0 L:994.718394 C:99.471839 R:0.165572 drive:100.0 turns:128.599732 load:100.0];
    } else if ([title hasPrefix:@"A2/B2"]) {
        [self setFrequency:32000.0 L:497.359197 C:49.735920 R:0.117238 drive:100.0 turns:91.058737 load:100.0];
    } else if ([title hasPrefix:@"A3/B3"]) {
        [self setFrequency:64000.0 L:497.359197 C:12.433980 R:0.062151 drive:120.0 turns:100.405929 load:200.0];
    } else if ([title hasPrefix:@"A4/B4"]) {
        [self setFrequency:128000.0 L:497.359197 C:3.108495 R:0.052071 drive:160.0 turns:100.405929 load:400.0];
    } else if ([title hasPrefix:@"Orthogonal"]) {
        [self apply10kWDefaults];
    } else {
        [self applyWRDefaultsWithoutRefreshingControls];
    }
    [self refreshControlsFromParams];
    [self clearPlots];
}

- (void)setFrequency:(double)frequency L:(double)L C:(double)C R:(double)R drive:(double)drive turns:(double)turns load:(double)load {
    self.params[kFrequencyHz] = @(frequency);
    self.params[kInductanceUH] = @(L);
    self.params[kCapacitanceNF] = @(C);
    self.params[kResistanceOhm] = @(R);
    self.params[kDriveVRMS] = @(drive);
    self.params[kTurns] = @(turns);
    self.params[kLoadOhm] = @(load);
}

- (void)applyWRDefaultsWithoutRefreshingControls {
    self.params[kFrequencyHz] = @(128000.0);
    self.params[kCouplingK] = @(0.08);
    self.params[kDriveVRMS] = @(183.020191);
    self.params[kInductanceUH] = @(92.051753);
    self.params[kCapacitanceNF] = @(16.795319);
    self.params[kResistanceOhm] = @(6.169368);
    self.params[kLoadOhm] = @(6.169368);
    self.params[kTemperatureC] = @(25.0);
    self.params[kTurns] = @(8.0);
    self.params[kGapMM] = @(2.0);
    self.params[kMuScale] = @(1.0);
    self.params[kBSatT] = @(1.56);
    self.params[kCapNonlinear] = @(0.0);
    self.params[kResAlpha] = @(0.0039);
    self.params[kPhaseOffset] = @(0.0);
}

- (void)apply10kWDefaults {
    self.params[kFrequencyHz] = @(128000.0);
    self.params[kCouplingK] = @(0.08);
    self.params[kDriveVRMS] = @(9314.329475);
    self.params[kInductanceUH] = @(207.116445);
    self.params[kCapacitanceNF] = @(7.464586);
    self.params[kResistanceOhm] = @(13.881077);
    self.params[kLoadOhm] = @(13.881077);
    self.params[kTemperatureC] = @(45.0);
    self.params[kTurns] = @(12.0);
    self.params[kGapMM] = @(2.0);
    self.params[kMuScale] = @(1.0);
    self.params[kBSatT] = @(1.56);
    self.params[kCapNonlinear] = @(0.0);
    self.params[kResAlpha] = @(0.0039);
    self.params[kPhaseOffset] = @(0.0);
}

- (void)refreshControlsFromParams {
    for (NSString *key in self.sliders) {
        self.sliders[key].doubleValue = self.params[key].doubleValue;
        [self refreshValueFieldForKey:key];
    }
    [self updateSimulationWithDelta:0.0];
}

- (void)refreshValueFieldForKey:(NSString *)key {
    NSTextField *field = self.valueFields[key];
    if (!field) {
        return;
    }
    NSString *unit = field.identifier ?: @"";
    double value = self.params[key].doubleValue;
    if ([key isEqualToString:kFrequencyHz]) {
        field.stringValue = [NSString stringWithFormat:@"%.1f kHz", value / 1000.0];
    } else if ([key isEqualToString:kCouplingK] || [key isEqualToString:kMuScale] || [key isEqualToString:kCapNonlinear] || [key isEqualToString:kResAlpha]) {
        field.stringValue = [NSString stringWithFormat:@"%.5f %@", value, unit];
    } else {
        field.stringValue = [NSString stringWithFormat:@"%.3f %@", value, unit];
    }
}

- (void)clearPlots {
    for (PlotView *plot in self.plots) {
        [plot clear];
    }
    self.modelTime = 0.0;
}

- (void)tick:(NSTimer *)timer {
    NSTimeInterval now = CACurrentMediaTime();
    double dt = MAX(0.0, MIN(0.05, now - self.lastTick));
    self.lastTick = now;
    if (self.running) {
        [self updateSimulationWithDelta:dt];
    }
}

- (void)updateSimulationWithDelta:(double)dt {
    self.modelTime += dt;

    double f = self.params[kFrequencyHz].doubleValue;
    double omega = 2.0 * M_PI * f;
    double L0 = self.params[kInductanceUH].doubleValue * 1e-6;
    double C0 = self.params[kCapacitanceNF].doubleValue * 1e-9;
    double R0 = MAX(1e-6, self.params[kResistanceOhm].doubleValue);
    double loadR = MAX(1e-6, self.params[kLoadOhm].doubleValue);
    double temp = self.params[kTemperatureC].doubleValue;
    double turns = MAX(1.0, self.params[kTurns].doubleValue);
    double gap = MAX(0.05, self.params[kGapMM].doubleValue);
    double muScale = self.params[kMuScale].doubleValue;
    double bSat = MAX(0.01, self.params[kBSatT].doubleValue);
    double capNL = self.params[kCapNonlinear].doubleValue;
    double alpha = self.params[kResAlpha].doubleValue;
    double phaseOffset = self.params[kPhaseOffset].doubleValue;
    double drive = self.params[kDriveVRMS].doubleValue;
    double k = self.params[kCouplingK].doubleValue;

    double phase = omega * self.modelTime + phaseOffset;
    double cState = 1.0 + 0.06 * capNL * sin(phase * 0.25);
    double cDyn = MAX(1e-12, C0 * cState);
    double rDyn = MAX(1e-6, R0 * (1.0 + alpha * (temp - 25.0)));
    double gapFactor = 2.0 / gap;
    double thermalMu = MAX(0.1, 1.0 - 0.0012 * (temp - 25.0));
    double lDyn = MAX(1e-9, L0 * muScale * gapFactor * thermalMu);

    for (NSInteger i = 0; i < 3; i++) {
        double xL = omega * lDyn;
        double xC = 1.0 / (omega * cDyn);
        double z = hypot(rDyn, xL - xC);
        double iRMS = drive / MAX(z, 1e-9);
        double iPeak = sqrt(2.0) * iRMS;
        double ae = 0.0023;
        double bPeak = lDyn * iPeak / (turns * ae);
        double satFactor = 1.0 / (1.0 + pow(fabs(bPeak) / bSat, 2.0));
        lDyn = MAX(1e-9, L0 * muScale * gapFactor * thermalMu * satFactor);
    }

    double xL = omega * lDyn;
    double xC = 1.0 / (omega * cDyn);
    double z = hypot(rDyn, xL - xC);
    double iRMS = drive / MAX(z, 1e-9);
    double phi = atan2(xL - xC, rDyn);
    double iInst = sqrt(2.0) * iRMS * sin(phase - phi);
    double vInst = sqrt(2.0) * drive * sin(phase);
    double vCapRMS = iRMS / MAX(omega * cDyn, 1e-12);
    double m = k * lDyn;
    double voc = omega * m * iRMS;
    double pMax = voc * voc / (4.0 * loadR);
    double ae = 0.0023;
    double bPeak = lDyn * sqrt(2.0) * iRMS / (turns * ae);
    double reactive = iRMS * iRMS * xL;

    self.simulationView.time = self.modelTime;
    self.simulationView.phase = phase;
    self.simulationView.running = self.running;
    self.simulationView.frequencyHz = f;
    self.simulationView.couplingK = k;
    self.simulationView.inductanceUH = lDyn * 1e6;
    self.simulationView.capacitanceNF = cDyn * 1e9;
    self.simulationView.resistanceOhm = rDyn;
    self.simulationView.loadOhm = loadR;
    self.simulationView.temperatureC = temp;
    self.simulationView.turns = turns;
    self.simulationView.gapMM = gap;
    self.simulationView.muScale = muScale;
    self.simulationView.bSatT = bSat;
    self.simulationView.driveVRMS = drive;
    self.simulationView.currentARMS = iRMS;
    self.simulationView.voltageVRMS = vCapRMS;
    self.simulationView.mutualUH = m * 1e6;
    self.simulationView.fluxPeakT = bPeak;
    self.simulationView.pMaxW = pMax;
    self.simulationView.zOhm = z;
    self.simulationView.reactiveVAR = reactive;
    self.simulationView.needsDisplay = YES;

    [self.voltagePlot appendValue:vInst];
    [self.currentPlot appendValue:iInst];
    [self.resistancePlot appendValue:rDyn];
    [self.powerPlot appendValue:pMax];
}

@end
