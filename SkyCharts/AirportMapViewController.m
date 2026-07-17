#import "AirportMapViewController.h"
#import <QuartzCore/QuartzCore.h>

static CGFloat SkyDistanceToSegment(CGPoint point, CGPoint start, CGPoint end) {
    CGFloat dx=end.x-start.x,dy=end.y-start.y,length=dx*dx+dy*dy;
    if(length<=.001)return hypot(point.x-start.x,point.y-start.y);
    CGFloat value=((point.x-start.x)*dx+(point.y-start.y)*dy)/length;value=MAX(0,MIN(1,value));
    CGPoint nearest=CGPointMake(start.x+value*dx,start.y+value*dy);
    return hypot(point.x-nearest.x,point.y-nearest.y);
}

static CGRect SkyLabelRect(NSString *text, CGPoint point, UIFont *font, CGFloat scale) {
    CGFloat padding=3/MAX(.01,scale),vertical=1/MAX(.01,scale);CGSize size=[text sizeWithFont:font];
    return CGRectMake(point.x-size.width/2-padding,point.y-size.height/2-vertical,size.width+padding*2,size.height+vertical*2);
}

static BOOL SkyLabelFits(CGRect box, NSArray *occupied, CGFloat margin, CGFloat scale) {
    CGRect candidate=CGRectInset(box,-margin/MAX(.01,scale),-margin/MAX(.01,scale));
    for(NSValue *value in occupied)if(CGRectIntersectsRect(candidate,[value CGRectValue]))return NO;
    return YES;
}

static void SkyDrawLabel(NSString *text, CGPoint point, UIFont *font, UIColor *textColor, UIColor *fillColor, UIColor *borderColor, CGFloat scale) {
    if(!text.length)return;CGRect box=SkyLabelRect(text,point,font,scale);[fillColor setFill];UIBezierPath *background=[UIBezierPath bezierPathWithRoundedRect:box cornerRadius:2/MAX(.01,scale)];[background fill];if(borderColor){[borderColor setStroke];background.lineWidth=.7/MAX(.01,scale);[background stroke];}[textColor set];CGFloat padding=3/MAX(.01,scale),vertical=1/MAX(.01,scale);[text drawAtPoint:CGPointMake(box.origin.x+padding,box.origin.y+vertical)withFont:font];
}

static CGPoint SkyRunwayPoint(CGPoint start, CGFloat alongX, CGFloat alongY, CGFloat along, CGFloat across) {
    return CGPointMake(start.x+alongX*along-alongY*across,start.y+alongY*along+alongX*across);
}

static void SkyFillRunwayRect(CGContextRef context, CGPoint center, CGFloat angle, CGFloat length, CGFloat width, UIColor *color) {
    CGContextSaveGState(context);CGContextTranslateCTM(context,center.x,center.y);CGContextRotateCTM(context,angle);[color setFill];CGContextFillRect(context,CGRectMake(-length/2,-width/2,length,width));CGContextRestoreGState(context);
}

@interface AirportMapCanvas : UIView
@property(nonatomic,retain) NSDictionary *mapData;
@property(nonatomic,retain) NSArray *features;
@property(nonatomic,retain) NSArray *backgroundFeatures;
@property(nonatomic,retain) NSArray *taxiwayFeatures;
@property(nonatomic,retain) NSArray *runwayRecords;
@property(nonatomic,retain) NSArray *standFeatures;
@property(nonatomic,retain) NSArray *terminalFeatures;
@property(nonatomic,retain) CAShapeLayer *taxiCenterlineLayer;
@property(nonatomic,assign) CGFloat labelScale;
- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size;
- (CGPoint)mapPoint:(NSArray *)coordinate;
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance;
- (void)configureForFitScale:(CGFloat)fitScale;
- (void)updateTaxiCenterlineForDisplayScale:(CGFloat)displayScale;
@end

@implementation AirportMapCanvas
@synthesize mapData=_mapData,features=_features,backgroundFeatures=_backgroundFeatures,taxiwayFeatures=_taxiwayFeatures,runwayRecords=_runwayRecords,standFeatures=_standFeatures,terminalFeatures=_terminalFeatures,taxiCenterlineLayer=_taxiCenterlineLayer,labelScale=_labelScale;

- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size {
    if((self=[super initWithFrame:CGRectMake(0,0,size.width,size.height)])){
        self.opaque=YES;self.contentScaleFactor=1;self.layer.contentsScale=1;self.backgroundColor=[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1];self.mapData=mapData;self.features=[mapData objectForKey:@"features"]?:[NSArray array];self.labelScale=1;
        NSMutableArray *background=[NSMutableArray array],*taxiways=[NSMutableArray array],*stands=[NSMutableArray array],*terminals=[NSMutableArray array];NSMutableDictionary *runwayGroups=[NSMutableDictionary dictionary];NSUInteger anonymous=0;
        for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];
            if([kind isEqual:@"apron"]||[kind isEqual:@"terminal"]||[kind isEqual:@"hangar"]){[background addObject:feature];if([kind isEqual:@"terminal"])[terminals addObject:feature];}
            else if([kind isEqual:@"taxiway"]||[kind isEqual:@"taxilane"])[taxiways addObject:feature];
            else if([kind isEqual:@"parking_position"]||[kind isEqual:@"gate"])[stands addObject:feature];
            else if([kind isEqual:@"runway"]){NSString *reference=[[[feature objectForKey:@"ref"]?:@"" stringByReplacingOccurrencesOfString:@" " withString:@""]uppercaseString];if(!reference.length)reference=[NSString stringWithFormat:@"RUNWAY-%lu",(unsigned long)++anonymous];NSMutableDictionary *group=[runwayGroups objectForKey:reference];if(!group){group=[NSMutableDictionary dictionaryWithObjectsAndKeys:[NSMutableArray array],@"points",[NSNumber numberWithDouble:0],@"width",nil];[runwayGroups setObject:group forKey:reference];}NSMutableArray *points=[group objectForKey:@"points"];for(NSArray *coordinate in [feature objectForKey:@"points"])[points addObject:coordinate];double width=[[feature objectForKey:@"width"]doubleValue];if(width>[[group objectForKey:@"width"]doubleValue])[group setObject:[NSNumber numberWithDouble:width]forKey:@"width"];}
        }
        self.backgroundFeatures=background;self.taxiwayFeatures=taxiways;self.standFeatures=stands;self.terminalFeatures=terminals;UIBezierPath *centerlines=[UIBezierPath bezierPath];for(NSDictionary *feature in taxiways){UIBezierPath *path=[self pathForFeature:feature];if(path)[centerlines appendPath:path];}CAShapeLayer *centerline=[CAShapeLayer layer];centerline.frame=self.bounds;centerline.path=centerlines.CGPath;centerline.fillColor=[UIColor clearColor].CGColor;centerline.strokeColor=[UIColor colorWithRed:1 green:.79 blue:.03 alpha:1].CGColor;centerline.lineCap=kCALineCapRound;centerline.lineJoin=kCALineJoinRound;[self.layer addSublayer:centerline];self.taxiCenterlineLayer=centerline;[self updateTaxiCenterlineForDisplayScale:1];NSMutableArray *runways=[NSMutableArray array];
        for(NSString *reference in runwayGroups){NSDictionary *group=[runwayGroups objectForKey:reference];NSArray *points=[group objectForKey:@"points"];if(points.count<2)continue;CGPoint first=CGPointZero,last=CGPointZero;CGFloat farthest=-1;for(NSUInteger left=0;left<points.count;left++)for(NSUInteger right=left+1;right<points.count;right++){CGPoint a=[self mapPoint:[points objectAtIndex:left]],b=[self mapPoint:[points objectAtIndex:right]];CGFloat dx=a.x-b.x,dy=a.y-b.y,distance=dx*dx+dy*dy;if(distance>farthest){farthest=distance;first=a;last=b;}}[runways addObject:[NSDictionary dictionaryWithObjectsAndKeys:reference,@"ref",[NSValue valueWithCGPoint:first],@"start",[NSValue valueWithCGPoint:last],@"end",[group objectForKey:@"width"],@"width",nil]];}
        self.runwayRecords=runways;
    }return self;
}
- (CGPoint)mapPoint:(NSArray *)coordinate {
    NSDictionary *bounds=[self.mapData objectForKey:@"bounds"];CGFloat padding=75;
    double minLon=[[bounds objectForKey:@"minLon"]doubleValue],maxLon=[[bounds objectForKey:@"maxLon"]doubleValue],minLat=[[bounds objectForKey:@"minLat"]doubleValue],maxLat=[[bounds objectForKey:@"maxLat"]doubleValue];
    double lon=[[coordinate objectAtIndex:0]doubleValue],lat=[[coordinate objectAtIndex:1]doubleValue];
    CGFloat width=MAX(1,self.bounds.size.width-padding*2),height=MAX(1,self.bounds.size.height-padding*2);
    return CGPointMake(padding+(lon-minLon)/MAX(.0000001,maxLon-minLon)*width,padding+(maxLat-lat)/MAX(.0000001,maxLat-minLat)*height);
}
- (UIBezierPath *)pathForFeature:(NSDictionary *)feature {
    NSArray *points=[feature objectForKey:@"points"];if(!points.count)return nil;UIBezierPath *path=[UIBezierPath bezierPath];[path moveToPoint:[self mapPoint:[points objectAtIndex:0]]];for(NSUInteger index=1;index<points.count;index++)[path addLineToPoint:[self mapPoint:[points objectAtIndex:index]]];if([[feature objectForKey:@"closed"]boolValue])[path closePath];return path;
}
- (UIColor *)fillForKind:(NSString *)kind {
    if([kind isEqual:@"apron"])return [UIColor colorWithRed:.33 green:.36 blue:.39 alpha:1];
    if([kind isEqual:@"terminal"])return [UIColor colorWithRed:.16 green:.22 blue:.34 alpha:1];
    if([kind isEqual:@"hangar"])return [UIColor colorWithRed:.20 green:.25 blue:.29 alpha:1];
    return nil;
}
- (UIFont *)labelFontWithScreenSize:(CGFloat)size { return [UIFont boldSystemFontOfSize:size/MAX(.01,self.labelScale)]; }
- (CGFloat)mapPointsPerMeter {
    NSDictionary *bounds=[self.mapData objectForKey:@"bounds"];double minLon=[[bounds objectForKey:@"minLon"]doubleValue],maxLon=[[bounds objectForKey:@"maxLon"]doubleValue],minLat=[[bounds objectForKey:@"minLat"]doubleValue],maxLat=[[bounds objectForKey:@"maxLat"]doubleValue],middleLat=(minLat+maxLat)/2;CGFloat padding=75;double eastWest=MAX(1,(maxLon-minLon)*111320.0*cos(middleLat*3.14159265359/180.0)),northSouth=MAX(1,(maxLat-minLat)*111320.0);CGFloat horizontal=MAX(1,self.bounds.size.width-padding*2)/eastWest,vertical=MAX(1,self.bounds.size.height-padding*2)/northSouth;return (horizontal+vertical)/2;
}
- (void)drawRunway:(NSDictionary *)runway context:(CGContextRef)context {
    CGPoint start=[[runway objectForKey:@"start"]CGPointValue],end=[[runway objectForKey:@"end"]CGPointValue];CGFloat dx=end.x-start.x,dy=end.y-start.y,length=hypot(dx,dy);if(length<1)return;CGFloat alongX=dx/length,alongY=dy/length,angle=atan2(dy,dx),meters=[[runway objectForKey:@"width"]doubleValue],pointsPerMeter=[self mapPointsPerMeter];if(meters<=0)meters=45;CGFloat width=MAX(4.5/MAX(.01,self.labelScale),meters*pointsPerMeter),edge=MAX(.65/MAX(.01,self.labelScale),width*.025);
    UIBezierPath *center=[UIBezierPath bezierPath];[center moveToPoint:start];[center addLineToPoint:end];center.lineCapStyle=kCGLineCapButt;[[UIColor colorWithWhite:.48 alpha:1]setStroke];center.lineWidth=width+MAX(2/MAX(.01,self.labelScale),4*pointsPerMeter);[center stroke];[[UIColor colorWithRed:.105 green:.12 blue:.135 alpha:1]setStroke];center.lineWidth=width;[center stroke];
    CGFloat side=width/2-edge*.9;for(NSInteger sign=-1;sign<=1;sign+=2){CGPoint a=SkyRunwayPoint(start,alongX,alongY,0,side*sign),b=SkyRunwayPoint(start,alongX,alongY,length,side*sign);UIBezierPath *line=[UIBezierPath bezierPath];[line moveToPoint:a];[line addLineToPoint:b];[[UIColor colorWithWhite:.88 alpha:1]setStroke];line.lineWidth=edge;[line stroke];}
    CGFloat threshold=MAX(width*.75,12/MAX(.01,self.labelScale)),markingStart=threshold+width*2.9,markingEnd=MAX(markingStart,length-markingStart);if(markingEnd>markingStart){UIBezierPath *dash=[UIBezierPath bezierPath];[dash moveToPoint:SkyRunwayPoint(start,alongX,alongY,markingStart,0)];[dash addLineToPoint:SkyRunwayPoint(start,alongX,alongY,markingEnd,0)];CGFloat pattern[]={MAX(width*.75,10/MAX(.01,self.labelScale)),MAX(width*.55,7/MAX(.01,self.labelScale))};CGContextSaveGState(context);CGContextSetLineDash(context,0,pattern,2);[[UIColor colorWithWhite:.88 alpha:1]setStroke];dash.lineWidth=MAX(edge,width*.045);[dash stroke];CGContextRestoreGState(context);}
    for(NSInteger runwayEnd=0;runwayEnd<2;runwayEnd++){CGFloat direction=runwayEnd? -1:1,origin=runwayEnd?length:0,inset=threshold;CGPoint thresholdCenter=SkyRunwayPoint(start,alongX,alongY,origin+direction*inset,0);SkyFillRunwayRect(context,thresholdCenter,angle,MAX(edge*1.25,width*.035),width*.84,[UIColor colorWithWhite:.90 alpha:1]);NSInteger stripes=8;for(NSInteger stripe=0;stripe<stripes;stripe++){CGFloat across=(-.39+(CGFloat)stripe*(.78/(stripes-1)))*width;CGPoint stripeCenter=SkyRunwayPoint(start,alongX,alongY,origin+direction*(inset+width*.48),across);SkyFillRunwayRect(context,stripeCenter,angle,width*.72,width*.055,[UIColor colorWithWhite:.90 alpha:1]);}
        CGFloat aimingDistance=MIN(length*.28,300*pointsPerMeter);if(aimingDistance>width*4&&aimingDistance<length/2){for(NSInteger sideMark=-1;sideMark<=1;sideMark+=2){CGPoint aiming=SkyRunwayPoint(start,alongX,alongY,origin+direction*aimingDistance,sideMark*width*.27);SkyFillRunwayRect(context,aiming,angle,MAX(width*.85,35*pointsPerMeter),width*.12,[UIColor colorWithWhite:.90 alpha:1]);}}
        for(NSInteger zone=1;zone<=2;zone++){CGFloat zoneDistance=(150+zone*150)*pointsPerMeter;if(zoneDistance>=length/2||zoneDistance<=aimingDistance+width)continue;for(NSInteger sideMark=-1;sideMark<=1;sideMark+=2){CGPoint touchdown=SkyRunwayPoint(start,alongX,alongY,origin+direction*zoneDistance,sideMark*width*.28);SkyFillRunwayRect(context,touchdown,angle,MAX(width*.38,15*pointsPerMeter),width*.075,[UIColor colorWithWhite:.82 alpha:1]);}}
    }
}
- (void)drawRect:(CGRect)rect {
    CGContextRef context=UIGraphicsGetCurrentContext();CGContextSetAllowsAntialiasing(context,YES);CGContextSetShouldAntialias(context,YES);CGContextSetLineCap(context,kCGLineCapRound);CGContextSetLineJoin(context,kCGLineJoinRound);
    [[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1]setFill];CGContextFillRect(context,self.bounds);
    for(NSDictionary *feature in self.backgroundFeatures){UIColor *fill=[self fillForKind:[feature objectForKey:@"kind"]];UIBezierPath *path=[self pathForFeature:feature];if(!fill||!path)continue;[fill setFill];[path fill];[[UIColor colorWithWhite:.48 alpha:.55]setStroke];path.lineWidth=1.5/MAX(.01,self.labelScale);[path stroke];}
    for(NSDictionary *feature in self.taxiwayFeatures){UIBezierPath *path=[self pathForFeature:feature];if(!path)continue;NSString *kind=[feature objectForKey:@"kind"];path.lineCapStyle=kCGLineCapRound;path.lineJoinStyle=kCGLineJoinRound;[[UIColor colorWithWhite:.40 alpha:1]setStroke];path.lineWidth=([kind isEqual:@"taxilane"]?3.5:6.5)/MAX(.01,self.labelScale);[path stroke];}
    for(NSDictionary *runway in self.runwayRecords)[self drawRunway:runway context:context];
    UIFont *runwayFont=[self labelFontWithScreenSize:15];for(NSDictionary *runway in self.runwayRecords){NSString *reference=[runway objectForKey:@"ref"];NSArray *ends=[reference componentsSeparatedByString:@"/"];NSString *first=ends.count?[ends objectAtIndex:0]:reference,*last=ends.count>1?[ends lastObject]:reference;for(NSDictionary *marker in [NSArray arrayWithObjects:[NSDictionary dictionaryWithObjectsAndKeys:first,@"text",[runway objectForKey:@"start"],@"point",nil],[NSDictionary dictionaryWithObjectsAndKeys:last,@"text",[runway objectForKey:@"end"],@"point",nil],nil]){NSString *text=[marker objectForKey:@"text"];CGPoint point=[[marker objectForKey:@"point"]CGPointValue];SkyDrawLabel(text,point,runwayFont,[UIColor whiteColor],[UIColor colorWithWhite:.02 alpha:.94],[UIColor colorWithWhite:.76 alpha:1],self.labelScale);}}
    CGFloat standScale=MAX(.01,self.labelScale*2.2);for(NSDictionary *feature in self.standFeatures){UIBezierPath *path=[self pathForFeature:feature];if(!path)continue;[[UIColor colorWithRed:.55 green:.72 blue:.62 alpha:.58]setStroke];path.lineWidth=.65/standScale;[path stroke];}
    NSString *north=@"N";UIFont *northFont=[UIFont boldSystemFontOfSize:22];[[UIColor whiteColor]set];[north drawAtPoint:CGPointMake(self.bounds.size.width-52,28)withFont:northFont];CGContextSetStrokeColorWithColor(context,[UIColor whiteColor].CGColor);CGContextSetLineWidth(context,3);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-42,93);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-50,72);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-34,72);CGContextStrokePath(context);
}
- (void)updateTaxiCenterlineForDisplayScale:(CGFloat)displayScale { if(displayScale<=0)return;[CATransaction begin];[CATransaction setDisableActions:YES];self.taxiCenterlineLayer.lineWidth=.78/MAX(.01,displayScale);[CATransaction commit]; }
- (void)configureForFitScale:(CGFloat)fitScale { if(fitScale>0&&fabs(fitScale-self.labelScale)>.001){self.labelScale=fitScale;[self updateTaxiCenterlineForDisplayScale:fitScale];[self setNeedsDisplay];} }
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance {
    NSDictionary *best=nil;CGFloat bestDistance=tolerance;
    for(NSDictionary *feature in self.features){NSArray *points=[feature objectForKey:@"points"];if(!points.count)continue;CGFloat distance=CGFLOAT_MAX;if(points.count==1){CGPoint target=[self mapPoint:[points objectAtIndex:0]];distance=hypot(point.x-target.x,point.y-target.y);}else for(NSUInteger index=1;index<points.count;index++)distance=MIN(distance,SkyDistanceToSegment(point,[self mapPoint:[points objectAtIndex:index-1]],[self mapPoint:[points objectAtIndex:index]]));if(distance<bestDistance){bestDistance=distance;best=feature;}}
    return best;
}
- (void)dealloc { [_mapData release];[_features release];[_backgroundFeatures release];[_taxiwayFeatures release];[_runwayRecords release];[_standFeatures release];[_terminalFeatures release];[_taxiCenterlineLayer release];[super dealloc]; }
@end

static NSInteger SkyTaxiReferenceSort(id left, id right, void *context) {
    NSDictionary *lengths=(NSDictionary *)context;double a=[[lengths objectForKey:left]doubleValue],b=[[lengths objectForKey:right]doubleValue];if(a>b)return NSOrderedAscending;if(a<b)return NSOrderedDescending;return [left compare:right];
}

static BOOL SkyTerminalSuffixIsValid(NSString *value) { if(value.length==1)return [[NSCharacterSet alphanumericCharacterSet]characterIsMember:[value characterAtIndex:0]];if(value.length>3)return NO;for(NSUInteger index=0;index<value.length;index++){unichar character=[value characterAtIndex:index];if(character<'0'||character>'9')return NO;}return YES; }
static NSString *SkyTerminalDisplayName(NSString *value) { value=[value stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];if(!value.length)return nil;if([value rangeOfString:@"terminal"options:NSCaseInsensitiveSearch].location==0)return [@"Terminal "stringByAppendingString:[[value substringFromIndex:8]stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]];NSString *upper=[value uppercaseString];if([upper hasPrefix:@"T"]&&upper.length>1)upper=[upper substringFromIndex:1];return [@"Terminal "stringByAppendingString:upper]; }

static NSString *SkyTerminalLabel(NSDictionary *feature) {
    NSString *label=[feature objectForKey:@"label"],*reference=[feature objectForKey:@"ref"];
    if(label.length)return SkyTerminalDisplayName(label);
    if(reference.length)return SkyTerminalDisplayName(reference);
    NSString *name=[feature objectForKey:@"name"];if(!name.length)return nil;NSArray *tokens=[name componentsSeparatedByCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    for(NSUInteger index=0;index<tokens.count;index++){NSString *token=[[tokens objectAtIndex:index]stringByTrimmingCharactersInSet:[NSCharacterSet punctuationCharacterSet]],*lower=[token lowercaseString];if(([lower hasPrefix:@"terminal"]||[lower hasPrefix:@"terminl"])&&index+1<tokens.count){NSString *number=[[[tokens objectAtIndex:index+1]stringByTrimmingCharactersInSet:[NSCharacterSet punctuationCharacterSet]]uppercaseString];if(SkyTerminalSuffixIsValid(number))return SkyTerminalDisplayName(number);}}
    for(NSUInteger index=0;index+1<name.length;index++){unichar marker=[name characterAtIndex:index],next=[name characterAtIndex:index+1];if((marker=='T'||marker=='t')&&next>='0'&&next<='9'){NSMutableString *value=[NSMutableString string];for(NSUInteger digit=index+1;digit<name.length&&value.length<4;digit++){unichar character=[name characterAtIndex:digit];if(character<'0'||character>'9')break;[value appendFormat:@"%C",character];}return SkyTerminalDisplayName(value);}}
    return nil;
}

@interface AirportMapLabelOverlay : UIView
@property(nonatomic,assign) AirportMapCanvas *canvas;
@property(nonatomic,assign) UIScrollView *scrollView;
- (id)initWithCanvas:(AirportMapCanvas *)canvas scrollView:(UIScrollView *)scrollView;
@end

@implementation AirportMapLabelOverlay
@synthesize canvas=_canvas,scrollView=_scrollView;

- (id)initWithCanvas:(AirportMapCanvas *)canvas scrollView:(UIScrollView *)scrollView { if((self=[super initWithFrame:CGRectZero])){self.canvas=canvas;self.scrollView=scrollView;self.opaque=NO;self.backgroundColor=[UIColor clearColor];self.userInteractionEnabled=NO;self.contentMode=UIViewContentModeRedraw;}return self; }
- (CGPoint)screenPointForCoordinate:(NSArray *)coordinate { return [self.canvas convertPoint:[self.canvas mapPoint:coordinate]toView:self]; }
- (CGPoint)screenPointForCanvasValue:(NSValue *)value { return [self.canvas convertPoint:[value CGPointValue]toView:self]; }
- (CGPoint)screenAnchorForFeature:(NSDictionary *)feature { NSArray *points=[feature objectForKey:@"points"];if(!points.count)return CGPointZero;CGFloat x=0,y=0;for(NSArray *coordinate in points){CGPoint point=[self.canvas mapPoint:coordinate];x+=point.x;y+=point.y;}return [self.canvas convertPoint:CGPointMake(x/points.count,y/points.count)toView:self]; }
- (NSValue *)availablePointForText:(NSString *)text around:(CGPoint)point font:(UIFont *)font occupied:(NSArray *)occupied margin:(CGFloat)margin {
    static const CGFloat offsets[][2]={{0,0},{0,-14},{0,14},{-18,0},{18,0},{-14,-13},{14,-13},{-14,13},{14,13}};CGRect safe=CGRectInset(self.bounds,2,2);for(NSUInteger index=0;index<9;index++){CGPoint candidate=CGPointMake(point.x+offsets[index][0],point.y+offsets[index][1]);CGRect box=SkyLabelRect(text,candidate,font,1);if(CGRectContainsRect(safe,box)&&SkyLabelFits(box,occupied,margin,1))return [NSValue valueWithCGPoint:candidate];}return nil;
}
- (NSArray *)screenCandidatesForFeature:(NSDictionary *)feature spacing:(CGFloat)spacing length:(CGFloat *)totalLength {
    NSArray *coordinates=[feature objectForKey:@"points"];if(coordinates.count<2)return [NSArray array];NSMutableArray *screen=[NSMutableArray arrayWithCapacity:coordinates.count];CGFloat total=0;for(NSArray *coordinate in coordinates){CGPoint point=[self screenPointForCoordinate:coordinate];if(screen.count){CGPoint prior=[[screen lastObject]CGPointValue];total+=hypot(point.x-prior.x,point.y-prior.y);}[screen addObject:[NSValue valueWithCGPoint:point]];}if(totalLength)*totalLength=total;if(total<8)return [NSArray array];NSInteger count=MAX(1,(NSInteger)ceil(total/MAX(55,spacing)));NSMutableArray *candidates=[NSMutableArray array];for(NSInteger marker=0;marker<count;marker++){CGFloat target=total*((CGFloat)marker+.5)/(CGFloat)count,walked=0;CGPoint previous=[[screen objectAtIndex:0]CGPointValue];for(NSUInteger index=1;index<screen.count;index++){CGPoint current=[[screen objectAtIndex:index]CGPointValue];CGFloat length=hypot(current.x-previous.x,current.y-previous.y);if(walked+length>=target){CGFloat fraction=length>0?(target-walked)/length:0;CGPoint point=CGPointMake(previous.x+(current.x-previous.x)*fraction,previous.y+(current.y-previous.y)*fraction);if(CGRectContainsPoint(CGRectInset(self.bounds,-20,-20),point))[candidates addObject:[NSValue valueWithCGPoint:point]];break;}walked+=length;previous=current;}}return candidates;
}
- (void)reserveRunwayBadges:(NSMutableArray *)occupied {
    for(NSDictionary *runway in self.canvas.runwayRecords){for(NSString *key in [NSArray arrayWithObjects:@"start",@"end",nil]){CGPoint point=[self screenPointForCanvasValue:[runway objectForKey:key]];if(CGRectContainsPoint(CGRectInset(self.bounds,-40,-40),point))[occupied addObject:[NSValue valueWithCGRect:CGRectMake(point.x-34,point.y-23,68,46)]];}}
}
- (void)drawTaxiwayLabels:(NSMutableArray *)occupied {
    CGFloat fit=MAX(.001,self.scrollView.minimumZoomScale),detail=MAX(1,self.scrollView.zoomScale/fit);NSMutableDictionary *groups=[NSMutableDictionary dictionary],*lengths=[NSMutableDictionary dictionary];for(NSDictionary *feature in self.canvas.taxiwayFeatures){NSString *reference=[[[feature objectForKey:@"ref"]?:@"" stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]uppercaseString];if(!reference.length||reference.length>7)continue;CGFloat length=0;NSArray *values=[self screenCandidatesForFeature:feature spacing:145 length:&length];if(!values.count)continue;NSMutableArray *group=[groups objectForKey:reference];if(!group){group=[NSMutableArray array];[groups setObject:group forKey:reference];}[group addObjectsFromArray:values];[lengths setObject:[NSNumber numberWithDouble:[[lengths objectForKey:reference]doubleValue]+length]forKey:reference];}
    NSArray *references=[[groups allKeys]sortedArrayUsingFunction:SkyTaxiReferenceSort context:lengths];UIFont *font=[UIFont boldSystemFontOfSize:11];NSUInteger density=(NSUInteger)MAX(22,MIN(50,self.bounds.size.width*self.bounds.size.height/17000.0)),lodBonus=(NSUInteger)MIN(12,MAX(0,log(detail)/log(2.0)*6)),labelLimit=MIN(60,density+lodBonus),labelsDrawn=0;CGContextRef context=UIGraphicsGetCurrentContext();for(NSString *reference in references){CGFloat screenLength=[[lengths objectForKey:reference]doubleValue],baseLength=screenLength/detail,reveal=baseLength>=85?.7:(baseLength>=45?1.2:(baseLength>=24?1.8:2.7)),alpha=MIN(1,MAX(0,(detail-(reveal-.45))/.45));if(alpha<=.03)continue;NSMutableArray *accepted=[NSMutableArray array];BOOL drew=NO;NSUInteger referenceLimit=MIN(4,MAX(1,(NSUInteger)ceil(screenLength/360.0))),referenceCount=0;CGContextSaveGState(context);CGContextSetAlpha(context,alpha);for(NSValue *value in [groups objectForKey:reference]){if(labelsDrawn>=labelLimit||referenceCount>=referenceLimit)break;CGPoint point=[value CGPointValue];BOOL duplicate=NO;for(NSValue *priorValue in accepted){CGPoint prior=[priorValue CGPointValue];if(hypot(point.x-prior.x,point.y-prior.y)<110){duplicate=YES;break;}}if(duplicate)continue;NSValue *placed=[self availablePointForText:reference around:point font:font occupied:occupied margin:4];if(!placed&&!drew)placed=[self availablePointForText:reference around:point font:font occupied:occupied margin:1];if(!placed)continue;CGPoint labelPoint=[placed CGPointValue];CGRect box=SkyLabelRect(reference,labelPoint,font,1);SkyDrawLabel(reference,labelPoint,font,[UIColor colorWithRed:1 green:.86 blue:.08 alpha:1],[UIColor colorWithWhite:.03 alpha:.92],[UIColor colorWithWhite:.25 alpha:1],1);[occupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-4,-4)]];[accepted addObject:[NSValue valueWithCGPoint:point]];drew=YES;labelsDrawn++;referenceCount++;}CGContextRestoreGState(context);if(labelsDrawn>=labelLimit)break;}
}
- (void)drawTerminalLabels:(NSMutableArray *)occupied {
    UIFont *font=[UIFont boldSystemFontOfSize:10];CGContextRef context=UIGraphicsGetCurrentContext();NSMutableDictionary *accepted=[NSMutableDictionary dictionary];for(NSDictionary *feature in self.canvas.terminalFeatures){NSString *reference=SkyTerminalLabel(feature);if(!reference.length)continue;CGPoint anchor=[self screenAnchorForFeature:feature];if(!CGRectContainsPoint(CGRectInset(self.bounds,-35,-35),anchor))continue;NSValue *previous=[accepted objectForKey:reference];if(previous&&hypot(anchor.x-[previous CGPointValue].x,anchor.y-[previous CGPointValue].y)<90)continue;NSValue *placed=[self availablePointForText:reference around:anchor font:font occupied:occupied margin:2];if(!placed)placed=[self availablePointForText:reference around:anchor font:font occupied:[NSArray array]margin:0];if(!placed)continue;CGPoint labelPoint=[placed CGPointValue];CGContextSetStrokeColorWithColor(context,[UIColor colorWithWhite:.70 alpha:.72].CGColor);CGContextSetLineWidth(context,.65);CGContextMoveToPoint(context,anchor.x,anchor.y);CGContextAddLineToPoint(context,labelPoint.x,labelPoint.y);CGContextStrokePath(context);CGRect box=SkyLabelRect(reference,labelPoint,font,1);SkyDrawLabel(reference,labelPoint,font,[UIColor colorWithWhite:.94 alpha:1],[UIColor colorWithWhite:.04 alpha:.88],[UIColor colorWithWhite:.58 alpha:.85],1);[occupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-2,-2)]];[accepted setObject:[NSValue valueWithCGPoint:anchor]forKey:reference];}
}
- (void)drawStandLabels:(NSMutableArray *)occupied {
    CGFloat fit=MAX(.001,self.scrollView.minimumZoomScale),detail=self.scrollView.zoomScale/fit,alpha=MIN(1,MAX(0,(detail-1.2)/.65));if(alpha<=.01)return;CGFloat fontSize=MAX(8.5,9.7-MIN(1.2,MAX(0,detail-1.65)*.45));UIFont *font=[UIFont boldSystemFontOfSize:fontSize];CGFloat margin=MAX(1,2.2-MIN(1.2,MAX(0,detail-1.65)*.35));CGContextRef context=UIGraphicsGetCurrentContext();CGContextSaveGState(context);CGContextSetAlpha(context,alpha);for(NSInteger pass=0;pass<2;pass++)for(NSDictionary *feature in self.canvas.standFeatures){NSString *kind=[feature objectForKey:@"kind"];if((pass==0&&![kind isEqual:@"gate"])||(pass==1&&![kind isEqual:@"parking_position"]))continue;NSString *reference=[feature objectForKey:@"ref"]?:[feature objectForKey:@"name"];NSArray *points=[feature objectForKey:@"points"];if(!reference.length||!points.count)continue;CGPoint anchor=[self screenPointForCoordinate:[points lastObject]];if(!CGRectContainsPoint(CGRectInset(self.bounds,-28,-28),anchor))continue;CGPoint preferred=CGPointMake(anchor.x,anchor.y-10);NSValue *placed=[self availablePointForText:reference around:preferred font:font occupied:occupied margin:margin];if(!placed)continue;CGPoint labelPoint=[placed CGPointValue];CGContextSetStrokeColorWithColor(context,[UIColor colorWithWhite:.70 alpha:.72].CGColor);CGContextSetLineWidth(context,.65);CGContextMoveToPoint(context,anchor.x,anchor.y);CGContextAddLineToPoint(context,labelPoint.x,labelPoint.y);CGContextStrokePath(context);CGRect box=SkyLabelRect(reference,labelPoint,font,1);SkyDrawLabel(reference,labelPoint,font,[UIColor colorWithWhite:.94 alpha:1],[UIColor colorWithWhite:.04 alpha:.88],[UIColor colorWithWhite:.58 alpha:.85],1);[occupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-margin,-margin)]];}CGContextRestoreGState(context);
}
- (void)drawRect:(CGRect)rect { NSMutableArray *occupied=[NSMutableArray array];[self reserveRunwayBadges:occupied];[self drawTerminalLabels:occupied];[self drawTaxiwayLabels:occupied];[self drawStandLabels:occupied]; }
@end

@interface AirportMapViewController ()
@property(nonatomic,retain) NSString *icao;
@property(nonatomic,retain) NSString *mapPath;
@property(nonatomic,retain) NSDictionary *mapData;
@property(nonatomic,retain) UIScrollView *scrollView;
@property(nonatomic,retain) AirportMapCanvas *canvas;
@property(nonatomic,retain) AirportMapLabelOverlay *labelOverlay;
@property(nonatomic,retain) UILabel *attributionLabel;
@property(nonatomic,retain) CADisplayLink *labelDisplayLink;
@property(nonatomic,assign) CGSize lastLayoutSize;
@property(nonatomic,assign) BOOL hasAppeared;
@property(nonatomic,assign) BOOL labelRefreshPending;
@end

@implementation AirportMapViewController
@synthesize icao=_icao,mapPath=_mapPath,mapData=_mapData,scrollView=_scrollView,canvas=_canvas,labelOverlay=_labelOverlay,attributionLabel=_attributionLabel,labelDisplayLink=_labelDisplayLink,lastLayoutSize=_lastLayoutSize,hasAppeared=_hasAppeared,labelRefreshPending=_labelRefreshPending;

- (id)initWithICAO:(NSString *)icao mapPath:(NSString *)mapPath { if((self=[super init])){self.icao=icao;self.mapPath=mapPath;}return self; }
- (CGSize)canvasSize {
    NSDictionary *bounds=[self.mapData objectForKey:@"bounds"];double minLon=[[bounds objectForKey:@"minLon"]doubleValue],maxLon=[[bounds objectForKey:@"maxLon"]doubleValue],minLat=[[bounds objectForKey:@"minLat"]doubleValue],maxLat=[[bounds objectForKey:@"maxLat"]doubleValue],middleLat=(minLat+maxLat)/2;
    double width=MAX(.0001,(maxLon-minLon)*cos(middleLat*3.14159265359/180.0)),height=MAX(.0001,maxLat-minLat),ratio=width/height;
    if(ratio>=1)return CGSizeMake(2600,MAX(1100,2600/ratio));return CGSizeMake(MAX(1100,2600*ratio),2600);
}
- (void)viewDidLoad {
    [super viewDidLoad];NSData *data=[NSData dataWithContentsOfFile:self.mapPath];self.mapData=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;self.title=[NSString stringWithFormat:@"%@ Airport Map",self.icao];self.view.backgroundColor=[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1];
    self.navigationItem.leftBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)]autorelease];self.navigationItem.rightBarButtonItem=[[[UIBarButtonItem alloc]initWithTitle:@"Fit" style:UIBarButtonItemStyleBordered target:self action:@selector(fitMap)]autorelease];
    self.scrollView=[[[UIScrollView alloc]initWithFrame:CGRectZero]autorelease];self.scrollView.delegate=self;self.scrollView.backgroundColor=self.view.backgroundColor;self.scrollView.bouncesZoom=YES;self.scrollView.maximumZoomScale=5;[self.view addSubview:self.scrollView];
    self.canvas=[[[AirportMapCanvas alloc]initWithMapData:self.mapData?:[NSDictionary dictionary]size:[self canvasSize]]autorelease];[self.scrollView addSubview:self.canvas];self.scrollView.contentSize=self.canvas.bounds.size;
    self.labelOverlay=[[[AirportMapLabelOverlay alloc]initWithCanvas:self.canvas scrollView:self.scrollView]autorelease];[self.view addSubview:self.labelOverlay];
    UITapGestureRecognizer *tap=[[[UITapGestureRecognizer alloc]initWithTarget:self action:@selector(mapTapped:)]autorelease];tap.numberOfTapsRequired=1;[self.canvas addGestureRecognizer:tap];self.canvas.userInteractionEnabled=YES;
    self.attributionLabel=[[[UILabel alloc]initWithFrame:CGRectZero]autorelease];self.attributionLabel.backgroundColor=[UIColor colorWithRed:.04 green:.05 blue:.07 alpha:1];self.attributionLabel.textColor=[UIColor colorWithWhite:.76 alpha:1];self.attributionLabel.font=[UIFont boldSystemFontOfSize:11];self.attributionLabel.textAlignment=NSTextAlignmentCenter;NSDictionary *counts=[self.mapData objectForKey:@"counts"];self.attributionLabel.text=[NSString stringWithFormat:@"Offline vector map • %d runways • %d taxiways • %d stands • © OpenStreetMap contributors",[[counts objectForKey:@"runway"]intValue],[[counts objectForKey:@"taxiway"]intValue]+[[counts objectForKey:@"taxilane"]intValue],[[counts objectForKey:@"parking_position"]intValue]];[self.view addSubview:self.attributionLabel];
}
- (void)viewWillLayoutSubviews { [super viewWillLayoutSubviews];CGSize size=self.view.bounds.size;self.scrollView.frame=CGRectMake(0,0,size.width,size.height-28);self.labelOverlay.frame=self.scrollView.frame;self.attributionLabel.frame=CGRectMake(0,size.height-28,size.width,28); }
- (void)viewDidLayoutSubviews { [super viewDidLayoutSubviews];CGSize size=self.view.bounds.size;if(!CGSizeEqualToSize(self.lastLayoutSize,size)){self.lastLayoutSize=size;[self fitMap];} }
- (void)startLabelDisplayLink { if(self.labelDisplayLink)return;CADisplayLink *link=[CADisplayLink displayLinkWithTarget:self selector:@selector(labelDisplayLinkFired:)];link.frameInterval=2;link.paused=YES;[link addToRunLoop:[NSRunLoop mainRunLoop]forMode:NSRunLoopCommonModes];self.labelDisplayLink=link; }
- (void)stopLabelDisplayLink { [self.labelDisplayLink invalidate];self.labelDisplayLink=nil;self.labelRefreshPending=NO; }
- (void)viewDidAppear:(BOOL)animated { [super viewDidAppear:animated];[self startLabelDisplayLink];if(!self.hasAppeared){self.hasAppeared=YES;[self fitMap];} }
- (void)viewWillDisappear:(BOOL)animated { [self stopLabelDisplayLink];[super viewWillDisappear:animated]; }
- (void)done { [self dismissModalViewControllerAnimated:YES]; }
- (UIView *)viewForZoomingInScrollView:(UIScrollView *)scrollView { return self.canvas; }
- (void)centerMap { CGSize bounds=self.scrollView.bounds.size;CGFloat scale=MAX(.01,self.scrollView.zoomScale),contentWidth=self.canvas.bounds.size.width*scale,contentHeight=self.canvas.bounds.size.height*scale,horizontal=MAX(0,(bounds.width-contentWidth)/2),vertical=MAX(0,(bounds.height-contentHeight)/2);self.scrollView.contentInset=UIEdgeInsetsMake(vertical,horizontal,vertical,horizontal); }
- (void)renderMapLabelsNow { self.labelOverlay.hidden=NO;[self.labelOverlay.layer setNeedsDisplay];[self.labelOverlay.layer displayIfNeeded]; }
- (void)labelDisplayLinkFired:(CADisplayLink *)link { if(!self.labelRefreshPending){link.paused=YES;return;}self.labelRefreshPending=NO;[self renderMapLabelsNow];link.paused=YES; }
- (void)refreshMapLabels { self.labelRefreshPending=NO;[self renderMapLabelsNow]; }
- (void)scheduleMapLabelRefresh { self.labelRefreshPending=YES;if(self.labelDisplayLink)self.labelDisplayLink.paused=NO;else [self refreshMapLabels]; }
- (void)forceMapLabelRefresh { self.labelRefreshPending=NO;[self renderMapLabelsNow];self.labelDisplayLink.paused=YES; }
- (void)scrollViewDidScroll:(UIScrollView *)scrollView { [self scheduleMapLabelRefresh]; }
- (void)scrollViewDidZoom:(UIScrollView *)scrollView { [self centerMap];[self.canvas updateTaxiCenterlineForDisplayScale:scrollView.zoomScale];[self scheduleMapLabelRefresh]; }
- (void)scrollViewWillBeginZooming:(UIScrollView *)scrollView withView:(UIView *)view { [self scheduleMapLabelRefresh]; }
- (void)scrollViewDidEndZooming:(UIScrollView *)scrollView withView:(UIView *)view atScale:(CGFloat)scale { [self.canvas updateTaxiCenterlineForDisplayScale:scale];[self forceMapLabelRefresh]; }
- (void)scrollViewWillBeginDragging:(UIScrollView *)scrollView { [self scheduleMapLabelRefresh]; }
- (void)scrollViewDidEndDragging:(UIScrollView *)scrollView willDecelerate:(BOOL)decelerate { if(!decelerate)[self forceMapLabelRefresh]; }
- (void)scrollViewDidEndDecelerating:(UIScrollView *)scrollView { [self forceMapLabelRefresh]; }
- (void)fitMap { if(!self.canvas)return;[self.view layoutIfNeeded];CGSize bounds=self.scrollView.bounds.size,content=self.canvas.bounds.size;if(bounds.width<=0||bounds.height<=0)return;CGFloat scale=MIN(bounds.width/content.width,bounds.height/content.height)*.96;self.scrollView.minimumZoomScale=scale;self.scrollView.maximumZoomScale=MAX(5,scale*6);[self.canvas configureForFitScale:scale];[self.scrollView setZoomScale:scale animated:NO];[self centerMap];UIEdgeInsets inset=self.scrollView.contentInset;self.scrollView.contentOffset=CGPointMake(-inset.left,-inset.top);[self forceMapLabelRefresh]; }
- (NSString *)displayNameForKind:(NSString *)kind { NSDictionary *names=[NSDictionary dictionaryWithObjectsAndKeys:@"Runway",@"runway",@"Taxiway",@"taxiway",@"Taxilane",@"taxilane",@"Apron",@"apron",@"Parking Stand",@"parking_position",@"Gate",@"gate",@"Holding Position",@"holding_position",@"Terminal",@"terminal",@"Hangar",@"hangar",nil];return [names objectForKey:kind]?:[kind capitalizedString]; }
- (void)mapTapped:(UITapGestureRecognizer *)gesture { if(gesture.state!=UIGestureRecognizerStateRecognized)return;CGPoint point=[gesture locationInView:self.canvas];CGFloat tolerance=MAX(12,28/MAX(.01,self.scrollView.zoomScale));NSDictionary *feature=[self.canvas featureAtPoint:point tolerance:tolerance];if(!feature)return;NSString *kind=[self displayNameForKind:[feature objectForKey:@"kind"]],*reference=[feature objectForKey:@"ref"],*name=[feature objectForKey:@"name"],*surface=[feature objectForKey:@"surface"];NSMutableArray *details=[NSMutableArray array];if(reference.length)[details addObject:[@"Reference: "stringByAppendingString:reference]];if(name.length&&![name isEqual:reference])[details addObject:name];if(surface.length)[details addObject:[@"Surface: "stringByAppendingString:surface]];UIAlertView *alert=[[[UIAlertView alloc]initWithTitle:kind message:details.count?[details componentsJoinedByString:@"\n"]:@"No additional information is available for this map feature." delegate:nil cancelButtonTitle:@"Done" otherButtonTitles:nil]autorelease];[alert show]; }
- (BOOL)shouldAutorotateToInterfaceOrientation:(UIInterfaceOrientation)orientation { return YES; }
- (void)dealloc { [_labelDisplayLink invalidate];[_icao release];[_mapPath release];[_mapData release];[_scrollView release];[_canvas release];[_labelOverlay release];[_attributionLabel release];[_labelDisplayLink release];[super dealloc]; }
@end
