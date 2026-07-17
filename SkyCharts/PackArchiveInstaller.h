#import <Foundation/Foundation.h>

@interface PackArchiveInstaller : NSObject <NSURLConnectionDelegate> {
    NSURL *_archiveURL;
    NSString *_chartRoot;
    NSString *_jobID;
    NSString *_incomingPath;
    NSString *_errorText;
    NSString *_currentRelativePath;
    NSString *_lastDirectory;
    NSMutableData *_headerBuffer;
    NSMutableSet *_extractedPaths;
    NSURLConnection *_connection;
    id _progressTarget;
    SEL _progressSelector;
    unsigned long long _fileRemaining;
    unsigned long long _paddingRemaining;
    long long _expectedBytes;
    long long _receivedBytes;
    NSUInteger _expectedFiles;
    NSUInteger _extractedFiles;
    NSTimeInterval _startedAt;
    NSTimeInterval _lastProgressAt;
    BOOL _running;
    BOOL _networkOK;
    BOOL _archiveOK;
    BOOL _sawArchiveEnd;
    int _outputFD;
}
- (id)initWithURL:(NSURL *)url chartRoot:(NSString *)root jobID:(NSString *)jobID expectedBytes:(long long)bytes expectedFiles:(NSUInteger)files progressTarget:(id)target selector:(SEL)selector;
- (BOOL)run;
@property(nonatomic, readonly) NSString *errorText;
@end
