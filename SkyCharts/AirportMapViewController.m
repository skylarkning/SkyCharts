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

@interface AirportMapCanvas : UIView
@property(nonatomic,retain) NSDictionary *mapData;
@property(nonatomic,retain) NSArray *features;
@property(nonatomic,retain) NSArray *backgroundFeatures;
@property(nonatomic,retain) NSArray *taxiwayFeatures;
@property(nonatomic,retain) NSArray *runwayRecords;
@property(nonatomic,retain) NSArray *standFeatures;
@property(nonatomic,assign) CGFloat labelScale;
- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size;
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance;
- (void)configureForFitScale:(CGFloat)fitScale;
@end

@implementation AirportMapCanvas
@synthesize mapData=_mapData,features=_features,backgroundFeatures=_backgroundFeatures,taxiwayFeatures=_taxiwayFeatures,runwayRecords=_runwayRecords,standFeatures=_standFeatures,labelScale=_labelScale;

- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size {
    if((self=[super initWithFrame:CGRectMake(0,0,size.width,size.height)])){
        self.opaque=YES;self.contentScaleFactor=1;self.layer.contentsScale=1;self.backgroundColor=[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1];self.mapData=mapData;self.features=[mapData objectForKey:@"features"]?:[NSArray array];self.labelScale=1;
        NSMutableArray *background=[NSMutableArray array],*taxiways=[NSMutableArray array],*stands=[NSMutableArray array];NSMutableDictionary *runwayGroups=[NSMutableDictionary dictionary];NSUInteger anonymous=0;
        for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];
            if([kind isEqual:@"apron"]||[kind isEqual:@"terminal"]||[kind isEqual:@"hangar"])[background addObject:feature];
            else if([kind isEqual:@"taxiway"]||[kind isEqual:@"taxilane"])[taxiways addObject:feature];
            else if([kind isEqual:@"parking_position"]||[kind isEqual:@"gate"])[stands addObject:feature];
            else if([kind isEqual:@"runway"]){NSString *reference=[[[feature objectForKey:@"ref"]?:@"" stringByReplacingOccurrencesOfString:@" " withString:@""]uppercaseString];if(!reference.length)reference=[NSString stringWithFormat:@"RUNWAY-%lu",(unsigned long)++anonymous];NSMutableArray *points=[runwayGroups objectForKey:reference];if(!points){points=[NSMutableArray array];[runwayGroups setObject:points forKey:reference];}for(NSArray *coordinate in [feature objectForKey:@"points"])[points addObject:coordinate];}
        }
        self.backgroundFeatures=background;self.taxiwayFeatures=taxiways;self.standFeatures=stands;NSMutableArray *runways=[NSMutableArray array];
        for(NSString *reference in runwayGroups){NSArray *points=[runwayGroups objectForKey:reference];if(points.count<2)continue;CGPoint first=CGPointZero,last=CGPointZero;CGFloat farthest=-1;for(NSUInteger left=0;left<points.count;left++)for(NSUInteger right=left+1;right<points.count;right++){CGPoint a=[self mapPoint:[points objectAtIndex:left]],b=[self mapPoint:[points objectAtIndex:right]];CGFloat dx=a.x-b.x,dy=a.y-b.y,distance=dx*dx+dy*dy;if(distance>farthest){farthest=distance;first=a;last=b;}}[runways addObject:[NSDictionary dictionaryWithObjectsAndKeys:reference,@"ref",[NSValue valueWithCGPoint:first],@"start",[NSValue valueWithCGPoint:last],@"end",nil]];}
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
- (NSArray *)markerPointsForFeature:(NSDictionary *)feature {
    NSArray *coordinates=[feature objectForKey:@"points"];if(coordinates.count<2)return [NSArray array];NSMutableArray *points=[NSMutableArray array];CGFloat total=0;CGPoint previous=[self mapPoint:[coordinates objectAtIndex:0]];for(NSUInteger index=1;index<coordinates.count;index++){CGPoint current=[self mapPoint:[coordinates objectAtIndex:index]];total+=hypot(current.x-previous.x,current.y-previous.y);previous=current;}if(total*self.labelScale<48)return [NSArray array];NSInteger count=MAX(1,(NSInteger)floor(total/(145/MAX(.01,self.labelScale))));for(NSInteger marker=0;marker<count;marker++){CGFloat target=total*((CGFloat)marker+.5)/(CGFloat)count,walked=0;previous=[self mapPoint:[coordinates objectAtIndex:0]];for(NSUInteger index=1;index<coordinates.count;index++){CGPoint current=[self mapPoint:[coordinates objectAtIndex:index]];CGFloat length=hypot(current.x-previous.x,current.y-previous.y);if(walked+length>=target){CGFloat fraction=length>0?(target-walked)/length:0;[points addObject:[NSValue valueWithCGPoint:CGPointMake(previous.x+(current.x-previous.x)*fraction,previous.y+(current.y-previous.y)*fraction)]];break;}walked+=length;previous=current;}}
    return points;
}
- (void)drawRect:(CGRect)rect {
    CGContextRef context=UIGraphicsGetCurrentContext();CGContextSetAllowsAntialiasing(context,YES);CGContextSetShouldAntialias(context,YES);CGContextSetLineCap(context,kCGLineCapRound);CGContextSetLineJoin(context,kCGLineJoinRound);
    [[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1]setFill];CGContextFillRect(context,self.bounds);
    for(NSDictionary *feature in self.backgroundFeatures){UIColor *fill=[self fillForKind:[feature objectForKey:@"kind"]];UIBezierPath *path=[self pathForFeature:feature];if(!fill||!path)continue;[fill setFill];[path fill];[[UIColor colorWithWhite:.48 alpha:.55]setStroke];path.lineWidth=1.5/MAX(.01,self.labelScale);[path stroke];}
    for(NSDictionary *feature in self.taxiwayFeatures){UIBezierPath *path=[self pathForFeature:feature];if(!path)continue;NSString *kind=[feature objectForKey:@"kind"];[[UIColor colorWithWhite:.40 alpha:1]setStroke];path.lineWidth=([kind isEqual:@"taxilane"]?5:9)/MAX(.01,self.labelScale);[path stroke];[[UIColor colorWithRed:1 green:.79 blue:.03 alpha:1]setStroke];path.lineWidth=1.2/MAX(.01,self.labelScale);[path stroke];}
    for(NSDictionary *runway in self.runwayRecords){UIBezierPath *path=[UIBezierPath bezierPath];[path moveToPoint:[[runway objectForKey:@"start"]CGPointValue]];[path addLineToPoint:[[runway objectForKey:@"end"]CGPointValue]];path.lineCapStyle=kCGLineCapButt;[[UIColor colorWithWhite:.78 alpha:1]setStroke];path.lineWidth=24/MAX(.01,self.labelScale);[path stroke];[[UIColor colorWithWhite:.075 alpha:1]setStroke];path.lineWidth=20/MAX(.01,self.labelScale);[path stroke];CGFloat dash[]={18/MAX(.01,self.labelScale),12/MAX(.01,self.labelScale)};CGContextSaveGState(context);CGContextSetLineDash(context,0,dash,2);[[UIColor whiteColor]setStroke];path.lineWidth=1.8/MAX(.01,self.labelScale);[path stroke];CGContextRestoreGState(context);}
    NSMutableArray *occupied=[NSMutableArray array];UIFont *runwayFont=[self labelFontWithScreenSize:15];for(NSDictionary *runway in self.runwayRecords){NSString *reference=[runway objectForKey:@"ref"];NSArray *ends=[reference componentsSeparatedByString:@"/"];NSString *first=ends.count?[ends objectAtIndex:0]:reference,*last=ends.count>1?[ends lastObject]:reference;for(NSDictionary *marker in [NSArray arrayWithObjects:[NSDictionary dictionaryWithObjectsAndKeys:first,@"text",[runway objectForKey:@"start"],@"point",nil],[NSDictionary dictionaryWithObjectsAndKeys:last,@"text",[runway objectForKey:@"end"],@"point",nil],nil]){NSString *text=[marker objectForKey:@"text"];CGPoint point=[[marker objectForKey:@"point"]CGPointValue];CGRect box=SkyLabelRect(text,point,runwayFont,self.labelScale);if(!SkyLabelFits(box,occupied,3,self.labelScale))continue;SkyDrawLabel(text,point,runwayFont,[UIColor whiteColor],[UIColor colorWithWhite:.02 alpha:.92],[UIColor colorWithWhite:.75 alpha:1],self.labelScale);[occupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-3/MAX(.01,self.labelScale),-3/MAX(.01,self.labelScale))]];}}
    UIFont *taxiFont=[self labelFontWithScreenSize:10];for(NSDictionary *feature in self.taxiwayFeatures){NSString *reference=[[[feature objectForKey:@"ref"]?:@"" stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]uppercaseString];if(!reference.length||reference.length>6)continue;for(NSValue *value in [self markerPointsForFeature:feature]){CGPoint point=[value CGPointValue];CGRect box=SkyLabelRect(reference,point,taxiFont,self.labelScale);if(!SkyLabelFits(box,occupied,4,self.labelScale))continue;SkyDrawLabel(reference,point,taxiFont,[UIColor colorWithRed:1 green:.86 blue:.08 alpha:1],[UIColor colorWithWhite:.03 alpha:.90],[UIColor colorWithWhite:.22 alpha:1],self.labelScale);[occupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-4/MAX(.01,self.labelScale),-4/MAX(.01,self.labelScale))]];}}
    CGFloat standScale=MAX(.01,self.labelScale*2.2);for(NSDictionary *feature in self.standFeatures){UIBezierPath *path=[self pathForFeature:feature];if(!path)continue;[[UIColor colorWithRed:.55 green:.72 blue:.62 alpha:.58]setStroke];path.lineWidth=.8/standScale;[path stroke];}
    NSMutableArray *standOccupied=[NSMutableArray array];UIFont *standFont=[UIFont boldSystemFontOfSize:8.5/standScale];for(NSInteger pass=0;pass<2;pass++)for(NSDictionary *feature in self.standFeatures){NSString *kind=[feature objectForKey:@"kind"];if((pass==0&&![kind isEqual:@"gate"])||(pass==1&&![kind isEqual:@"parking_position"]))continue;NSString *reference=[[feature objectForKey:@"ref"]?:[feature objectForKey:@"name"] description];NSArray *points=[feature objectForKey:@"points"];if(!reference.length||!points.count)continue;CGPoint anchor=[self mapPoint:[points lastObject]],point=CGPointMake(anchor.x,anchor.y-7/standScale);CGRect box=SkyLabelRect(reference,point,standFont,standScale);if(!SkyLabelFits(box,standOccupied,5,standScale))continue;CGContextSetStrokeColorWithColor(context,[UIColor colorWithWhite:.72 alpha:.7].CGColor);CGContextSetLineWidth(context,.6/standScale);CGContextMoveToPoint(context,anchor.x,anchor.y);CGContextAddLineToPoint(context,point.x,point.y);CGContextStrokePath(context);SkyDrawLabel(reference,point,standFont,[UIColor colorWithWhite:.92 alpha:1],[UIColor colorWithWhite:.06 alpha:.78],[UIColor colorWithWhite:.55 alpha:.8],standScale);[standOccupied addObject:[NSValue valueWithCGRect:CGRectInset(box,-5/standScale,-5/standScale)]];}
    NSString *north=@"N";UIFont *northFont=[UIFont boldSystemFontOfSize:22];[[UIColor whiteColor]set];[north drawAtPoint:CGPointMake(self.bounds.size.width-52,28)withFont:northFont];CGContextSetStrokeColorWithColor(context,[UIColor whiteColor].CGColor);CGContextSetLineWidth(context,3);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-42,93);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-50,72);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-34,72);CGContextStrokePath(context);
}
- (void)configureForFitScale:(CGFloat)fitScale { if(fitScale>0&&fabs(fitScale-self.labelScale)>.001){self.labelScale=fitScale;[self setNeedsDisplay];} }
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance {
    NSDictionary *best=nil;CGFloat bestDistance=tolerance;
    for(NSDictionary *feature in self.features){NSArray *points=[feature objectForKey:@"points"];if(!points.count)continue;CGFloat distance=CGFLOAT_MAX;if(points.count==1){CGPoint target=[self mapPoint:[points objectAtIndex:0]];distance=hypot(point.x-target.x,point.y-target.y);}else for(NSUInteger index=1;index<points.count;index++)distance=MIN(distance,SkyDistanceToSegment(point,[self mapPoint:[points objectAtIndex:index-1]],[self mapPoint:[points objectAtIndex:index]]));if(distance<bestDistance){bestDistance=distance;best=feature;}}
    return best;
}
- (void)dealloc { [_mapData release];[_features release];[_backgroundFeatures release];[_taxiwayFeatures release];[_runwayRecords release];[_standFeatures release];[super dealloc]; }
@end

@interface AirportMapViewController ()
@property(nonatomic,retain) NSString *icao;
@property(nonatomic,retain) NSString *mapPath;
@property(nonatomic,retain) NSDictionary *mapData;
@property(nonatomic,retain) UIScrollView *scrollView;
@property(nonatomic,retain) AirportMapCanvas *canvas;
@property(nonatomic,retain) UILabel *attributionLabel;
@property(nonatomic,assign) CGSize lastLayoutSize;
@end

@implementation AirportMapViewController
@synthesize icao=_icao,mapPath=_mapPath,mapData=_mapData,scrollView=_scrollView,canvas=_canvas,attributionLabel=_attributionLabel,lastLayoutSize=_lastLayoutSize;

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
    UITapGestureRecognizer *tap=[[[UITapGestureRecognizer alloc]initWithTarget:self action:@selector(mapTapped:)]autorelease];tap.numberOfTapsRequired=1;[self.canvas addGestureRecognizer:tap];self.canvas.userInteractionEnabled=YES;
    self.attributionLabel=[[[UILabel alloc]initWithFrame:CGRectZero]autorelease];self.attributionLabel.backgroundColor=[UIColor colorWithRed:.04 green:.05 blue:.07 alpha:1];self.attributionLabel.textColor=[UIColor colorWithWhite:.76 alpha:1];self.attributionLabel.font=[UIFont boldSystemFontOfSize:11];self.attributionLabel.textAlignment=NSTextAlignmentCenter;NSDictionary *counts=[self.mapData objectForKey:@"counts"];self.attributionLabel.text=[NSString stringWithFormat:@"Offline vector map • %d runways • %d taxiways • %d stands • © OpenStreetMap contributors",[[counts objectForKey:@"runway"]intValue],[[counts objectForKey:@"taxiway"]intValue]+[[counts objectForKey:@"taxilane"]intValue],[[counts objectForKey:@"parking_position"]intValue]];[self.view addSubview:self.attributionLabel];
}
- (void)viewWillLayoutSubviews { [super viewWillLayoutSubviews];CGSize size=self.view.bounds.size;self.scrollView.frame=CGRectMake(0,0,size.width,size.height-28);self.attributionLabel.frame=CGRectMake(0,size.height-28,size.width,28);if(!CGSizeEqualToSize(self.lastLayoutSize,size)){self.lastLayoutSize=size;[self performSelector:@selector(fitMap)withObject:nil afterDelay:0];} }
- (void)done { [self dismissModalViewControllerAnimated:YES]; }
- (UIView *)viewForZoomingInScrollView:(UIScrollView *)scrollView { return self.canvas; }
- (void)centerMap { CGSize bounds=self.scrollView.bounds.size,content=self.scrollView.contentSize;CGFloat horizontal=MAX(0,(bounds.width-content.width)/2),vertical=MAX(0,(bounds.height-content.height)/2);self.scrollView.contentInset=UIEdgeInsetsMake(vertical,horizontal,vertical,horizontal); }
- (void)scrollViewDidZoom:(UIScrollView *)scrollView { [self centerMap]; }
- (void)fitMap { if(!self.canvas)return;CGSize bounds=self.scrollView.bounds.size,content=self.canvas.bounds.size;if(bounds.width<=0||bounds.height<=0)return;CGFloat scale=MIN(bounds.width/content.width,bounds.height/content.height)*.96;self.scrollView.minimumZoomScale=scale;self.scrollView.maximumZoomScale=MAX(5,scale*6);[self.canvas configureForFitScale:scale];self.scrollView.zoomScale=scale;self.scrollView.contentOffset=CGPointZero;[self centerMap]; }
- (NSString *)displayNameForKind:(NSString *)kind { NSDictionary *names=[NSDictionary dictionaryWithObjectsAndKeys:@"Runway",@"runway",@"Taxiway",@"taxiway",@"Taxilane",@"taxilane",@"Apron",@"apron",@"Parking Stand",@"parking_position",@"Gate",@"gate",@"Holding Position",@"holding_position",@"Terminal",@"terminal",@"Hangar",@"hangar",nil];return [names objectForKey:kind]?:[kind capitalizedString]; }
- (void)mapTapped:(UITapGestureRecognizer *)gesture { if(gesture.state!=UIGestureRecognizerStateRecognized)return;CGPoint point=[gesture locationInView:self.canvas];CGFloat tolerance=MAX(12,28/MAX(.01,self.scrollView.zoomScale));NSDictionary *feature=[self.canvas featureAtPoint:point tolerance:tolerance];if(!feature)return;NSString *kind=[self displayNameForKind:[feature objectForKey:@"kind"]],*reference=[feature objectForKey:@"ref"],*name=[feature objectForKey:@"name"],*surface=[feature objectForKey:@"surface"];NSMutableArray *details=[NSMutableArray array];if(reference.length)[details addObject:[@"Reference: "stringByAppendingString:reference]];if(name.length&&![name isEqual:reference])[details addObject:name];if(surface.length)[details addObject:[@"Surface: "stringByAppendingString:surface]];UIAlertView *alert=[[[UIAlertView alloc]initWithTitle:kind message:details.count?[details componentsJoinedByString:@"\n"]:@"No additional information is available for this map feature." delegate:nil cancelButtonTitle:@"Done" otherButtonTitles:nil]autorelease];[alert show]; }
- (BOOL)shouldAutorotateToInterfaceOrientation:(UIInterfaceOrientation)orientation { return YES; }
- (void)dealloc { [_icao release];[_mapPath release];[_mapData release];[_scrollView release];[_canvas release];[_attributionLabel release];[super dealloc]; }
@end
