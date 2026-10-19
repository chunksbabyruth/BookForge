#!/usr/bin/env bash
# Sign BookForge.app, check the signature, and package it as a .dmg and a .zip.
#
# usage: tools/macos_sign_and_package.sh dist/BookForge.app OUTPUT_BASENAME
#   e.g. tools/macos_sign_and_package.sh dist/BookForge.app BookForge-macOS-arm64
#
# With an Apple "Developer ID Application" certificate (GitHub secrets, see README) the app is signed with
# the hardened runtime, notarized by Apple and stapled, so it opens normally on any Mac.
# Without one it is ad-hoc signed: the signature is complete and valid, but macOS still asks the user to
# allow the app once (Gatekeeper only trusts Developer ID + notarization). The DMG then includes a
# "How to open BookForge" note with the exact steps.
#
# Environment (all optional; leave unset for the ad-hoc build):
#   MACOS_CERTIFICATE_P12_BASE64   base64 of the exported Developer ID Application certificate (.p12)
#   MACOS_CERTIFICATE_PASSWORD     the .p12 password
#   MACOS_SIGNING_IDENTITY         e.g. "Developer ID Application: Your Name (TEAMID)" (found automatically if unset)
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_SPECIFIC_PASSWORD   for notarization (xcrun notarytool)
set -euo pipefail

APP="$1"
OUT="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
test -d "$APP" || { echo "::error::App bundle not found: $APP"; exit 1; }

# ------------------------------------------------------------------ identity
IDENTITY="-"
SIGN_ARGS=(--force --sign -)
DEVELOPER_ID=0
if [[ -n "${MACOS_CERTIFICATE_P12_BASE64:-}" ]]; then
  KEYCHAIN="$WORK/bookforge-signing.keychain-db"
  KEYCHAIN_PW="$(uuidgen)"
  echo "$MACOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$WORK/cert.p12"
  security create-keychain -p "$KEYCHAIN_PW" "$KEYCHAIN"
  security set-keychain-settings -lut 21600 "$KEYCHAIN"
  security unlock-keychain -p "$KEYCHAIN_PW" "$KEYCHAIN"
  security import "$WORK/cert.p12" -k "$KEYCHAIN" -P "${MACOS_CERTIFICATE_PASSWORD:-}" -T /usr/bin/codesign -T /usr/bin/security
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PW" "$KEYCHAIN" > /dev/null
  # put the new keychain first in the search list, keep the existing ones
  existing=()
  while IFS= read -r kc; do existing+=("$(echo "$kc" | tr -d ' "')"); done < <(security list-keychains -d user)
  security list-keychains -d user -s "$KEYCHAIN" "${existing[@]}"
  rm -f "$WORK/cert.p12"
  IDENTITY="${MACOS_SIGNING_IDENTITY:-}"
  if [[ -z "$IDENTITY" ]]; then
    IDENTITY="$(security find-identity -v -p codesigning "$KEYCHAIN" | grep -m1 'Developer ID Application' | sed -E 's/.*"(.*)".*/\1/')"
  fi
  [[ -n "$IDENTITY" ]] || { echo "::error::No 'Developer ID Application' identity in the certificate"; exit 1; }
  echo "Signing with: $IDENTITY"
  SIGN_ARGS=(--force --timestamp --options runtime --entitlements "$HERE/macos_entitlements.plist" --sign "$IDENTITY")
  DEVELOPER_ID=1
else
  echo "No Developer ID certificate configured: ad-hoc signing (macOS will ask the user to allow the app once)."
fi

# ------------------------------------------------------------------ sign inside-out
# Extended attributes and Finder info make codesign fail or give a broken seal.
xattr -cr "$APP"
EXE_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist" 2>/dev/null || echo BookForge)"
MAIN="$APP/Contents/MacOS/$EXE_NAME"
# every Mach-O file except the main executable, deepest first, so each container is sealed after its contents
while IFS= read -r f; do
  if [[ "$f" != "$MAIN" ]] && file -b "$f" | grep -q 'Mach-O'; then
    codesign "${SIGN_ARGS[@]}" "$f"
  fi
done < <(find "$APP/Contents" -type f -print | awk -F/ '{print NF "\t" $0}' | sort -rn | cut -f2-)
# nested bundles/frameworks (if any), then the app itself (this signs the main executable too)
while IFS= read -r b; do
  codesign "${SIGN_ARGS[@]}" "$b" || echo "::warning::$b is not a complete bundle; its files were signed one by one"
done < <(find "$APP/Contents" -depth -type d \( -name '*.framework' -o -name '*.app' -o -name '*.bundle' \) -print)
codesign "${SIGN_ARGS[@]}" "$APP"

codesign --verify --deep --strict --verbose=2 "$APP"
codesign --display --verbose=2 "$APP" 2>&1 | grep -E 'Identifier|Authority|Signature|Runtime|TeamIdentifier' || true

# ------------------------------------------------------------------ notarize + staple (Developer ID only)
notarize() {
  local file="$1" json
  json="$WORK/notary-$(basename "$file").json"
  xcrun notarytool submit "$file" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" --wait --timeout 45m --output-format json > "$json" || true
  cat "$json"
  local status id
  status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' "$json" 2>/dev/null || true)"
  id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("id",""))' "$json" 2>/dev/null || true)"
  if [[ "$status" != "Accepted" ]]; then
    [[ -n "$id" ]] && xcrun notarytool log "$id" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
      --password "$APPLE_APP_SPECIFIC_PASSWORD" || true
    echo "::error::Apple notarization of $(basename "$file") was not accepted (status: ${status:-unknown})"
    exit 1
  fi
}

NOTARIZED=0
if [[ "$DEVELOPER_ID" == 1 ]]; then
  if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ]]; then
    ditto -c -k --keepParent "$APP" "$WORK/notarize-app.zip"
    notarize "$WORK/notarize-app.zip"
    xcrun stapler staple "$APP"
    xcrun stapler validate "$APP"
    NOTARIZED=1
  else
    echo "::warning::Developer ID signed but NOT notarized (APPLE_ID / APPLE_TEAM_ID / APPLE_APP_SPECIFIC_PASSWORD not set). macOS will still warn."
  fi
fi

echo "Gatekeeper's view of the app (as a downloaded copy would be checked):"
if spctl --assess --type execute --verbose=4 "$APP" 2>&1; then
  echo "Gatekeeper: accepted"
else
  if [[ "$NOTARIZED" == 1 ]]; then
    echo "::error::Gatekeeper rejected the notarized app"; exit 1
  fi
  echo "Gatekeeper: not accepted (expected without a Developer ID certificate and notarization)"
fi

# ------------------------------------------------------------------ DMG and ZIP
STAGE="$WORK/dmg"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"
if [[ "$NOTARIZED" == 1 ]]; then
  cat > "$STAGE/How to install BookForge.txt" <<'TXT'
Drag BookForge onto the Applications folder, then open it from Applications.
BookForge is signed and notarized by Apple, so it opens like any other app.
TXT
else
  cat > "$STAGE/How to open BookForge.txt" <<'TXT'
HOW TO OPEN BOOKFORGE ON A MAC

1. Drag BookForge onto the Applications folder.
2. Open Applications and double-click BookForge.
   macOS says it can't check BookForge for malicious software (or that it is "damaged").
   This is because BookForge is free and not signed with a paid Apple Developer ID - the app itself is fine.
3. Click Done (or Cancel), then open System Settings > Privacy & Security.
   Scroll down to Security: "BookForge was blocked..." - click "Open Anyway" and confirm with your password.
   BookForge then opens normally from now on.

If macOS only offers "Move to Trash" (the "damaged" message) and there is no "Open Anyway" button:
   open Terminal (Applications > Utilities > Terminal), paste this line and press Return:

       xattr -dr com.apple.quarantine /Applications/BookForge.app

   then double-click BookForge again. (This removes the "downloaded from the internet" flag from
   BookForge only.)

Choose the right download for your Mac: Apple Silicon (M1, M2, M3, M4...) = arm64, Intel = x86_64.
(Apple menu > About This Mac shows "Chip: Apple M..." or "Processor: Intel...".)
TXT
fi
for doc in README.md LICENSE; do
  if [[ -f "$doc" ]]; then cp "$doc" "$STAGE/$doc"; fi
done
rm -f "$OUT.dmg"
hdiutil create -volname "BookForge" -srcfolder "$STAGE" -ov -format UDZO "$OUT.dmg"
if [[ "$DEVELOPER_ID" == 1 ]]; then
  codesign --force --timestamp --sign "$IDENTITY" "$OUT.dmg"
  if [[ "$NOTARIZED" == 1 ]]; then
    notarize "$OUT.dmg"
    xcrun stapler staple "$OUT.dmg"
    xcrun stapler validate "$OUT.dmg"
    spctl --assess --type open --context context:primary-signature --verbose=4 "$OUT.dmg"
  fi
fi
hdiutil verify "$OUT.dmg"
# the ZIP keeps the same contents as before (app bundle only), now with the stapled ticket when notarized
rm -f "$OUT.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT.zip"

# a copy extracted from the ZIP must still verify (catches packaging that breaks the signature)
mkdir -p "$WORK/unzip"
ditto -x -k "$OUT.zip" "$WORK/unzip"
codesign --verify --deep --strict --verbose=2 "$WORK/unzip/$(basename "$APP")"
echo "signed=$([[ $DEVELOPER_ID == 1 ]] && echo developer-id || echo ad-hoc) notarized=$NOTARIZED"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "notarized=$NOTARIZED" >> "$GITHUB_OUTPUT"
fi
if [[ -n "${KEYCHAIN:-}" ]]; then
  security delete-keychain "$KEYCHAIN" || true
fi
