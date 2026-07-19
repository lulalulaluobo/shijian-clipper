# Shijian · 拾笺

[中文说明](README_CN.md)

Shijian is an Android and Python service for capturing WeChat public-account articles into an Obsidian vault through Fast Note Sync. This repository contains the Android client, API, Worker, PocketBase migrations, and local H5 debugging PoC.

## Android app

- App name: 拾笺 (Shijian)
- Default service: `https://wechat.lucc.fun`
- Self-hosting: change the service URL from Settings, then sign in again.
- Input: share a WeChat public-account article from the system share sheet, or paste its HTTPS URL.
- Output: Markdown is written to the configured Fast Note Sync vault and Obsidian folder; article images keep their original URLs.

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

## Local H5 PoC

```bash
python3 -m poc.server
```

Open `http://127.0.0.1:8765`. FNS API tokens are kept only in memory in the H5 page and are not saved to browser storage.

## Deployment

Production deployment, PocketBase administration, and Docker Compose instructions are in [deploy/README.md](deploy/README.md). For an AI agent-operated VPS deployment with Nginx, see [deploy/AI_DEPLOYMENT.md](deploy/AI_DEPLOYMENT.md). Never commit `.env`, FNS tokens, or signing keys.
