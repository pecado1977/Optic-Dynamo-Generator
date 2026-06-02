#import <Cocoa/Cocoa.h>

@interface PlotView : NSView

@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSString *unit;
@property (nonatomic) NSColor *strokeColor;
@property (nonatomic) double latestValue;

- (instancetype)initWithTitle:(NSString *)title unit:(NSString *)unit color:(NSColor *)color;
- (void)appendValue:(double)value;
- (void)clear;

@end
