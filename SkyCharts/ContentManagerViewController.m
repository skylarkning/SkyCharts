#import "ContentManagerViewController.h"

@interface ContentManagerViewController ()
@property(nonatomic, retain) UITableView *tableView;
@property(nonatomic, retain) UILabel *storageLabel;
@property(nonatomic, retain) NSArray *rootNodes;
@property(nonatomic, retain) NSArray *rows;
@property(nonatomic, retain) NSMutableSet *expandedKeys;
@end

@implementation ContentManagerViewController
@synthesize tableView=_tableView,storageLabel=_storageLabel,rootNodes=_rootNodes,rows=_rows,expandedKeys=_expandedKeys;

- (void)viewDidLoad {
    [super viewDidLoad];self.title=@"Downloaded Content";
    self.navigationItem.rightBarButtonItem=[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)]autorelease];
    self.expandedKeys=[NSMutableSet set];
    self.tableView=[[[UITableView alloc]initWithFrame:self.view.bounds style:UITableViewStyleGrouped]autorelease];self.tableView.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;self.tableView.dataSource=self;self.tableView.delegate=self;UIView *summary=[[[UIView alloc]initWithFrame:CGRectMake(0,0,self.view.bounds.size.width,62)]autorelease];summary.autoresizingMask=UIViewAutoresizingFlexibleWidth;self.storageLabel=[[[UILabel alloc]initWithFrame:CGRectMake(18,7,summary.bounds.size.width-36,48)]autorelease];self.storageLabel.autoresizingMask=UIViewAutoresizingFlexibleWidth;self.storageLabel.backgroundColor=[UIColor clearColor];self.storageLabel.numberOfLines=2;self.storageLabel.textAlignment=NSTextAlignmentCenter;self.storageLabel.font=[UIFont boldSystemFontOfSize:14];self.storageLabel.textColor=[UIColor colorWithWhite:.28 alpha:1];self.storageLabel.shadowColor=[UIColor whiteColor];self.storageLabel.shadowOffset=CGSizeMake(0,1);[summary addSubview:self.storageLabel];self.tableView.tableHeaderView=summary;[self.view addSubview:self.tableView];[self reloadContent];
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
- (NSString *)formattedBytes:(unsigned long long)bytes { double value=(double)bytes;NSArray *units=[NSArray arrayWithObjects:@"bytes",@"KB",@"MB",@"GB",@"TB",nil];NSUInteger unit=0;while(value>=1024&&unit+1<units.count){value/=1024;unit++;}if(unit==0)return [NSString stringWithFormat:@"%llu bytes",bytes];return [NSString stringWithFormat:value>=100?@"%.0f %@":value>=10?@"%.1f %@":@"%.2f %@",value,[units objectAtIndex:unit]]; }
- (unsigned long long)sizeOfFiles:(NSSet *)files sizes:(NSDictionary *)sizes { unsigned long long total=0;for(NSString *path in files)total+=[[sizes objectForKey:path]unsignedLongLongValue];return total; }
- (NSDictionary *)node:(NSString *)title subtitle:(NSString *)subtitle key:(NSString *)key level:(NSInteger)level children:(NSArray *)children kind:(NSString *)kind targets:(NSArray *)targets files:(NSSet *)files sizes:(NSDictionary *)sizes { unsigned long long bytes=[self sizeOfFiles:files sizes:sizes];NSString *detail=subtitle.length?[NSString stringWithFormat:@"%@ • %@",subtitle,[self formattedBytes:bytes]]:[self formattedBytes:bytes];return [NSDictionary dictionaryWithObjectsAndKeys:title?:@"Unknown",@"title",detail,@"subtitle",key?:@"",@"key",[NSNumber numberWithInteger:level],@"level",children?:[NSArray array],@"children",kind?:@"group",@"kind",targets?:[NSArray array],@"targets",[files allObjects]?:[NSArray array],@"files",[NSNumber numberWithUnsignedLongLong:bytes],@"bytes",nil]; }
- (void)addTargetsFromNodes:(NSArray *)nodes toArray:(NSMutableArray *)targets { for(NSDictionary *node in nodes)[targets addObjectsFromArray:[node objectForKey:@"targets"]]; }
- (void)addFilesFromNodes:(NSArray *)nodes toSet:(NSMutableSet *)files { for(NSDictionary *node in nodes)[files addObjectsFromArray:[node objectForKey:@"files"]]; }

- (void)reloadContent {
    NSString *root=@"/var/mobile/Library/SkyCharts/ChartPacks",*mapRoot=@"/var/mobile/Library/SkyCharts/AirportMaps";NSFileManager *fm=[NSFileManager defaultManager];NSMutableDictionary *tree=[NSMutableDictionary dictionary],*fileSizes=[NSMutableDictionary dictionary];unsigned long long totalUsed=0;for(NSString *storageRoot in [NSArray arrayWithObjects:root,mapRoot,nil]){NSDirectoryEnumerator *enumerator=[fm enumeratorAtPath:storageRoot];NSString *relativePath=nil;while((relativePath=[enumerator nextObject])){NSDictionary *attributes=[enumerator fileAttributes];if([[attributes objectForKey:NSFileType]isEqual:NSFileTypeRegular]){unsigned long long bytes=[[attributes objectForKey:NSFileSize]unsignedLongLongValue];NSString *absolute=[storageRoot stringByAppendingPathComponent:relativePath];[fileSizes setObject:[NSNumber numberWithUnsignedLongLong:bytes]forKey:absolute];totalUsed+=bytes;}}}NSDictionary *fileSystem=[fm attributesOfFileSystemForPath:root error:NULL];unsigned long long available=[[fileSystem objectForKey:NSFileSystemFreeSize]unsignedLongLongValue];self.storageLabel.text=[NSString stringWithFormat:@"Total SkyCharts storage: %@\nAvailable on iPad: %@",[self formattedBytes:totalUsed],[self formattedBytes:available]];
    NSArray *directories=[[fm contentsOfDirectoryAtPath:root error:NULL]sortedArrayUsingSelector:@selector(caseInsensitiveCompare:)];
    for(NSString *directory in directories){
        NSString *packPath=[root stringByAppendingPathComponent:directory];NSData *data=[NSData dataWithContentsOfFile:[packPath stringByAppendingPathComponent:@"pack.json"]];NSDictionary *manifest=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;if(!manifest)continue;
        for(NSDictionary *airport in [manifest objectForKey:@"airports"]?:[NSArray array]){
            id countryValue=[airport objectForKey:@"country"]?:[manifest objectForKey:@"country"]?:@"ZZ";NSString *countryCode=[[countryValue description]uppercaseString];
            NSString *continent=[airport objectForKey:@"continent"]?:[self continentForCountry:countryCode];
            NSString *countryName=[airport objectForKey:@"countryName"]?:[self countryName:countryCode];NSString *country=[NSString stringWithFormat:@"%@ (%@)",countryName,countryCode];
            id regionValue=[airport objectForKey:@"region"]?:@"";NSString *regionCode=[[regionValue description]uppercaseString],*regionName=[airport objectForKey:@"regionName"]?:regionCode;if(!regionName.length)regionName=@"Unknown Region";NSString *region=regionCode.length?[NSString stringWithFormat:@"%@ (%@)",regionName,regionCode]:regionName;
            id identValue=[airport objectForKey:@"ident"]?:@"Unknown";NSString *city=[airport objectForKey:@"city"]?:@"Unknown City",*ident=[[identValue description]uppercaseString],*airportName=[airport objectForKey:@"name"]?:ident;
            NSMutableDictionary *countries=[tree objectForKey:continent];if(!countries){countries=[NSMutableDictionary dictionary];[tree setObject:countries forKey:continent];}
            NSMutableDictionary *regions=[countries objectForKey:country];if(!regions){regions=[NSMutableDictionary dictionary];[countries setObject:regions forKey:country];}
            NSMutableDictionary *cities=[regions objectForKey:region];if(!cities){cities=[NSMutableDictionary dictionary];[regions setObject:cities forKey:region];}
            NSMutableDictionary *airports=[cities objectForKey:city];if(!airports){airports=[NSMutableDictionary dictionary];[cities setObject:airports forKey:city];}
            NSMutableDictionary *record=[airports objectForKey:ident];if(!record){record=[NSMutableDictionary dictionaryWithObjectsAndKeys:airportName,@"name",[NSMutableArray array],@"targets",[NSMutableSet set],@"files",nil];[airports setObject:record forKey:ident];}
            NSMutableArray *targets=[record objectForKey:@"targets"];BOOL duplicate=NO;for(NSDictionary *target in targets)if([[target objectForKey:@"path"]isEqual:packPath]){duplicate=YES;break;}if(!duplicate)[targets addObject:[NSDictionary dictionaryWithObjectsAndKeys:packPath,@"path",ident,@"ident",nil]];
            NSMutableSet *files=[record objectForKey:@"files"];for(NSDictionary *category in [airport objectForKey:@"categories"])for(NSDictionary *chart in [category objectForKey:@"charts"])for(NSDictionary *page in [chart objectForKey:@"pages"]){NSString *asset=[page objectForKey:@"light"];if(asset.length)[files addObject:[packPath stringByAppendingPathComponent:asset]];}NSString *bundledMap=[airport objectForKey:@"map"];if(bundledMap.length)[files addObject:[packPath stringByAppendingPathComponent:bundledMap]];NSString *mapPath=[mapRoot stringByAppendingPathComponent:[ident stringByAppendingString:@".json"]];if([fm fileExistsAtPath:mapPath])[files addObject:mapPath];
        }
    }
    NSMutableArray *roots=[NSMutableArray array];
    for(NSString *continent in [self sortedKeys:tree]){
        NSMutableDictionary *countries=[tree objectForKey:continent];NSMutableArray *countryNodes=[NSMutableArray array];
        for(NSString *country in [self sortedKeys:countries]){
            NSMutableDictionary *regions=[countries objectForKey:country];NSMutableArray *regionNodes=[NSMutableArray array];
            for(NSString *region in [self sortedKeys:regions]){
                NSMutableDictionary *cities=[regions objectForKey:region];NSMutableArray *cityNodes=[NSMutableArray array];
                for(NSString *city in [self sortedKeys:cities]){
                    NSMutableDictionary *airports=[cities objectForKey:city];NSMutableArray *airportNodes=[NSMutableArray array];
                    for(NSString *ident in [self sortedKeys:airports]){NSDictionary *record=[airports objectForKey:ident];NSString *name=[record objectForKey:@"name"],*title=name.length&&![name isEqual:ident]?[NSString stringWithFormat:@"%@ / %@",ident,name]:ident,*key=[NSString stringWithFormat:@"%@/%@/%@/%@/%@",continent,country,region,city,ident];NSArray *targets=[record objectForKey:@"targets"];[airportNodes addObject:[self node:title subtitle:[NSString stringWithFormat:@"%lu installed package entr%@",(unsigned long)targets.count,targets.count==1?@"y":@"ies"] key:key level:4 children:nil kind:@"airport" targets:targets files:[record objectForKey:@"files"] sizes:fileSizes]];}
                    NSMutableArray *targets=[NSMutableArray array];NSMutableSet *files=[NSMutableSet set];[self addTargetsFromNodes:airportNodes toArray:targets];[self addFilesFromNodes:airportNodes toSet:files];NSString *key=[NSString stringWithFormat:@"%@/%@/%@/%@",continent,country,region,city];[cityNodes addObject:[self node:city subtitle:[NSString stringWithFormat:@"%lu airport%@",(unsigned long)airportNodes.count,airportNodes.count==1?@"":@"s"] key:key level:3 children:airportNodes kind:@"city" targets:targets files:files sizes:fileSizes]];
                }
                NSMutableArray *targets=[NSMutableArray array];NSMutableSet *files=[NSMutableSet set];[self addTargetsFromNodes:cityNodes toArray:targets];[self addFilesFromNodes:cityNodes toSet:files];NSString *key=[NSString stringWithFormat:@"%@/%@/%@",continent,country,region];[regionNodes addObject:[self node:region subtitle:[NSString stringWithFormat:@"%lu cit%@",(unsigned long)cityNodes.count,cityNodes.count==1?@"y":@"ies"] key:key level:2 children:cityNodes kind:@"region" targets:targets files:files sizes:fileSizes]];
            }
            NSMutableArray *targets=[NSMutableArray array];NSMutableSet *files=[NSMutableSet set];[self addTargetsFromNodes:regionNodes toArray:targets];[self addFilesFromNodes:regionNodes toSet:files];NSString *key=[NSString stringWithFormat:@"%@/%@",continent,country];[countryNodes addObject:[self node:country subtitle:[NSString stringWithFormat:@"%lu subdivision%@",(unsigned long)regionNodes.count,regionNodes.count==1?@"":@"s"] key:key level:1 children:regionNodes kind:@"country" targets:targets files:files sizes:fileSizes]];
        }
        NSMutableArray *targets=[NSMutableArray array];NSMutableSet *files=[NSMutableSet set];[self addTargetsFromNodes:countryNodes toArray:targets];[self addFilesFromNodes:countryNodes toSet:files];[roots addObject:[self node:continent subtitle:[NSString stringWithFormat:@"%lu countr%@",(unsigned long)countryNodes.count,countryNodes.count==1?@"y":@"ies"] key:continent level:0 children:countryNodes kind:@"continent" targets:targets files:files sizes:fileSizes]];
    }
    self.rootNodes=roots;[self rebuildRows];
}
- (void)appendNode:(NSDictionary *)node toRows:(NSMutableArray *)rows { [rows addObject:node];NSArray *children=[node objectForKey:@"children"];if(children.count&&[self.expandedKeys containsObject:[node objectForKey:@"key"]])for(NSDictionary *child in children)[self appendNode:child toRows:rows]; }
- (void)rebuildRows { NSMutableArray *visible=[NSMutableArray array];for(NSDictionary *node in self.rootNodes)[self appendNode:node toRows:visible];self.rows=visible;[self.tableView reloadData]; }

- (NSInteger)numberOfSectionsInTableView:(UITableView *)table { return 1; }
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section { return self.rows.count; }
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    UITableViewCell *cell=[table dequeueReusableCellWithIdentifier:@"content"];if(!cell)cell=[[[UITableViewCell alloc]initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:@"content"]autorelease];NSDictionary *row=[self.rows objectAtIndex:path.row];NSInteger level=[[row objectForKey:@"level"]integerValue];NSArray *children=[row objectForKey:@"children"];
    cell.indentationLevel=level;cell.indentationWidth=18;cell.textLabel.text=[row objectForKey:@"title"];cell.detailTextLabel.text=[row objectForKey:@"subtitle"];cell.textLabel.adjustsFontSizeToFitWidth=YES;cell.textLabel.minimumScaleFactor=.72;cell.textLabel.font=[UIFont fontWithName:level==0?@"Helvetica-Bold":@"Helvetica" size:level==0?18:16];cell.selectionStyle=children.count?UITableViewCellSelectionStyleBlue:UITableViewCellSelectionStyleNone;
    if(children.count){UILabel *arrow=[[[UILabel alloc]initWithFrame:CGRectMake(0,0,24,30)]autorelease];arrow.backgroundColor=[UIColor clearColor];arrow.textAlignment=NSTextAlignmentCenter;arrow.font=[UIFont boldSystemFontOfSize:18];arrow.textColor=[UIColor grayColor];arrow.text=[self.expandedKeys containsObject:[row objectForKey:@"key"]]?@"▾":@"▸";cell.accessoryView=arrow;}else cell.accessoryView=nil;
    return cell;
}
- (void)tableView:(UITableView *)table didSelectRowAtIndexPath:(NSIndexPath *)path { NSDictionary *row=[self.rows objectAtIndex:path.row];if([[row objectForKey:@"children"]count]){NSString *key=[row objectForKey:@"key"];if([self.expandedKeys containsObject:key])[self.expandedKeys removeObject:key];else[self.expandedKeys addObject:key];[self rebuildRows];}[table deselectRowAtIndexPath:path animated:YES]; }
- (BOOL)tableView:(UITableView *)table canEditRowAtIndexPath:(NSIndexPath *)path { return [[[self.rows objectAtIndex:path.row]objectForKey:@"targets"]count]>0; }
- (UITableViewCellEditingStyle)tableView:(UITableView *)table editingStyleForRowAtIndexPath:(NSIndexPath *)path { return UITableViewCellEditingStyleDelete; }
- (NSString *)tableView:(UITableView *)table titleForDeleteConfirmationButtonForRowAtIndexPath:(NSIndexPath *)path { NSString *kind=[[[self.rows objectAtIndex:path.row]objectForKey:@"kind"]capitalizedString];return [NSString stringWithFormat:@"Delete %@",kind]; }
- (void)tableView:(UITableView *)table commitEditingStyle:(UITableViewCellEditingStyle)style forRowAtIndexPath:(NSIndexPath *)path { if(style!=UITableViewCellEditingStyleDelete)return;NSDictionary *row=[self.rows objectAtIndex:path.row];NSArray *targets=[[row objectForKey:@"targets"]copy];self.tableView.userInteractionEnabled=NO;self.navigationItem.prompt=[NSString stringWithFormat:@"Deleting %@ charts…",[row objectForKey:@"title"]];[self performSelectorInBackground:@selector(deleteTargetsBackground:)withObject:[targets autorelease]]; }
- (void)addAssetsFromAirport:(NSDictionary *)airport toSet:(NSMutableSet *)assets { NSString *map=[airport objectForKey:@"map"];if(map.length)[assets addObject:map];for(NSDictionary *category in [airport objectForKey:@"categories"])for(NSDictionary *chart in [category objectForKey:@"charts"])for(NSDictionary *page in [chart objectForKey:@"pages"]){NSString *path=[page objectForKey:@"light"];if(path.length)[assets addObject:path];} }
- (void)deleteTargetsBackground:(NSArray *)targets {
    NSAutoreleasePool *pool=[[NSAutoreleasePool alloc]init];NSFileManager *fm=[NSFileManager defaultManager];NSMutableDictionary *identsByPack=[NSMutableDictionary dictionary];
    for(NSDictionary *target in targets){NSString *path=[target objectForKey:@"path"],*ident=[target objectForKey:@"ident"];NSMutableSet *idents=[identsByPack objectForKey:path];if(!idents){idents=[NSMutableSet set];[identsByPack setObject:idents forKey:path];}if(ident)[idents addObject:ident];}
    NSUInteger deleted=0,failures=0;NSMutableSet *deletedIdents=[NSMutableSet set];
    for(NSString *packPath in identsByPack){NSData *data=[NSData dataWithContentsOfFile:[packPath stringByAppendingPathComponent:@"pack.json"]];NSDictionary *manifest=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;if(!manifest){failures++;continue;}NSMutableArray *remaining=[NSMutableArray array],*removed=[NSMutableArray array];NSSet *idents=[identsByPack objectForKey:packPath];for(NSDictionary *airport in [manifest objectForKey:@"airports"]){if([idents containsObject:[[airport objectForKey:@"ident"]uppercaseString]])[removed addObject:airport];else[remaining addObject:airport];}if(!removed.count)continue;[deletedIdents unionSet:idents];
        if(!remaining.count){NSError *error=nil;if([fm removeItemAtPath:packPath error:&error])deleted+=removed.count;else failures++;continue;}
        NSMutableDictionary *updated=[NSMutableDictionary dictionaryWithDictionary:manifest];[updated setObject:remaining forKey:@"airports"];NSData *updatedData=[NSJSONSerialization dataWithJSONObject:updated options:NSJSONWritingPrettyPrinted error:NULL];if(!updatedData||![updatedData writeToFile:[packPath stringByAppendingPathComponent:@"pack.json"]atomically:YES]){failures++;continue;}
        NSMutableSet *keptAssets=[NSMutableSet set],*removedAssets=[NSMutableSet set];for(NSDictionary *airport in remaining)[self addAssetsFromAirport:airport toSet:keptAssets];for(NSDictionary *airport in removed)[self addAssetsFromAirport:airport toSet:removedAssets];[removedAssets minusSet:keptAssets];for(NSString *relative in removedAssets)[fm removeItemAtPath:[packPath stringByAppendingPathComponent:relative]error:NULL];deleted+=removed.count;
    }
    NSString *mapRoot=@"/var/mobile/Library/SkyCharts/AirportMaps";for(NSString *ident in deletedIdents)[fm removeItemAtPath:[mapRoot stringByAppendingPathComponent:[ident stringByAppendingString:@".json"]]error:NULL];
    NSDictionary *result=[NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithUnsignedInteger:deleted],@"deleted",[NSNumber numberWithUnsignedInteger:failures],@"failures",nil];[self performSelectorOnMainThread:@selector(deleteTargetsFinished:)withObject:result waitUntilDone:NO];[pool drain];
}
- (void)deleteTargetsFinished:(NSDictionary *)result { NSUInteger deleted=[[result objectForKey:@"deleted"]unsignedIntegerValue],failures=[[result objectForKey:@"failures"]unsignedIntegerValue];self.navigationItem.prompt=failures?[NSString stringWithFormat:@"Deleted %lu; %lu package error%@",(unsigned long)deleted,(unsigned long)failures,failures==1?@"":@"s"]:nil;self.tableView.userInteractionEnabled=YES;[self reloadContent]; }
- (void)dealloc { [_tableView release];[_storageLabel release];[_rootNodes release];[_rows release];[_expandedKeys release];[super dealloc]; }
@end
