#!/bin/bash
# Build the FileReceiver APK using Android command line tools
set -e

ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
BUILD_TOOLS="$ANDROID_HOME/build-tools/34.0.0"
PLATFORM="$ANDROID_HOME/platforms/android-34/android.jar"

AAPT2="$BUILD_TOOLS/aapt2"
D8="$BUILD_TOOLS/d8"
ZIPALIGN="$BUILD_TOOLS/zipalign"
APKSIGNER="$BUILD_TOOLS/apksigner"

SRC_DIR="src"
OUT_DIR="build"
APK_NAME="FileReceiver.apk"

echo "=== Building FileReceiver APK ==="

# Clean
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/compiled" "$OUT_DIR/classes"

# 1. Compile resources (minimal - no res files needed for this app)
echo "[1/5] Linking resources..."
$AAPT2 link \
    --manifest AndroidManifest.xml \
    -I "$PLATFORM" \
    --java "$OUT_DIR/gen" \
    -o "$OUT_DIR/base.apk" \
    --auto-add-overlay

# 2. Compile Java
echo "[2/5] Compiling Java..."
# Find all .java files
find "$SRC_DIR" -name "*.java" > "$OUT_DIR/sources.txt"

# Add generated R.java if it exists
if [ -d "$OUT_DIR/gen" ]; then
    find "$OUT_DIR/gen" -name "*.java" >> "$OUT_DIR/sources.txt"
fi

javac \
    -classpath "$PLATFORM" \
    -source 11 -target 11 \
    -d "$OUT_DIR/classes" \
    @"$OUT_DIR/sources.txt" \
    2>&1

# 3. Convert to DEX
echo "[3/5] Converting to DEX..."
find "$OUT_DIR/classes" -name "*.class" > "$OUT_DIR/classes.txt"
$D8 \
    --release \
    --min-api 21 \
    --output "$OUT_DIR" \
    @"$OUT_DIR/classes.txt"

# 4. Add DEX to APK
echo "[4/5] Building APK..."
cp "$OUT_DIR/base.apk" "$OUT_DIR/$APK_NAME"
cd "$OUT_DIR"
zip -u "$APK_NAME" classes.dex
cd ..

# 5. Align and sign
echo "[5/5] Signing APK..."

# Create a debug keystore if it doesn't exist
KEYSTORE="$OUT_DIR/debug.keystore"
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair \
        -keystore "$KEYSTORE" \
        -storepass android \
        -keypass android \
        -alias debug \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000 \
        -dname "CN=Debug,O=Boost,C=BR" \
        2>/dev/null
fi

$ZIPALIGN -f 4 "$OUT_DIR/$APK_NAME" "$OUT_DIR/aligned.apk"

$APKSIGNER sign \
    --ks "$KEYSTORE" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --ks-key-alias debug \
    --out "$APK_NAME" \
    "$OUT_DIR/aligned.apk"

# Verify
$APKSIGNER verify "$APK_NAME" && echo "APK verified OK"

SIZE=$(ls -lh "$APK_NAME" | awk '{print $5}')
echo ""
echo "=== Build complete: $APK_NAME ($SIZE) ==="
