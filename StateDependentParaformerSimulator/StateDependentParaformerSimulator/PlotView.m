#import "PlotView.h"
#include <float.h>

static const NSUInteger kMaxSamples = 360;

@interface PlotView ()
@property (nonatomic) NSMutableArray<NSNumber *> *samples;
@end

@implementation PlotView

- (instancetype)initWithTitle:(NSString *)title unit:(NSString *)unit color:(NSColor *)color {
    self = [super initWithFrame:NSZeroRect];
    if (self) {
        _title = [title copy];
        _unit = [unit copy];
        _strokeColor = color;
        _samples = [NSMutableArray arrayWithCapacity:kMaxSamples];
        self.wantsLayer = YES;
        self.layer.cornerRadius = 8.0;
        self.layer.masksToBounds = YES;
        self.layer.backgroundColor = [[NSColor colorWithCalibratedRed:0.035 green:0.055 blue:0.080 alpha:0.92] CGColor];
    }
    return self;
}

- (BOOL)isFlipped {
    return YES;
}

- (void)appendValue:(double)value {
    self.latestValue = value;
    [self.samples addObject:@(value)];
    if (self.samples.count > kMaxSamples) {
        [self.samples removeObjectAtIndex:0];
    }
    self.needsDisplay = YES;
}

- (void)clear {
    [self.samples removeAllObjects];
    self.latestValue = 0.0;
    self.needsDisplay = YES;
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];

    NSRect bounds = self.bounds;
    NSGraphicsContext *context = [NSGraphicsContext currentContext];
    CGContextRef cg = context.CGContext;

    NSGradient *gradient = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithCalibratedRed:0.040 green:0.064 blue:0.094 alpha:1.0]
                                                         endingColor:[NSColor colorWithCalibratedRed:0.020 green:0.030 blue:0.050 alpha:1.0]];
    [gradient drawInRect:bounds angle:90.0];

    NSBezierPath *outline = [NSBezierPath bezierPathWithRoundedRect:NSInsetRect(bounds, 0.7, 0.7) xRadius:8 yRadius:8];
    [[NSColor colorWithCalibratedWhite:0.80 alpha:0.18] setStroke];
    outline.lineWidth = 1.0;
    [outline stroke];

    NSDictionary *titleAttrs = @{
        NSFontAttributeName: [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightSemibold],
        NSForegroundColorAttributeName: [NSColor colorWithCalibratedWhite:0.88 alpha:0.94]
    };
    NSDictionary *valueAttrs = @{
        NSFontAttributeName: [NSFont monospacedDigitSystemFontOfSize:13 weight:NSFontWeightBold],
        NSForegroundColorAttributeName: self.strokeColor ?: NSColor.systemCyanColor
    };
    [self.title drawAtPoint:NSMakePoint(12, 9) withAttributes:titleAttrs];
    NSString *value = [NSString stringWithFormat:@"%8.3f %@", self.latestValue, self.unit ?: @""];
    NSSize valueSize = [value sizeWithAttributes:valueAttrs];
    [value drawAtPoint:NSMakePoint(NSMaxX(bounds) - valueSize.width - 12, 8) withAttributes:valueAttrs];

    NSRect plot = NSInsetRect(bounds, 14, 34);
    plot.origin.y += 10;
    plot.size.height -= 14;

    [[NSColor colorWithCalibratedWhite:1.0 alpha:0.08] setStroke];
    for (NSInteger i = 0; i <= 4; i++) {
        CGFloat y = plot.origin.y + plot.size.height * (CGFloat)i / 4.0;
        NSBezierPath *line = [NSBezierPath bezierPath];
        [line moveToPoint:NSMakePoint(plot.origin.x, y)];
        [line lineToPoint:NSMakePoint(NSMaxX(plot), y)];
        [line stroke];
    }
    for (NSInteger i = 0; i <= 5; i++) {
        CGFloat x = plot.origin.x + plot.size.width * (CGFloat)i / 5.0;
        NSBezierPath *line = [NSBezierPath bezierPath];
        [line moveToPoint:NSMakePoint(x, plot.origin.y)];
        [line lineToPoint:NSMakePoint(x, NSMaxY(plot))];
        [line stroke];
    }

    if (self.samples.count < 2) {
        return;
    }

    double minV = DBL_MAX;
    double maxV = -DBL_MAX;
    for (NSNumber *sample in self.samples) {
        double v = sample.doubleValue;
        minV = MIN(minV, v);
        maxV = MAX(maxV, v);
    }
    if (fabs(maxV - minV) < 1e-9) {
        maxV += 1.0;
        minV -= 1.0;
    }
    double pad = 0.12 * (maxV - minV);
    minV -= pad;
    maxV += pad;

    NSBezierPath *path = [NSBezierPath bezierPath];
    for (NSUInteger i = 0; i < self.samples.count; i++) {
        double v = self.samples[i].doubleValue;
        CGFloat x = plot.origin.x + plot.size.width * (CGFloat)i / (CGFloat)(MAX(self.samples.count - 1, 1));
        CGFloat y = NSMaxY(plot) - plot.size.height * (CGFloat)((v - minV) / (maxV - minV));
        if (i == 0) {
            [path moveToPoint:NSMakePoint(x, y)];
        } else {
            [path lineToPoint:NSMakePoint(x, y)];
        }
    }

    CGContextSaveGState(cg);
    CGContextSetShadowWithColor(cg, CGSizeMake(0, 0), 8.0, self.strokeColor.CGColor);
    [self.strokeColor setStroke];
    path.lineWidth = 2.2;
    [path stroke];
    CGContextRestoreGState(cg);
}

@end
