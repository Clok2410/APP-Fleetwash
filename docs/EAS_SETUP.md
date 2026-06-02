# Fleetwash Hub — EAS Build Setup (iOS / Android)

**Goal:** wire this app to your Expo account so you can build store-ready iOS
and Android binaries with one command. Takes ~5 minutes the first time.

> You only need to do this once. After that, `eas build -p ios` (or `-p android`)
> just works from your laptop.

---

## 1. Prerequisites (one-time)

On your laptop (Mac or Windows — not the Emergent pod):

```bash
# Node 20+ — already installed if you have a recent Node
node -v

# Install the Expo CLI globally
npm install -g eas-cli
```

Create a free Expo account if you don't have one:
https://expo.dev/signup

## 2. Clone the repo to your laptop

```bash
git clone https://github.com/Clok2410/APP-Fleetwash.git
cd APP-Fleetwash/frontend
yarn install
```

## 3. Log into EAS and init the project

```bash
eas login
# email: your-expo-email   password: your-expo-password

eas init
# Choose: "Yes, link to an existing project" → No (first time)
# Project name: Fleetwash Hub
# Slug:         fleetwash-hub
```

`eas init` writes the **`projectId`** into `app.json` automatically — you can
verify it under `extra.eas.projectId` (it'll look like
`a8e1c0a4-...-...-...-...`).

> If it doesn't update `app.json` for some reason, copy the printed projectId
> and paste it manually into `frontend/app.json` under `extra.eas.projectId`,
> replacing the placeholder string.

## 4. Commit + push the projectId back to GitHub

```bash
cd ..   # back to repo root
git add frontend/app.json
git commit -m "EAS: set projectId"
git push origin main
```

(That keeps the pod in sync the next time it pulls the repo.)

## 5. Build for iOS / Android

iOS (TestFlight / App Store) — **needs an Apple Developer account ($99/yr)**:

```bash
cd frontend
eas build --platform ios --profile production
# First time: EAS will ask to register a Bundle Identifier + generate
# certificates/provisioning profiles. Just say "yes" to all prompts —
# EAS manages everything in the cloud.
```

Android (Play Store) — **needs a Google Play Developer account ($25 one-time)**:

```bash
eas build --platform android --profile production
```

Internal testing build (no store needed — install via QR code on a real phone):

```bash
eas build --platform android --profile preview      # APK you can sideload
eas build --platform ios --profile preview          # ad-hoc, attach phone UDID
```

## 6. Submit to the stores (optional, when ready)

```bash
# iOS App Store
eas submit -p ios --latest

# Google Play
eas submit -p android --latest
```

EAS will walk you through the App Store Connect / Play Console linking.

---

## Build profiles already configured

See `frontend/eas.json`:
- `development` — dev client with hot-reload, install on your device
- `preview`     — internal QR-code share (APK / ad-hoc IPA)
- `production` — store-ready binaries

## Troubleshooting

- **"Project not found"** → make sure `extra.eas.projectId` in `app.json`
  matches what `eas init` printed. Rerun `eas init` if needed.
- **"Apple credentials expired"** → `eas credentials -p ios` → "Manage
  Credentials" → regenerate.
- **Splash / icon wrong** → re-run `npx expo prebuild --clean` then rebuild.
- **Bundle identifier already taken** → change `ios.bundleIdentifier` and
  `android.package` in `app.json` to e.g. `com.fleetwash.hubpro`.

---

## What's already set for you

- ✅ App name: **Fleetwash Hub**
- ✅ Slug: `fleetwash-hub`
- ✅ iOS bundle: `com.fleetwash.hub`
- ✅ Android package: `com.fleetwash.hub`
- ✅ Icon: `assets/images/icon.png` (FleetWash logo on black)
- ✅ Adaptive icon: `assets/images/adaptive-icon.png` (Android)
- ✅ Splash: `assets/images/splash-image.png` (logo on black)
- ✅ Favicon: `assets/images/favicon.png` (web)
- ✅ Permissions: location (geofenced clock-in), camera, photos
- ⏳ `projectId` placeholder — **`eas init` will fill this in for you**
