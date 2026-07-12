#import "PackArchiveInstaller.h"

static unsigned long long SkyChartsTarOctal(const unsigned char *bytes, NSUInteger length) {
    unsigned long long value=0;NSUInteger index=0;while(index<length&&(bytes[index]==' '||bytes[index]=='\0'))index++;for(;index<length;index++){unsigned char byte=bytes[index];if(byte<'0'||byte>'7')break;value=(value<<3)+(byte-'0');}return value;
}
static NSString *SkyChartsTarString(const unsigned char *bytes, NSUInteger length) {
    NSUInteger used=0;while(used<length&&bytes[used])used++;if(!used)return @"";return [[[NSString alloc]initWithBytes:bytes length:used encoding:NSUTF8StringEncoding]autorelease];
}

@implementation PackArchiveInstaller
@synthesize errorText=_errorText;

- (id)initWithURL:(NSURL *)url chartRoot:(NSString *)root jobID:(NSString *)jobID expectedBytes:(long long)bytes expectedFiles:(NSUInteger)files progressTarget:(id)target selector:(SEL)selector {
    if((self=[super init])){_archiveURL=[url retain];_chartRoot=[root copy];_jobID=[jobID copy];_expectedBytes=bytes;_expectedFiles=files;_progressTarget=target;_progressSelector=selector;_headerBuffer=[[NSMutableData alloc]initWithCapacity:512];_archiveOK=YES;}return self;
}
- (BOOL)safeRelativePath:(NSString *)path { if(!path.length||[path hasPrefix:@"/"])return NO;for(NSString *part in [path pathComponents])if([part isEqual:@".."]||[part isEqual:@"."]||[part isEqual:@"/"]||!part.length)return NO;return YES; }
- (void)fail:(NSString *)message { if(!_errorText)_errorText=[message copy];_archiveOK=NO;[_connection cancel];_running=NO; }
- (void)closeOutput { if(_outputHandle){@try{[_outputHandle closeFile];}@catch(NSException *exception){}[_outputHandle release];_outputHandle=nil;} }
- (BOOL)openHeader:(const unsigned char *)header {
    BOOL allZero=YES;for(NSUInteger index=0;index<512;index++)if(header[index]){allZero=NO;break;}if(allZero){_sawArchiveEnd=YES;return YES;}
    NSString *name=SkyChartsTarString(header,100),*prefix=SkyChartsTarString(header+345,155);if(prefix.length)name=[NSString stringWithFormat:@"%@/%@",prefix,name];if(![self safeRelativePath:name]){[self fail:@"Archive contains an unsafe file path"];return NO;}
    unsigned char type=header[156];if(type!='\0'&&type!='0'){[self fail:@"Archive contains an unsupported entry"];return NO;}
    _fileRemaining=SkyChartsTarOctal(header+124,12);_paddingRemaining=(512-(_fileRemaining%512))%512;NSString *target=[_incomingPath stringByAppendingPathComponent:name];NSFileManager *fm=[NSFileManager defaultManager];if(![fm createDirectoryAtPath:[target stringByDeletingLastPathComponent]withIntermediateDirectories:YES attributes:nil error:NULL]||![fm createFileAtPath:target contents:nil attributes:nil]){[self fail:@"Could not create an extracted chart file"];return NO;}_outputHandle=[[NSFileHandle fileHandleForWritingAtPath:target]retain];if(!_outputHandle){[self fail:@"Could not open an extracted chart file"];return NO;}if(!_fileRemaining){[self closeOutput];_extractedFiles++;}return YES;
}
- (void)consumeData:(NSData *)data {
    const unsigned char *bytes=[data bytes];NSUInteger offset=0,length=[data length];
    while(offset<length&&_archiveOK&&!_sawArchiveEnd){
        if(_fileRemaining){NSUInteger amount=(NSUInteger)MIN((unsigned long long)(length-offset),_fileRemaining);@try{NSData *chunk=[[NSData alloc]initWithBytes:bytes+offset length:amount];[_outputHandle writeData:chunk];[chunk release];}@catch(NSException *exception){[self fail:@"Could not write an extracted chart file"];break;}offset+=amount;_fileRemaining-=amount;if(!_fileRemaining){[self closeOutput];_extractedFiles++;}continue;}
        if(_paddingRemaining){NSUInteger amount=(NSUInteger)MIN((unsigned long long)(length-offset),_paddingRemaining);offset+=amount;_paddingRemaining-=amount;continue;}
        NSUInteger needed=512-[_headerBuffer length],amount=MIN(needed,length-offset);[_headerBuffer appendBytes:bytes+offset length:amount];offset+=amount;if([_headerBuffer length]==512){unsigned char header[512];[_headerBuffer getBytes:header length:512];[_headerBuffer setLength:0];if(![self openHeader:header])break;}
    }
}
- (void)reportProgressForced:(BOOL)forced {
    NSTimeInterval now=[NSDate timeIntervalSinceReferenceDate];if(!forced&&now-_lastProgressAt<.45)return;_lastProgressAt=now;long long total=_expectedBytes>0?_expectedBytes:MAX((long long)1,_receivedBytes);NSInteger eta=0;NSTimeInterval elapsed=now-_startedAt;if(_expectedBytes>0&&_receivedBytes>0&&elapsed>1)eta=(NSInteger)(elapsed*(_expectedBytes-_receivedBytes)/_receivedBytes);NSArray *values=[NSArray arrayWithObjects:[NSNumber numberWithUnsignedInteger:_extractedFiles],[NSNumber numberWithUnsignedInteger:_expectedFiles],[NSNumber numberWithLongLong:_receivedBytes],[NSNumber numberWithLongLong:total],[NSNumber numberWithInteger:MAX(0,eta)],nil];if(_progressTarget&&_progressSelector)[_progressTarget performSelectorOnMainThread:_progressSelector withObject:values waitUntilDone:NO];
}
- (BOOL)finishInstallation {
    if(!_networkOK||!_archiveOK||!_sawArchiveEnd||(_expectedBytes>0&&_receivedBytes!=_expectedBytes)||(_expectedFiles>0&&_extractedFiles!=_expectedFiles)){if(!_errorText)_errorText=[@"Chart archive transfer was incomplete" copy];return NO;}NSString *manifestPath=[_incomingPath stringByAppendingPathComponent:@"pack.json"];NSData *data=[NSData dataWithContentsOfFile:manifestPath];NSDictionary *manifest=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;NSString *packID=[manifest objectForKey:@"packId"];if(!packID.length||[packID rangeOfString:@"/"].location!=NSNotFound||[packID rangeOfString:@".."].location!=NSNotFound){_errorText=[@"Downloaded archive has an invalid manifest" copy];return NO;}NSFileManager *fm=[NSFileManager defaultManager];for(NSDictionary *airport in [manifest objectForKey:@"airports"])for(NSDictionary *category in [airport objectForKey:@"categories"])for(NSDictionary *chart in [category objectForKey:@"charts"])for(NSDictionary *page in [chart objectForKey:@"pages"]){NSString *relative=[page objectForKey:@"light"];if(relative.length&&(![self safeRelativePath:relative]||![fm fileExistsAtPath:[_incomingPath stringByAppendingPathComponent:relative]])){_errorText=[@"Downloaded archive is missing a chart referenced by its manifest" copy];return NO;}}NSString *target=[_chartRoot stringByAppendingPathComponent:packID];[fm removeItemAtPath:target error:NULL];if(![fm moveItemAtPath:_incomingPath toPath:target error:NULL]){_errorText=[@"Could not activate the downloaded chart package" copy];return NO;}return YES;
}
- (BOOL)run {
    NSFileManager *fm=[NSFileManager defaultManager];if(!_jobID.length||[_jobID rangeOfString:@"/"].location!=NSNotFound||[_jobID rangeOfString:@".."].location!=NSNotFound){_errorText=[@"Invalid chart job identifier" copy];return NO;}_incomingPath=[[_chartRoot stringByAppendingPathComponent:[@".incoming-" stringByAppendingString:_jobID]]copy];[fm createDirectoryAtPath:_chartRoot withIntermediateDirectories:YES attributes:nil error:NULL];[fm removeItemAtPath:_incomingPath error:NULL];if(![fm createDirectoryAtPath:_incomingPath withIntermediateDirectories:YES attributes:nil error:NULL]){_errorText=[@"Could not create temporary chart directory" copy];return NO;}
    Class requestClass=NSClassFromString(@"NSMutableURLRequest"),connectionClass=NSClassFromString(@"NSURLConnection");id request=[requestClass requestWithURL:_archiveURL cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:3600];_startedAt=[NSDate timeIntervalSinceReferenceDate];_running=YES;_connection=[[connectionClass alloc]initWithRequest:request delegate:self startImmediately:YES];if(!_connection){[self fail:@"Could not start chart archive transfer"];}
    while(_running){NSAutoreleasePool *loopPool=[[NSAutoreleasePool alloc]init];[[NSRunLoop currentRunLoop]runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.20]];[loopPool drain];}[self closeOutput];BOOL success=[self finishInstallation];if(!success)[fm removeItemAtPath:_incomingPath error:NULL];[self reportProgressForced:YES];return success;
}
- (void)connection:(NSURLConnection *)connection didReceiveResponse:(NSURLResponse *)response { Class responseClass=NSClassFromString(@"NSHTTPURLResponse");if(responseClass&&[response isKindOfClass:responseClass]&&[(id)response statusCode]!=200){[self fail:[NSString stringWithFormat:@"Mac Pack Agent rejected the archive request"]];return;}if([response expectedContentLength]>0)_expectedBytes=[response expectedContentLength]; }
- (void)connection:(NSURLConnection *)connection didReceiveData:(NSData *)data { NSAutoreleasePool *pool=[[NSAutoreleasePool alloc]init];_receivedBytes+=[data length];[self consumeData:data];[self reportProgressForced:NO];[pool drain]; }
- (void)connectionDidFinishLoading:(NSURLConnection *)connection { _networkOK=YES;_running=NO; }
- (void)connection:(NSURLConnection *)connection didFailWithError:(NSError *)error { if(!_errorText)_errorText=[[error localizedDescription]copy];_running=NO; }
- (void)dealloc { [_connection cancel];[_connection release];[self closeOutput];[_archiveURL release];[_chartRoot release];[_jobID release];[_incomingPath release];[_errorText release];[_headerBuffer release];[super dealloc]; }
@end
