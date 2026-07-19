# Shijian · 拾笺

Shijian is a personal capture bridge to Obsidian. Share a WeChat article to the Android app, and it queues the article for conversion and delivery to your own Fast Note Sync vault. The product is designed to grow from WeChat links to text, images, and other captured information.

Suggested GitHub repository name: `shijian-clipper`.

## Android app

- App name: 拾笺 (Shijian)
- Default service: `https://wechat.lucc.fun`
- Self-hosting: change the service URL from Settings, then sign in again.
- Input: share a WeChat public-account article from the system share sheet, or paste its HTTPS URL.
- Output: Markdown is written to the configured Fast Note Sync vault and Obsidian folder; article images keep their original URLs.

Accounts are invitation-only. An invitation grants 30 days of use from registration; PocketBase administrators can extend a user by editing `access_expires_at` in the `users` collection.

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

Production deployment, PocketBase administration, and Docker Compose instructions are in [deploy/README.md](deploy/README.md). Never commit `.env`, FNS tokens, or signing keys.
