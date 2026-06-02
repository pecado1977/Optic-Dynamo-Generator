#import <Cocoa/Cocoa.h>

@interface SimulationView : NSView

@property (nonatomic) BOOL running;
@property (nonatomic) double time;
@property (nonatomic) double frequencyHz;
@property (nonatomic) double couplingK;
@property (nonatomic) double inductanceUH;
@property (nonatomic) double capacitanceNF;
@property (nonatomic) double resistanceOhm;
@property (nonatomic) double loadOhm;
@property (nonatomic) double temperatureC;
@property (nonatomic) double turns;
@property (nonatomic) double gapMM;
@property (nonatomic) double muScale;
@property (nonatomic) double bSatT;
@property (nonatomic) double driveVRMS;
@property (nonatomic) double currentARMS;
@property (nonatomic) double voltageVRMS;
@property (nonatomic) double mutualUH;
@property (nonatomic) double fluxPeakT;
@property (nonatomic) double pMaxW;
@property (nonatomic) double zOhm;
@property (nonatomic) double reactiveVAR;
@property (nonatomic) double phase;

@end
