# Shijian · 拾笺

[中文说明](README_CN.md)

Shijian is an Android and Python service for capturing WeChat public-account articles into an Obsidian vault through Fast Note Sync. This repository contains the Android client, API, Worker, PocketBase migrations, and local H5 debugging PoC.

## Android app

- App name: 拾笺 (Shijian)
- Default service: `https://wechat.fun` (or your custom deployment)
- Self-hosting: change the service URL from Settings, then sign in again.
- Input: share a WeChat public-account article (text URL) or **share any file / image** from the system share sheet, or paste its HTTPS URL / upload from Chat interface.
- Output: WeChat articles are written to the **WeChat Article folder**, and attachments (images, PDFs, documents) are saved to the **Attachment folder** configured in Settings. Both destinations reside in your self-hosted Fast Note Sync vault.
- About: Settings shows the installed version and GitHub repository. It checks the latest GitHub Release, highlights a newer version, verifies its SHA-256 and signing certificate, then hands installation to Android for user confirmation.

### Screenshots
<p align="center">
  <img src="assets/screenshots/main.jpg" width="30%" />
  &nbsp; &nbsp; &nbsp; &nbsp;
  <img src="assets/screenshots/settings.jpg" width="30%" />
</p>


## Invitation and access management

- Registration requires a single-use invitation code. A code has no expiry before it is consumed.
- The first successful registration consumes the code and assigns 30 days of access.
- A PocketBase superuser can edit `users.access_expires_at` to extend or shorten a specific user's access.
- A PocketBase superuser can set `users.can_create_invites` for a user. Authorized users then see **Member invitation** in the Android Settings page and can generate one single-use invitation at a time.
- Do not manually create an `invite_codes` record unless both its plaintext `code` and SHA-256 `code_hash` are set correctly.

## Build the APK

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug'
```

The Debug APK is created at `android/app/build/outputs/apk/debug/app-debug.apk`.

## Build and publish a signed release

Only distribute a release-signed APK. Keep the keystore outside this repository and back it up with its password; changing the signing certificate prevents in-place upgrades. The release Gradle task deliberately fails unless all four environment variables are present:

```bash
export SHIJIAN_RELEASE_STORE_FILE="/safe/path/shijian-release.jks"
export SHIJIAN_RELEASE_STORE_PASSWORD="…"
export SHIJIAN_RELEASE_KEY_ALIAS="shijian-release"
export SHIJIAN_RELEASE_KEY_PASSWORD="…"

JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:testDebugUnitTest :app:assembleRelease'
```

Publish `android/app/build/outputs/apk/release/app-release.apk` as a GitHub Release asset named `Shijian-v<versionName>-<versionCode>-release.apk`, with a matching tag `v<versionName>`. GitHub calculates and exposes the asset `sha256` digest through its Release API; the app rejects releases without that digest, unexpected asset names/URLs, mismatched package metadata, or a certificate different from the installed app. Installation is never silent: users confirm the download in the app and the install in Android.

The first signed release cannot upgrade an older Debug-signed installation. Test users must uninstall the Debug APK, install the signed release, and log in again. Subsequent releases signed with the same keystore upgrade normally.

## Local H5 PoC

```bash
python3 -m poc.server
```

Open `http://127.0.0.1:8765`. FNS API tokens are kept only in memory in the H5 page and are not saved to browser storage.

## Deployment

Production deployment, PocketBase administration, and Docker Compose instructions are in [deploy/README.md](deploy/README.md). For an AI agent-operated VPS deployment with Nginx, see [deploy/AI_DEPLOYMENT.md](deploy/AI_DEPLOYMENT.md). Never commit `.env`, FNS tokens, or signing keys.
