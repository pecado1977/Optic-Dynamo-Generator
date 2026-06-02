#import "SimulationView.h"

static CGFloat clamp01(CGFloat v) {
    return MAX(0.0, MIN(1.0, v));
}

@implementation SimulationView

- (instancetype)initWithFrame:(NSRect)frameRect {
    self = [super initWithFrame:frameRect];
    if (self) {
        self.wantsLayer = YES;
        self.layer.opaque = YES;
        self.layer.backgroundColor = [[NSColor colorWithCalibratedRed:0.028 green:0.044 blue:0.067 alpha:1.0] CGColor];
        _running = YES;
        _frequencyHz = 128000.0;
        _couplingK = 0.08;
        _inductanceUH = 92.051753;
        _capacitanceNF = 16.795319;
        _resistanceOhm = 6.169368;
        _loadOhm = 6.169368;
        _temperatureC = 25.0;
        _turns = 8.0;
        _gapMM = 2.0;
        _muScale = 1.0;
        _bSatT = 1.56;
        _driveVRMS = 183.0;
    }
    return self;
}

- (BOOL)isFlipped {
    return YES;
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];

    NSRect b = self.bounds;
    NSGraphicsContext *ctx = [NSGraphicsContext currentContext];
    CGContextRef cg = ctx.CGContext;

    NSGradient *bg = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithCalibratedRed:0.020 green:0.032 blue:0.052 alpha:1.0]
                                                   endingColor:[NSColor colorWithCalibratedRed:0.075 green:0.105 blue:0.135 alpha:1.0]];
    [bg drawInRect:b angle:270.0];

    [self drawHeaderInRect:b];
    [self drawPanelGridInRect:NSMakeRect(26, 104, b.size.width - 52, b.size.height - 130)];
    [self drawMiniSurfacesInRect:b];
    [self drawParaformerInRect:b context:cg];
    [self drawHUDInRect:b];
}

- (void)drawHeaderInRect:(NSRect)b {
    NSDictionary *titleAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:34 weight:NSFontWeightBold],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.94 alpha:0.96]
    };
    NSDictionary *subAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:15 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.70 alpha:0.82]
    };
    [@"State-Dependent Paraformer Simulator" drawAtPoint:NSMakePoint(30, 24) withAttributes:titleAttrs];
    [@"AMCC-1000 orthogonal resonant coupler - live coefficients, voltages, currents, resistance and matched transfer" drawAtPoint:NSMakePoint(33, 68) withAttributes:subAttrs];
}

- (void)drawPanelGridInRect:(NSRect)r {
    [[NSColor colorWithCalibratedWhite:0.78 alpha:0.15] setStroke];
    NSBezierPath *outer = [NSBezierPath bezierPathWithRoundedRect:r xRadius:7 yRadius:7];
    outer.lineWidth = 1.0;
    [outer stroke];

    NSInteger cols = 5;
    NSInteger rows = 4;
    for (NSInteger i = 1; i < cols; i++) {
        CGFloat x = r.origin.x + r.size.width * (CGFloat)i / (CGFloat)cols;
        NSBezierPath *line = [NSBezierPath bezierPath];
        [line moveToPoint:NSMakePoint(x, r.origin.y)];
        [line lineToPoint:NSMakePoint(x, NSMaxY(r))];
        [line stroke];
    }
    for (NSInteger i = 1; i < rows; i++) {
        CGFloat y = r.origin.y + r.size.height * (CGFloat)i / (CGFloat)rows;
        NSBezierPath *line = [NSBezierPath bezierPath];
        [line moveToPoint:NSMakePoint(r.origin.x, y)];
        [line lineToPoint:NSMakePoint(NSMaxX(r), y)];
        [line stroke];
    }
}

- (void)drawMiniSurfacesInRect:(NSRect)b {
    NSArray<NSString *> *labels = @[
        @"Inductance", @"Capacitance", @"Resistance", @"Permeability", @"Permittivity",
        @"Conductivity", @"Characteristic Z", @"Amplifier gain", @"Resonant f0", @"Mutual M"
    ];
    CGFloat cellW = (b.size.width - 52) / 5.0;
    CGFloat cellH = (b.size.height - 130) / 4.0;
    NSInteger labelIndex = 0;
    for (NSInteger row = 0; row < 4; row++) {
        for (NSInteger col = 0; col < 5; col++) {
            BOOL central = (row == 1 && (col == 1 || col == 2 || col == 3)) || (row == 2 && (col == 1 || col == 2 || col == 3));
            if (central || labelIndex >= labels.count) {
                continue;
            }
            NSRect cell = NSMakeRect(26 + col * cellW, 104 + row * cellH, cellW, cellH);
            [self drawSmallPlotInRect:NSInsetRect(cell, 18, 18) label:labels[labelIndex++]];
        }
    }
}

- (void)drawSmallPlotInRect:(NSRect)r label:(NSString *)label {
    NSDictionary *labelAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:13 weight:NSFontWeightMedium],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.76 alpha:0.82]
    };
    [label drawAtPoint:NSMakePoint(r.origin.x, r.origin.y) withAttributes:labelAttrs];

    NSRect plot = NSMakeRect(r.origin.x + 2, r.origin.y + 28, r.size.width - 10, r.size.height - 42);
    [[NSColor colorWithCalibratedWhite:0.95 alpha:0.25] setStroke];
    NSBezierPath *axes = [NSBezierPath bezierPath];
    [axes moveToPoint:NSMakePoint(plot.origin.x, NSMaxY(plot))];
    [axes lineToPoint:NSMakePoint(plot.origin.x, plot.origin.y)];
    [axes moveToPoint:NSMakePoint(plot.origin.x, NSMaxY(plot))];
    [axes lineToPoint:NSMakePoint(NSMaxX(plot), NSMaxY(plot))];
    axes.lineWidth = 1.0;
    [axes stroke];

    for (NSInteger i = 0; i < 9; i++) {
        CGFloat x0 = plot.origin.x + plot.size.width * (CGFloat)i / 8.0;
        CGFloat x1 = plot.origin.x + plot.size.width * (CGFloat)(i + 1) / 8.0;
        CGFloat phase = self.phase + i * 0.21;
        CGFloat y0 = NSMaxY(plot) - plot.size.height * (0.28 + 0.48 * clamp01((sin(phase) + 1.0) * 0.5));
        CGFloat y1 = NSMaxY(plot) - plot.size.height * (0.28 + 0.48 * clamp01((sin(phase + 0.7) + 1.0) * 0.5));
        NSBezierPath *line = [NSBezierPath bezierPath];
        [line moveToPoint:NSMakePoint(x0, y0)];
        [line lineToPoint:NSMakePoint(x1, y1)];
        NSColor *c = [NSColor colorWithCalibratedRed:0.20 + 0.55 * i / 8.0 green:0.78 - 0.25 * i / 8.0 blue:0.92 - 0.58 * i / 8.0 alpha:0.82];
        [c setStroke];
        line.lineWidth = 2.0;
        [line stroke];
    }
}

- (void)drawParaformerInRect:(NSRect)b context:(CGContextRef)cg {
    CGPoint center = CGPointMake(NSMidX(b), NSMidY(b) + 40.0);
    CGFloat scale = MIN(b.size.width, b.size.height) / 760.0;

    for (NSInteger i = 0; i < 18; i++) {
        CGFloat t = ((CGFloat)i / 17.0);
        CGFloat phase = self.phase + t * M_PI * 2.0;
        CGFloat w = (210.0 + 165.0 * t) * scale;
        CGFloat h = (86.0 + 130.0 * sin(phase) * 0.18 + 165.0 * t) * scale;
        NSRect ellipse = NSMakeRect(center.x - w / 2.0 + cos(phase) * 22.0 * scale,
                                    center.y - h / 2.0 + sin(phase) * 14.0 * scale,
                                    w,
                                    h);
        NSBezierPath *line = [NSBezierPath bezierPathWithOvalInRect:ellipse];
        NSColor *field = (i % 2 == 0)
            ? [NSColor colorWithCalibratedRed:0.42 green:0.82 blue:1.00 alpha:0.34]
            : [NSColor colorWithCalibratedRed:1.00 green:0.66 blue:0.32 alpha:0.28];
        [field setStroke];
        line.lineWidth = 1.2 + 1.0 * t;
        [line stroke];
    }

    CGContextSaveGState(cg);
    CGContextSetShadowWithColor(cg, CGSizeMake(0, 8), 24.0, [[NSColor colorWithCalibratedWhite:0 alpha:0.55] CGColor]);

    NSColor *coreLight = [NSColor colorWithCalibratedRed:0.78 green:0.84 blue:0.84 alpha:1.0];
    NSColor *coreDark = [NSColor colorWithCalibratedRed:0.36 green:0.43 blue:0.45 alpha:1.0];
    NSGradient *coreGradient = [[NSGradient alloc] initWithStartingColor:coreLight endingColor:coreDark];

    NSRect base = NSMakeRect(center.x - 230 * scale, center.y - 38 * scale, 460 * scale, 106 * scale);
    NSBezierPath *basePath = [NSBezierPath bezierPathWithRoundedRect:base xRadius:24 * scale yRadius:24 * scale];
    [coreGradient drawInBezierPath:basePath angle:-32.0];
    [[NSColor colorWithCalibratedWhite:1.0 alpha:0.28] setStroke];
    basePath.lineWidth = 2.0;
    [basePath stroke];

    NSArray<NSValue *> *limbs = @[
        [NSValue valueWithRect:NSMakeRect(center.x - 186 * scale, center.y - 238 * scale, 96 * scale, 254 * scale)],
        [NSValue valueWithRect:NSMakeRect(center.x + 90 * scale, center.y - 238 * scale, 96 * scale, 254 * scale)]
    ];
    for (NSValue *v in limbs) {
        NSRect limb = v.rectValue;
        NSBezierPath *limbPath = [NSBezierPath bezierPathWithRoundedRect:limb xRadius:22 * scale yRadius:22 * scale];
        [coreGradient drawInBezierPath:limbPath angle:-18.0];
        [[NSColor colorWithCalibratedWhite:1.0 alpha:0.25] setStroke];
        limbPath.lineWidth = 2.0;
        [limbPath stroke];
    }
    CGContextRestoreGState(cg);

    [self drawCopperCoilAt:NSMakePoint(center.x - 138 * scale, center.y - 64 * scale) width:118 * scale height:70 * scale turns:16 vertical:NO];
    [self drawCopperCoilAt:NSMakePoint(center.x + 128 * scale, center.y - 154 * scale) width:72 * scale height:128 * scale turns:14 vertical:YES];

    NSDictionary *axisAttrs = @{
        NSFontAttributeName: [NSFont systemFontOfSize:22 weight:NSFontWeightBold],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedRed:1.0 green:0.70 blue:0.35 alpha:0.95]
    };
    [@"X" drawAtPoint:NSMakePoint(center.x - 258 * scale, center.y + 114 * scale) withAttributes:axisAttrs];
    [@"Y" drawAtPoint:NSMakePoint(center.x + 248 * scale, center.y + 116 * scale) withAttributes:axisAttrs];

    NSDictionary *formulaAttrs = @{
        NSFontAttributeName: [NSFont fontWithName:@"Times New Roman" size:28] ?: [NSFont systemFontOfSize:28 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.96 alpha:0.92]
    };
    [@"L(I,B,T)" drawAtPoint:NSMakePoint(center.x - 316 * scale, center.y - 244 * scale) withAttributes:formulaAttrs];
    [@"M(θ,x,t)" drawAtPoint:NSMakePoint(center.x + 155 * scale, center.y + 202 * scale) withAttributes:formulaAttrs];
    [@"μ(B,T,σ)" drawAtPoint:NSMakePoint(center.x - 258 * scale, center.y + 202 * scale) withAttributes:formulaAttrs];
}

- (void)drawCopperCoilAt:(NSPoint)p width:(CGFloat)w height:(CGFloat)h turns:(NSInteger)turns vertical:(BOOL)vertical {
    NSColor *copper = [NSColor colorWithCalibratedRed:0.96 green:0.56 blue:0.32 alpha:0.92];
    NSColor *copperDark = [NSColor colorWithCalibratedRed:0.45 green:0.22 blue:0.14 alpha:0.92];
    for (NSInteger i = 0; i < turns; i++) {
        CGFloat q = (CGFloat)i / MAX((CGFloat)turns - 1.0, 1.0);
        NSBezierPath *line = [NSBezierPath bezierPath];
        if (vertical) {
            CGFloat x = p.x - w / 2.0 + q * w;
            [line moveToPoint:NSMakePoint(x, p.y - h / 2.0)];
            [line lineToPoint:NSMakePoint(x + 10.0 * sin(self.phase + q * 5.0), p.y + h / 2.0)];
        } else {
            CGFloat x = p.x - w / 2.0 + q * w;
            [line moveToPoint:NSMakePoint(x, p.y - h / 2.0)];
            [line lineToPoint:NSMakePoint(x + 8.0 * sin(self.phase + q * 4.0), p.y + h / 2.0)];
        }
        [(i % 2 == 0 ? copper : copperDark) setStroke];
        line.lineWidth = 3.0;
        [line stroke];
    }
}

- (void)drawHUDInRect:(NSRect)b {
    NSArray<NSArray *> *items = @[
        @[@"f0", [NSString stringWithFormat:@"%.1f kHz", self.frequencyHz / 1000.0]],
        @[@"k", [NSString stringWithFormat:@"%.3f", self.couplingK]],
        @[@"L", [NSString stringWithFormat:@"%.3f uH", self.inductanceUH]],
        @[@"C", [NSString stringWithFormat:@"%.3f nF", self.capacitanceNF]],
        @[@"R", [NSString stringWithFormat:@"%.3f ohm", self.resistanceOhm]],
        @[@"I", [NSString stringWithFormat:@"%.3f Arms", self.currentARMS]],
        @[@"V", [NSString stringWithFormat:@"%.1f Vrms", self.voltageVRMS]],
        @[@"Pmax", [NSString stringWithFormat:@"%.2f W", self.pMaxW]],
        @[@"Bpk", [NSString stringWithFormat:@"%.4f T", self.fluxPeakT]],
        @[@"Z", [NSString stringWithFormat:@"%.2f ohm", self.zOhm]]
    ];

    CGFloat cardW = 132.0;
    CGFloat cardH = 48.0;
    CGFloat gap = 10.0;
    CGFloat startX = 34.0;
    CGFloat y = NSMaxY(b) - 72.0;
    NSDictionary *nameAttrs = @{
        NSFontAttributeName: [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.68 alpha:0.9]
    };
    NSDictionary *valueAttrs = @{
        NSFontAttributeName: [NSFont monospacedDigitSystemFontOfSize:14 weight:NSFontWeightBold],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedRed:0.70 green:0.91 blue:1.0 alpha:0.96]
    };

    for (NSUInteger i = 0; i < items.count; i++) {
        CGFloat x = startX + (cardW + gap) * (CGFloat)i;
        if (x + cardW > b.size.width - 28) {
            break;
        }
        NSRect card = NSMakeRect(x, y, cardW, cardH);
        NSBezierPath *path = [NSBezierPath bezierPathWithRoundedRect:card xRadius:8 yRadius:8];
        [[NSColor colorWithCalibratedWhite:0.0 alpha:0.24] setFill];
        [path fill];
        [[NSColor colorWithCalibratedWhite:1.0 alpha:0.14] setStroke];
        [path stroke];
        [items[i][0] drawAtPoint:NSMakePoint(x + 10, y + 7) withAttributes:nameAttrs];
        [items[i][1] drawAtPoint:NSMakePoint(x + 10, y + 24) withAttributes:valueAttrs];
    }
}

@end
