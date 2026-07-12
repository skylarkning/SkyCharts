export TARGET = iphone:clang:10.3:6.0
export ARCHS = armv7

include $(THEOS)/makefiles/common.mk

APPLICATION_NAME = SkyCharts

SkyCharts_FILES = SkyCharts/main.m SkyCharts/AppDelegate.m SkyCharts/ChartViewController.m SkyCharts/ContentManagerViewController.m SkyCharts/Compat.c
SkyCharts_FRAMEWORKS = UIKit Foundation CoreGraphics QuartzCore Security
SkyCharts_CFLAGS = -fno-objc-arc -Wno-deprecated-declarations -fmodules-cache-path=$(THEOS_PROJECT_DIR)/.theos/module-cache
SkyCharts_USE_MODULES = 0
SkyCharts_INSTALL_PATH = /Applications

include $(THEOS_MAKE_PATH)/application.mk

after-stage::
	cp SkyCharts.plist "$(THEOS_STAGING_DIR)/Applications/SkyCharts.app/Info.plist"
