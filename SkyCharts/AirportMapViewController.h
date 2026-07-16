#import <UIKit/UIKit.h>

@interface AirportMapViewController : UIViewController <UIScrollViewDelegate>
- (id)initWithICAO:(NSString *)icao mapPath:(NSString *)mapPath;
@end
