#import "ContentManagerViewController.h"

@interface ContentManagerViewController ()
@property(nonatomic, retain) UITableView *tableView;
@property(nonatomic, retain) NSArray *rootNodes;
@property(nonatomic, retain) NSArray *rows;
@property(nonatomic, retain) NSMutableSet *expandedKeys;
@end

@implementation ContentManagerViewController
@synthesize tableView=_tableView,rootNodes=_rootNodes,rows=_rows,expandedKeys=_expandedKeys;

- (void)viewDidLoad {
    [super viewDidLoad];self.title=@"Downloaded Content";
    self.navigationItem.rightBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)]autorelease];
    self.expandedKeys=[NSMutableSet set];
    self.tableView=[[[UITableView alloc]initWithFrame:self.view.bounds style:UITableViewStyleGrouped]autorelease];self.tableView.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;self.tableView.dataSource=self;self.tableView.delegate=self;[self.view addSubview:self.tableView];[self reloadContent];
}
- (void)done { [self dismissModalViewControllerAnimated:YES]; }

- (NSString *)continentForCountry:(NSString *)country {
    NSString *code=[country uppercaseString],*needle=[NSString stringWithFormat:@",%@,",code];
    NSString *asia=@",AF,AM,AZ,BH,BD,BT,BN,KH,CN,CY,GE,HK,IN,ID,IR,IQ,IL,JP,JO,KZ,KP,KR,KW,KG,LA,LB,MO,MY,MV,MN,MM,NP,OM,PK,PS,PH,QA,SA,SG,LK,SY,TW,TJ,TH,TL,TR,TM,AE,UZ,VN,YE,";
    NSString *europe=@",AD,AL,AT,AX,BA,BE,BG,BY,CH,CZ,DE,DK,EE,ES,FI,FO,FR,GB,GG,GI,GR,HR,HU,IE,IM,IS,IT,JE,LI,LT,LU,LV,MC,MD,ME,MK,MT,NL,NO,PL,PT,RO,RS,RU,SE,SI,SK,SM,UA,VA,";
    NSString *northAmerica=@",AG,AI,AW,BB,BL,BM,BQ,BS,BZ,CA,CR,CU,CW,DM,DO,GD,GL,GP,GT,HN,HT,JM,KN,KY,LC,MF,MQ,MS,MX,NI,PA,PM,PR,SV,SX,TC,TT,US,VC,VG,VI,";
    NSString *southAmerica=@",AR,BO,BR,CL,CO,EC,FK,GF,GY,PE,PY,SR,UY,VE,";
    NSString *oceania=@",AS,AU,CC,CK,CX,FJ,FM,GU,KI,MH,MP,NC,NF,NR,NU,NZ,PF,PG,PN,PW,SB,TK,TO,TV,UM,VU,WF,WS,";
    NSString *antarctica=@",AQ,BV,GS,HM,TF,";
    NSString *africa=@",AO,BF,BI,BJ,BW,CD,CF,CG,CI,CM,CV,DJ,DZ,EG,EH,ER,ET,GA,GH,GM,GN,GQ,GW,KE,KM,LR,LS,LY,MA,MG,ML,MR,MU,MW,MZ,NA,NE,NG,RE,RW,SC,SD,SH,SL,SN,SO,SS,ST,SZ,TD,TG,TN,TZ,UG,YT,ZA,ZM,ZW,";
    if([asia rangeOfString:needle].location!=NSNotFound)return @"Asia";if([europe rangeOfString:needle].location!=NSNotFound)return @"Europe";if([northAmerica rangeOfString:needle].location!=NSNotFound)return @"North America";if([southAmerica rangeOfString:needle].location!=NSNotFound)return @"South America";if([oceania rangeOfString:needle].location!=NSNotFound)return @"Oceania";if([antarctica rangeOfString:needle].location!=NSNotFound)return @"Antarctica";if([africa rangeOfString:needle].location!=NSNotFound)return @"Africa";return @"Other";
}
- (NSString *)countryName:(NSString *)country { NSLocale *locale=[[[NSLocale alloc]initWithLocaleIdentifier:@"en_US"]autorelease];return [locale displayNameForKey:NSLocaleCountryCode value:[country uppercaseString]]?:[country uppercaseString]; }
- (NSArray *)sortedKeys:(NSDictionary *)dictionary { return [[dictionary allKeys]sortedArrayUsingSelector:@selector(localizedCaseInsensitiveCompare:)]; }
- (NSDictionary *)node:(NSString *)title subtitle:(NSString *)subtitle key:(NSString *)key level:(NSInteger)level children:(NSArray *)children type:(NSString *)type path:(NSString *)path { NSMutableDictionary *node=[NSMutableDictionary dictionaryWithObjectsAndKeys:title?:@"Unknown",@"title",subtitle?:@"",@"subtitle",key?:@"",@"key",[NSNumber numberWithInteger:level],@"level",children?:[NSArray array],@"children",type?:@"group",@"type",nil];if(path)[node setObject:path forKey:@"path"];return node; }

- (void)reloadContent {
    NSString *root=@"/var/mobile/Library/SkyCharts/ChartPacks";NSFileManager *fm=[NSFileManager defaultManager];NSMutableDictionary *tree=[NSMutableDictionary dictionary];NSMutableArray *packages=[NSMutableArray array];
    NSArray *directories=[[fm contentsOfDirectoryAtPath:root error:NULL]sortedArrayUsingSelector:@selector(caseInsensitiveCompare:)];
    for(NSString *directory in directories){
        NSString *packPath=[root stringByAppendingPathComponent:directory];NSData *data=[NSData dataWithContentsOfFile:[packPath stringByAppendingPathComponent:@"pack.json"]];NSDictionary *manifest=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;if(!manifest)continue;
        NSArray *airports=[manifest objectForKey:@"airports"]?:[NSArray array];[packages addObject:[self node:[manifest objectForKey:@"name"]?:directory subtitle:[NSString stringWithFormat:@"%@ • %lu airports",[manifest objectForKey:@"country"]?:@"Custom",(unsigned long)airports.count]key:[@"pack:" stringByAppendingString:directory]level:1 children:nil type:@"pack" path:packPath]];
        for(NSDictionary *airport in airports){
            id countryValue=[airport objectForKey:@"country"]?:[manifest objectForKey:@"country"]?:@"ZZ";NSString *countryCode=[[countryValue description]uppercaseString],*continent=[airport objectForKey:@"continent"]?:[self continentForCountry:countryCode],*country=[airport objectForKey:@"countryName"]?:[self countryName:countryCode],*region=[airport objectForKey:@"regionName"]?:[airport objectForKey:@"region"]?:@"Unknown Region",*city=[airport objectForKey:@"city"]?:@"Unknown City",*ident=[airport objectForKey:@"ident"]?:@"Unknown";
            NSMutableDictionary *countries=[tree objectForKey:continent];if(!countries){countries=[NSMutableDictionary dictionary];[tree setObject:countries forKey:continent];}
            NSMutableDictionary *regions=[countries objectForKey:country];if(!regions){regions=[NSMutableDictionary dictionary];[countries setObject:regions forKey:country];}
            NSMutableDictionary *cities=[regions objectForKey:region];if(!cities){cities=[NSMutableDictionary dictionary];[regions setObject:cities forKey:region];}
            NSMutableSet *airportsInCity=[cities objectForKey:city];if(!airportsInCity){airportsInCity=[NSMutableSet set];[cities setObject:airportsInCity forKey:city];}[airportsInCity addObject:ident];
        }
    }
    NSMutableArray *roots=[NSMutableArray array];
    for(NSString *continent in [self sortedKeys:tree]){NSMutableDictionary *countries=[tree objectForKey:continent];NSMutableArray *countryNodes=[NSMutableArray array];
        for(NSString *country in [self sortedKeys:countries]){NSMutableDictionary *regions=[countries objectForKey:country];NSMutableArray *regionNodes=[NSMutableArray array];
            for(NSString *region in [self sortedKeys:regions]){NSMutableDictionary *cities=[regions objectForKey:region];NSMutableArray *cityNodes=[NSMutableArray array];
                for(NSString *city in [self sortedKeys:cities]){NSUInteger count=[[cities objectForKey:city]count];NSString *key=[NSString stringWithFormat:@"%@/%@/%@/%@",continent,country,region,city];[cityNodes addObject:[self node:city subtitle:[NSString stringWithFormat:@"%lu airport%@",(unsigned long)count,count==1?@"":@"s"]key:key level:3 children:nil type:@"city" path:nil]];}
                NSString *key=[NSString stringWithFormat:@"%@/%@/%@",continent,country,region];[regionNodes addObject:[self node:region subtitle:[NSString stringWithFormat:@"%lu cit%@",(unsigned long)cityNodes.count,cityNodes.count==1?@"y":@"ies"]key:key level:2 children:cityNodes type:@"group" path:nil]];}
            NSString *key=[NSString stringWithFormat:@"%@/%@",continent,country];[countryNodes addObject:[self node:country subtitle:[NSString stringWithFormat:@"%lu region%@",(unsigned long)regionNodes.count,regionNodes.count==1?@"":@"s"]key:key level:1 children:regionNodes type:@"group" path:nil]];}
        [roots addObject:[self node:continent subtitle:[NSString stringWithFormat:@"%lu countr%@",(unsigned long)countryNodes.count,countryNodes.count==1?@"y":@"ies"]key:continent level:0 children:countryNodes type:@"group" path:nil]];
    }
    if(packages.count)[roots addObject:[self node:@"Installed Packages" subtitle:[NSString stringWithFormat:@"%lu package%@ • swipe a package to delete",(unsigned long)packages.count,packages.count==1?@"":@"s"]key:@"installed-packages" level:0 children:packages type:@"group" path:nil]];
    self.rootNodes=roots;[self rebuildRows];
}
- (void)appendNode:(NSDictionary *)node toRows:(NSMutableArray *)rows { [rows addObject:node];NSArray *children=[node objectForKey:@"children"];if(children.count&&[self.expandedKeys containsObject:[node objectForKey:@"key"]])for(NSDictionary *child in children)[self appendNode:child toRows:rows]; }
- (void)rebuildRows { NSMutableArray *visible=[NSMutableArray array];for(NSDictionary *node in self.rootNodes)[self appendNode:node toRows:visible];self.rows=visible;[self.tableView reloadData]; }

- (NSInteger)numberOfSectionsInTableView:(UITableView *)table { return 1; }
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section { return self.rows.count; }
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    UITableViewCell *cell=[table dequeueReusableCellWithIdentifier:@"content"];if(!cell)cell=[[[UITableViewCell alloc]initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:@"content"]autorelease];NSDictionary *row=[self.rows objectAtIndex:path.row];NSInteger level=[[row objectForKey:@"level"]integerValue];NSArray *children=[row objectForKey:@"children"];
    cell.indentationLevel=level;cell.indentationWidth=20;cell.textLabel.text=[row objectForKey:@"title"];cell.detailTextLabel.text=[row objectForKey:@"subtitle"];cell.textLabel.font=[UIFont fontWithName:level==0?@"Helvetica-Bold":@"Helvetica" size:level==0?18:16];cell.selectionStyle=children.count?UITableViewCellSelectionStyleBlue:UITableViewCellSelectionStyleNone;
    if(children.count){UILabel *arrow=[[[UILabel alloc]initWithFrame:CGRectMake(0,0,24,30)]autorelease];arrow.backgroundColor=[UIColor clearColor];arrow.textAlignment=NSTextAlignmentCenter;arrow.font=[UIFont boldSystemFontOfSize:18];arrow.textColor=[UIColor grayColor];arrow.text=[self.expandedKeys containsObject:[row objectForKey:@"key"]]?@"▾":@"▸";cell.accessoryView=arrow;}else cell.accessoryView=nil;
    return cell;
}
- (void)tableView:(UITableView *)table didSelectRowAtIndexPath:(NSIndexPath *)path { NSDictionary *row=[self.rows objectAtIndex:path.row];if([[row objectForKey:@"children"]count]){NSString *key=[row objectForKey:@"key"];if([self.expandedKeys containsObject:key])[self.expandedKeys removeObject:key];else[self.expandedKeys addObject:key];[self rebuildRows];}[table deselectRowAtIndexPath:path animated:YES]; }
- (BOOL)tableView:(UITableView *)table canEditRowAtIndexPath:(NSIndexPath *)path { return [[[self.rows objectAtIndex:path.row]objectForKey:@"type"]isEqual:@"pack"]; }
- (UITableViewCellEditingStyle)tableView:(UITableView *)table editingStyleForRowAtIndexPath:(NSIndexPath *)path { return UITableViewCellEditingStyleDelete; }
- (NSString *)tableView:(UITableView *)table titleForDeleteConfirmationButtonForRowAtIndexPath:(NSIndexPath *)path { return @"Delete Pack"; }
- (void)tableView:(UITableView *)table commitEditingStyle:(UITableViewCellEditingStyle)style forRowAtIndexPath:(NSIndexPath *)path { if(style!=UITableViewCellEditingStyleDelete)return;NSDictionary *row=[self.rows objectAtIndex:path.row];NSString *packPath=[[row objectForKey:@"path"]copy];self.tableView.userInteractionEnabled=NO;self.navigationItem.prompt=@"Deleting chart package…";[self performSelectorInBackground:@selector(deletePackBackground:)withObject:[packPath autorelease]]; }
- (void)deletePackBackground:(NSString *)packPath { NSAutoreleasePool *pool=[[NSAutoreleasePool alloc]init];[[NSFileManager defaultManager]removeItemAtPath:packPath error:NULL];[self performSelectorOnMainThread:@selector(deletePackFinished)withObject:nil waitUntilDone:NO];[pool drain]; }
- (void)deletePackFinished { self.navigationItem.prompt=nil;self.tableView.userInteractionEnabled=YES;[self performSelector:@selector(reloadContent)withObject:nil afterDelay:0]; }
- (void)dealloc { [_tableView release];[_rootNodes release];[_rows release];[_expandedKeys release];[super dealloc]; }
@end
