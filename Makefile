export TARGET = iphone:clang:10.3:6.0
export ARCHS = armv7

include $(THEOS)/makefiles/common.mk

APPLICATION_NAME = AtlasSix

AtlasSix_FILES = AtlasSix/main.m AtlasSix/AppDelegate.m AtlasSix/ChartViewController.m AtlasSix/ContentManagerViewController.m AtlasSix/Compat.c
AtlasSix_FRAMEWORKS = UIKit Foundation CoreGraphics QuartzCore Security
AtlasSix_CFLAGS = -fno-objc-arc -Wno-deprecated-declarations -fmodules-cache-path=$(THEOS_PROJECT_DIR)/.theos/module-cache
AtlasSix_USE_MODULES = 0
AtlasSix_INSTALL_PATH = /Applications

include $(THEOS_MAKE_PATH)/application.mk

after-stage::
	cp AtlasSix.plist "$(THEOS_STAGING_DIR)/Applications/AtlasSix.app/Info.plist"
