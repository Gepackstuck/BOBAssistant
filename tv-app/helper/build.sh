#!/bin/sh
set -e
SDK=${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}
JAVA=${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}
export JAVA_HOME=$JAVA
DIR=$(cd "$(dirname "$0")" && pwd)
rm -rf "$DIR/build"
mkdir "$DIR/build"
"$JAVA/bin/javac" -source 8 -target 8 -cp "$SDK/platforms/android-34/android.jar" -d "$DIR/build" "$DIR"/src/com/bobassistant/helper/*.java 2>&1 | grep -v "warning\|Note" || true
"$SDK/build-tools/34.0.0/d8" --release --lib "$SDK/platforms/android-34/android.jar" --output "$DIR/build" "$DIR"/build/com/bobassistant/helper/*.class
(cd "$DIR/build" && zip -q helper.jar classes.dex)
echo "$DIR/build/helper.jar"
