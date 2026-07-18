#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
APP_PATH=${1:-"$PROJECT_ROOT/.theos/_/Applications/SkyCharts.app"}
OUTPUT_DIR=${2:-"$PROJECT_ROOT/outputs"}
PLIST_BUDDY=/usr/libexec/PlistBuddy

if [ ! -d "$APP_PATH" ]; then
    echo "SkyCharts.app is not staged at $APP_PATH" >&2
    echo "Run 'make package FINALPACKAGE=1' first, or use 'make ipa'." >&2
    exit 1
fi

INFO_PLIST="$APP_PATH/Info.plist"
if [ ! -f "$INFO_PLIST" ]; then
    echo "Staged app is missing Info.plist: $INFO_PLIST" >&2
    exit 1
fi

PUBLIC_VERSION=$($PLIST_BUDDY -c 'Print :SkyChartsPublicVersion' "$INFO_PLIST")
INTERNAL_VERSION=$($PLIST_BUDDY -c 'Print :CFBundleShortVersionString' "$INFO_PLIST")
BUILD_NUMBER=$($PLIST_BUDDY -c 'Print :CFBundleVersion' "$INFO_PLIST")

if [ -z "$PUBLIC_VERSION" ] || [ -z "$INTERNAL_VERSION" ] || [ -z "$BUILD_NUMBER" ]; then
    echo "Public version, internal version, and build number must all be set." >&2
    exit 1
fi

PUBLIC_SLUG=$(printf '%s' "$PUBLIC_VERSION" | tr '[:space:]' '-' | tr -cd '[:alnum:]._-')
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
OUTPUT_PATH="$OUTPUT_DIR/SkyCharts-$PUBLIC_SLUG-ios6-armv7.ipa"

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/skycharts-ipa.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM
mkdir -p "$TEMP_ROOT/Payload"
cp -R "$APP_PATH" "$TEMP_ROOT/Payload/SkyCharts.app"

rm -f "$OUTPUT_PATH"
(cd "$TEMP_ROOT" && COPYFILE_DISABLE=1 /usr/bin/zip -qry "$OUTPUT_PATH" Payload)

echo "Created $OUTPUT_PATH"
echo "Public: $PUBLIC_VERSION (Build $BUILD_NUMBER)"
echo "Internal: $INTERNAL_VERSION"
