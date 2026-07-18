#import "StoragePaths.h"

static BOOL SkyChartsDirectoryIsWritable(NSString *path) {
    NSFileManager *fm=[NSFileManager defaultManager];
    if(![fm createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL])return NO;
    NSString *probe=[path stringByAppendingPathComponent:@".write-test"];
    NSData *data=[NSData dataWithBytes:"1" length:1];
    BOOL writable=[data writeToFile:probe atomically:NO];
    if(writable)[fm removeItemAtPath:probe error:NULL];
    return writable;
}

static NSString *SkyChartsSandboxStorageRoot(void) {
    NSArray *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES);
    NSString *base=documents.count?[documents objectAtIndex:0]:NSTemporaryDirectory();
    return [base stringByAppendingPathComponent:@"SkyCharts"];
}

static void SkyChartsMergeDirectory(NSString *source,NSString *destination) {
    NSFileManager *fm=[NSFileManager defaultManager];BOOL isDirectory=NO;
    if(![fm fileExistsAtPath:source isDirectory:&isDirectory]||!isDirectory)return;
    [fm createDirectoryAtPath:destination withIntermediateDirectories:YES attributes:nil error:NULL];
    for(NSString *entry in [fm contentsOfDirectoryAtPath:source error:NULL]){
        NSString *from=[source stringByAppendingPathComponent:entry],*to=[destination stringByAppendingPathComponent:entry];
        if(![fm fileExistsAtPath:to])[fm moveItemAtPath:from toPath:to error:NULL];
    }
}

NSString *SkyChartsStorageRoot(void) {
    static NSString *root=nil;
    @synchronized([NSFileManager class]){
        if(root)return root;
        NSString *shared=@"/var/mobile/Library/SkyCharts",*sandbox=SkyChartsSandboxStorageRoot();
        if(SkyChartsDirectoryIsWritable(shared)){
            root=[shared copy];
            if(![sandbox isEqualToString:shared]){
                SkyChartsMergeDirectory([sandbox stringByAppendingPathComponent:@"ChartPacks"],[shared stringByAppendingPathComponent:@"ChartPacks"]);
                SkyChartsMergeDirectory([sandbox stringByAppendingPathComponent:@"AirportMaps"],[shared stringByAppendingPathComponent:@"AirportMaps"]);
            }
        }else{
            SkyChartsDirectoryIsWritable(sandbox);
            root=[sandbox copy];
        }
        return root;
    }
}

NSString *SkyChartsChartPackRoot(void) {
    NSString *path=[SkyChartsStorageRoot() stringByAppendingPathComponent:@"ChartPacks"];
    [[NSFileManager defaultManager]createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
    return path;
}

NSString *SkyChartsAirportMapRoot(void) {
    NSString *path=[SkyChartsStorageRoot() stringByAppendingPathComponent:@"AirportMaps"];
    [[NSFileManager defaultManager]createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
    return path;
}
