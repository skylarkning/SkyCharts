#import "AirportMapViewController.h"
#import <QuartzCore/QuartzCore.h>

static CGFloat SkyDistanceToSegment(CGPoint point, CGPoint start, CGPoint end) {
    CGFloat dx=end.x-start.x,dy=end.y-start.y,length=dx*dx+dy*dy;
    if(length<=.001)return hypot(point.x-start.x,point.y-start.y);
    CGFloat value=((point.x-start.x)*dx+(point.y-start.y)*dy)/length;value=MAX(0,MIN(1,value));
    CGPoint nearest=CGPointMake(start.x+value*dx,start.y+value*dy);
    return hypot(point.x-nearest.x,point.y-nearest.y);
}

@interface AirportMapCanvas : UIView
@property(nonatomic,retain) NSDictionary *mapData;
@property(nonatomic,retain) NSArray *features;
- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size;
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance;
@end

@implementation AirportMapCanvas
@synthesize mapData=_mapData,features=_features;

- (id)initWithMapData:(NSDictionary *)mapData size:(CGSize)size {
    if((self=[super initWithFrame:CGRectMake(0,0,size.width,size.height)])){
        self.opaque=YES;self.backgroundColor=[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1];self.mapData=mapData;self.features=[mapData objectForKey:@"features"]?:[NSArray array];
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
- (void)drawLabel:(NSString *)text point:(CGPoint)point color:(UIColor *)color font:(UIFont *)font {
    if(!text.length)return;CGSize size=[text sizeWithFont:font];CGRect box=CGRectMake(point.x-size.width/2-3,point.y-size.height/2-1,size.width+6,size.height+2);[[UIColor colorWithWhite:.03 alpha:.82]setFill];UIBezierPath *background=[UIBezierPath bezierPathWithRoundedRect:box cornerRadius:2];[background fill];[color set];[text drawAtPoint:CGPointMake(box.origin.x+3,box.origin.y+1)withFont:font];
}
- (CGPoint)middlePointForFeature:(NSDictionary *)feature {
    NSArray *points=[feature objectForKey:@"points"];if(!points.count)return CGPointZero;return [self mapPoint:[points objectAtIndex:points.count/2]];
}
- (void)drawRect:(CGRect)rect {
    CGContextRef context=UIGraphicsGetCurrentContext();CGContextSetAllowsAntialiasing(context,YES);CGContextSetShouldAntialias(context,YES);CGContextSetLineCap(context,kCGLineCapRound);CGContextSetLineJoin(context,kCGLineJoinRound);
    [[UIColor colorWithRed:.075 green:.095 blue:.12 alpha:1]setFill];CGContextFillRect(context,self.bounds);
    for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];UIColor *fill=[self fillForKind:kind];if(!fill)continue;UIBezierPath *path=[self pathForFeature:feature];[fill setFill];[path fill];[[UIColor colorWithWhite:.48 alpha:.55]setStroke];path.lineWidth=2;[path stroke];}
    for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];if(![kind isEqual:@"runway"])continue;UIBezierPath *path=[self pathForFeature:feature];[[UIColor colorWithWhite:.80 alpha:1]setStroke];path.lineWidth=50;[path stroke];[[UIColor colorWithWhite:.10 alpha:1]setStroke];path.lineWidth=44;[path stroke];CGFloat dash[]={24,16};CGContextSaveGState(context);CGContextSetLineDash(context,0,dash,2);[[UIColor whiteColor]setStroke];path.lineWidth=3;[path stroke];CGContextRestoreGState(context);}
    for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];if(!([kind isEqual:@"taxiway"]||[kind isEqual:@"taxilane"]))continue;UIBezierPath *path=[self pathForFeature:feature];[[UIColor colorWithWhite:.40 alpha:1]setStroke];path.lineWidth=[kind isEqual:@"taxilane"]?10:18;[path stroke];[[UIColor colorWithRed:1 green:.79 blue:.03 alpha:1]setStroke];path.lineWidth=2;[path stroke];}
    for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"];if(![kind isEqual:@"parking_position"])continue;NSArray *points=[feature objectForKey:@"points"];UIBezierPath *path=[self pathForFeature:feature];[[UIColor colorWithRed:.15 green:.86 blue:.70 alpha:1]setStroke];path.lineWidth=3;[path stroke];CGPoint point=[self mapPoint:[points lastObject]];[[UIColor colorWithRed:.15 green:.86 blue:.70 alpha:1]setFill];CGContextFillEllipseInRect(context,CGRectMake(point.x-4,point.y-4,8,8));}
    NSMutableSet *labeledTaxiways=[NSMutableSet set];for(NSDictionary *feature in self.features){NSString *kind=[feature objectForKey:@"kind"],*reference=[feature objectForKey:@"ref"]?:[feature objectForKey:@"name"];
        if([kind isEqual:@"runway"]){NSArray *points=[feature objectForKey:@"points"];if(points.count){[self drawLabel:reference point:[self mapPoint:[points objectAtIndex:0]]color:[UIColor whiteColor]font:[UIFont boldSystemFontOfSize:15]];[self drawLabel:reference point:[self mapPoint:[points lastObject]]color:[UIColor whiteColor]font:[UIFont boldSystemFontOfSize:15]];}}
        else if(([kind isEqual:@"taxiway"]||[kind isEqual:@"taxilane"])&&reference.length<=8&&![labeledTaxiways containsObject:reference]){[labeledTaxiways addObject:reference];[self drawLabel:reference point:[self middlePointForFeature:feature]color:[UIColor colorWithRed:1 green:.86 blue:.08 alpha:1]font:[UIFont boldSystemFontOfSize:12]];}
        else if([kind isEqual:@"parking_position"]||[kind isEqual:@"gate"])[self drawLabel:reference point:[self middlePointForFeature:feature]color:[UIColor colorWithRed:.60 green:1 blue:.90 alpha:1]font:[UIFont boldSystemFontOfSize:10]];
        else if([kind isEqual:@"terminal"]&&reference.length)[self drawLabel:reference point:[self middlePointForFeature:feature]color:[UIColor whiteColor]font:[UIFont boldSystemFontOfSize:14]];
    }
    NSString *north=@"N";UIFont *northFont=[UIFont boldSystemFontOfSize:22];[[UIColor whiteColor]set];[north drawAtPoint:CGPointMake(self.bounds.size.width-52,28)withFont:northFont];CGContextSetStrokeColorWithColor(context,[UIColor whiteColor].CGColor);CGContextSetLineWidth(context,3);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-42,93);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-50,72);CGContextMoveToPoint(context,self.bounds.size.width-42,58);CGContextAddLineToPoint(context,self.bounds.size.width-34,72);CGContextStrokePath(context);
}
- (NSDictionary *)featureAtPoint:(CGPoint)point tolerance:(CGFloat)tolerance {
    NSDictionary *best=nil;CGFloat bestDistance=tolerance;
    for(NSDictionary *feature in self.features){NSArray *points=[feature objectForKey:@"points"];if(!points.count)continue;CGFloat distance=CGFLOAT_MAX;if(points.count==1){CGPoint target=[self mapPoint:[points objectAtIndex:0]];distance=hypot(point.x-target.x,point.y-target.y);}else for(NSUInteger index=1;index<points.count;index++)distance=MIN(distance,SkyDistanceToSegment(point,[self mapPoint:[points objectAtIndex:index-1]],[self mapPoint:[points objectAtIndex:index]]));if(distance<bestDistance){bestDistance=distance;best=feature;}}
    return best;
}
- (void)dealloc { [_mapData release];[_features release];[super dealloc]; }
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
- (void)fitMap { if(!self.canvas)return;CGSize bounds=self.scrollView.bounds.size,content=self.canvas.bounds.size;if(bounds.width<=0||bounds.height<=0)return;CGFloat scale=MIN(bounds.width/content.width,bounds.height/content.height)*.96;self.scrollView.minimumZoomScale=scale;self.scrollView.maximumZoomScale=MAX(5,scale*6);self.scrollView.zoomScale=scale;self.scrollView.contentOffset=CGPointZero;[self centerMap]; }
- (NSString *)displayNameForKind:(NSString *)kind { NSDictionary *names=[NSDictionary dictionaryWithObjectsAndKeys:@"Runway",@"runway",@"Taxiway",@"taxiway",@"Taxilane",@"taxilane",@"Apron",@"apron",@"Parking Stand",@"parking_position",@"Gate",@"gate",@"Holding Position",@"holding_position",@"Terminal",@"terminal",@"Hangar",@"hangar",nil];return [names objectForKey:kind]?:[kind capitalizedString]; }
- (void)mapTapped:(UITapGestureRecognizer *)gesture { if(gesture.state!=UIGestureRecognizerStateRecognized)return;CGPoint point=[gesture locationInView:self.canvas];CGFloat tolerance=MAX(12,28/MAX(.01,self.scrollView.zoomScale));NSDictionary *feature=[self.canvas featureAtPoint:point tolerance:tolerance];if(!feature)return;NSString *kind=[self displayNameForKind:[feature objectForKey:@"kind"]],*reference=[feature objectForKey:@"ref"],*name=[feature objectForKey:@"name"],*surface=[feature objectForKey:@"surface"];NSMutableArray *details=[NSMutableArray array];if(reference.length)[details addObject:[@"Reference: "stringByAppendingString:reference]];if(name.length&&![name isEqual:reference])[details addObject:name];if(surface.length)[details addObject:[@"Surface: "stringByAppendingString:surface]];UIAlertView *alert=[[[UIAlertView alloc]initWithTitle:kind message:details.count?[details componentsJoinedByString:@"\n"]:@"No additional information is available for this map feature." delegate:nil cancelButtonTitle:@"Done" otherButtonTitles:nil]autorelease];[alert show]; }
- (BOOL)shouldAutorotateToInterfaceOrientation:(UIInterfaceOrientation)orientation { return YES; }
- (void)dealloc { [_icao release];[_mapPath release];[_mapData release];[_scrollView release];[_canvas release];[_attributionLabel release];[super dealloc]; }
@end
