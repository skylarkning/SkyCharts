#import "WeatherViewController.h"
#import <QuartzCore/QuartzCore.h>

@interface WeatherViewController ()
@property(nonatomic, retain) NSString *icao;
@property(nonatomic, retain) UISegmentedControl *modeControl;
@property(nonatomic, retain) UITextView *textView;
@property(nonatomic, retain) UIActivityIndicatorView *spinner;
@property(nonatomic, retain) UILabel *statusLabel;
@end

@implementation WeatherViewController
@synthesize icao=_icao,modeControl=_modeControl,textView=_textView,spinner=_spinner,statusLabel=_statusLabel;

- (id)initWithICAO:(NSString *)icao { if((self=[super init]))self.icao=[icao uppercaseString];return self; }
- (void)viewDidLoad {
    [super viewDidLoad];self.title=[NSString stringWithFormat:@"%@ Weather",self.icao];self.view.backgroundColor=[UIColor colorWithWhite:.88 alpha:1];
    self.navigationItem.leftBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)]autorelease];self.navigationItem.rightBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemRefresh target:self action:@selector(refresh)]autorelease];
    self.modeControl=[[[UISegmentedControl alloc]initWithItems:[NSArray arrayWithObjects:@"Raw",@"Decoded",nil]]autorelease];self.modeControl.segmentedControlStyle=UISegmentedControlStyleBar;self.modeControl.selectedSegmentIndex=1;[self.modeControl addTarget:self action:@selector(modeChanged) forControlEvents:UIControlEventValueChanged];[self.view addSubview:self.modeControl];
    self.textView=[[[UITextView alloc]initWithFrame:CGRectZero]autorelease];self.textView.editable=NO;self.textView.font=[UIFont systemFontOfSize:17];self.textView.textColor=[UIColor colorWithWhite:.16 alpha:1];self.textView.backgroundColor=[UIColor whiteColor];self.textView.layer.cornerRadius=7;[self.view addSubview:self.textView];
    self.statusLabel=[[[UILabel alloc]initWithFrame:CGRectZero]autorelease];self.statusLabel.backgroundColor=[UIColor clearColor];self.statusLabel.textColor=[UIColor grayColor];self.statusLabel.font=[UIFont boldSystemFontOfSize:12];[self.view addSubview:self.statusLabel];
    self.spinner=[[[UIActivityIndicatorView alloc]initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleGray]autorelease];[self.view addSubview:self.spinner];[self refresh];
}
- (void)viewWillLayoutSubviews { [super viewWillLayoutSubviews];CGFloat width=self.view.bounds.size.width,height=self.view.bounds.size.height;self.modeControl.frame=CGRectMake(18,14,width-36,34);self.textView.frame=CGRectMake(18,60,width-36,height-100);self.statusLabel.frame=CGRectMake(20,height-34,width-66,24);self.spinner.center=CGPointMake(width-30,height-22); }
- (void)done { [self dismissModalViewControllerAnimated:YES]; }
- (void)modeChanged { [self refresh]; }
- (void)refresh { self.textView.text=@"";self.statusLabel.text=@"Fetching latest METAR…";[self.spinner startAnimating];NSString *kind=self.modeControl.selectedSegmentIndex==0?@"stations":@"decoded";NSString *url=[NSString stringWithFormat:@"ftp://tgftp.nws.noaa.gov/data/observations/metar/%@/%@.TXT",kind,self.icao];[self performSelectorInBackground:@selector(fetchBackground:)withObject:url]; }
- (void)fetchBackground:(NSString *)url { NSAutoreleasePool *pool=[[NSAutoreleasePool alloc]init];NSData *data=[NSData dataWithContentsOfURL:[NSURL URLWithString:url]];NSString *text=data?[[[NSString alloc]initWithData:data encoding:NSUTF8StringEncoding]autorelease]:nil;NSDictionary *result=[NSDictionary dictionaryWithObjectsAndKeys:text?:@"",@"text",url,@"url",nil];[self performSelectorOnMainThread:@selector(fetchFinished:)withObject:result waitUntilDone:NO];[pool drain]; }
- (void)fetchFinished:(NSDictionary *)result { [self.spinner stopAnimating];NSString *text=[result objectForKey:@"text"];if(text.length){self.textView.text=text;self.statusLabel.text=@"Latest NWS observation • tap refresh to update";}else{self.textView.text=@"No METAR was returned for this airport. The station may not report METAR weather, or the iPad may be offline.";self.statusLabel.text=@"Weather unavailable";} }
- (void)dealloc { [_icao release];[_modeControl release];[_textView release];[_spinner release];[_statusLabel release];[super dealloc]; }
@end
