#import "AboutViewController.h"
#import <QuartzCore/QuartzCore.h>

@interface AboutViewController ()
- (UILabel *)label:(CGRect)frame text:(NSString *)text font:(UIFont *)font color:(UIColor *)color;
@end

@implementation AboutViewController
- (void)viewDidLoad {
    [super viewDidLoad];self.title=@"About SkyCharts";self.view.backgroundColor=[UIColor colorWithRed:.82 green:.84 blue:.87 alpha:1];self.navigationItem.rightBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)]autorelease];
    UIImageView *logo=[[[UIImageView alloc]initWithImage:[UIImage imageNamed:@"Icon-72@2x.png"]]autorelease];logo.frame=CGRectMake(0,28,144,144);logo.center=CGPointMake(self.view.bounds.size.width/2,logo.center.y);logo.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;logo.layer.cornerRadius=24;logo.layer.shadowColor=[UIColor blackColor].CGColor;logo.layer.shadowOpacity=.45;logo.layer.shadowRadius=6;logo.layer.shadowOffset=CGSizeMake(0,3);[self.view addSubview:logo];
    UILabel *name=[self label:CGRectMake(24,188,self.view.bounds.size.width-48,38) text:@"SkyCharts" font:[UIFont boldSystemFontOfSize:30] color:[UIColor colorWithWhite:.12 alpha:1]];name.autoresizingMask=UIViewAutoresizingFlexibleWidth;[self.view addSubview:name];
    NSString *version=[[NSBundle mainBundle]objectForInfoDictionaryKey:@"CFBundleShortVersionString"]?:@"";NSString *build=[[NSBundle mainBundle]objectForInfoDictionaryKey:@"CFBundleVersion"]?:@"";
    UILabel *details=[self label:CGRectMake(38,232,self.view.bounds.size.width-76,180) text:[NSString stringWithFormat:@"Offline aviation charts for legacy iPad\n\nVersion %@ (Build %@)\n\nDeveloped by Sky Ning\n© 2026 Sky Ning. All rights reserved.",version,build] font:[UIFont systemFontOfSize:17] color:[UIColor colorWithWhite:.20 alpha:1]];details.numberOfLines=0;details.autoresizingMask=UIViewAutoresizingFlexibleWidth;[self.view addSubview:details];
    UILabel *legal=[self label:CGRectMake(38,self.view.bounds.size.height-118,self.view.bounds.size.width-76,76) text:@"SkyCharts is an independent project and is not affiliated with or endorsed by Microsoft. Aviation charts are for flight simulation use only." font:[UIFont systemFontOfSize:12] color:[UIColor colorWithWhite:.35 alpha:1]];legal.numberOfLines=0;legal.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleTopMargin;[self.view addSubview:legal];
}
- (UILabel *)label:(CGRect)frame text:(NSString *)text font:(UIFont *)font color:(UIColor *)color { UILabel *label=[[[UILabel alloc]initWithFrame:frame]autorelease];label.backgroundColor=[UIColor clearColor];label.textAlignment=NSTextAlignmentCenter;label.text=text;label.font=font;label.textColor=color;label.shadowColor=[UIColor colorWithWhite:1 alpha:.75];label.shadowOffset=CGSizeMake(0,1);return label; }
- (void)done { [self dismissModalViewControllerAnimated:YES]; }
@end
