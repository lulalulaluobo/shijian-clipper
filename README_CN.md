# Shijian · 拾笺

[English](README.md)

拾笺由 Android 客户端与 Python 服务组成，用于将微信公众号文章经 Fast Note Sync 转存到 Obsidian。本仓库包含 Android 客户端、API、Worker、PocketBase 迁移和本地 H5 调试页。

## Android App

- 应用名：拾笺（Shijian）
- 默认服务：`https://wechat.lucc.fun`
- 自部署：在「设置」中修改服务地址，然后重新登录。
- 输入：在系统分享面板分享微信公众号文章，或粘贴 HTTPS 文章链接。
- 输出：文章 Markdown 会写入配置的 Fast Note Sync 仓库与 Obsidian 目录；图片保留原始链接。
- 状态：任务排队或执行时，首页会自动刷新状态；完成、失败后会停止刷新并显示最终状态。
- 关于：在「设置」可查看当前版本与 GitHub 项目。应用会检查最新 GitHub Release，高亮新版本；下载后校验 SHA-256 与发布签名，最后仍由 Android 系统要求用户确认安装。

## 邀请码与使用期限管理

- 账户必须通过一次性邀请码注册；邀请码在被使用前不会过期。
- 邀请码首次成功注册后即被消费，注册用户默认获得 30 天使用期限。
- PocketBase 超级管理员可在 `users` 集合修改指定用户的 `access_expires_at`，延长或缩短该用户的使用期限。
- PocketBase 超级管理员可为指定用户开启 `users.can_create_invites`。被授权用户会在 APK「设置 → 成员邀请」看到生成入口，可生成并分享一次性邀请码。
- 不要直接随意新建 `invite_codes` 记录；真实 `code` 与对应 SHA-256 `code_hash` 必须同时正确写入，邀请码才能注册。

## 构建 APK

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug'
```

Debug APK 位于 `android/app/build/outputs/apk/debug/app-debug.apk`。

## 构建并发布正式签名包

请只分发正式签名的 APK。keystore 必须放在仓库外，并和密码一起备份；一旦更换发布证书，已安装应用无法原地升级。release 任务要求以下四个环境变量齐全，否则会主动失败：

```bash
export SHIJIAN_RELEASE_STORE_FILE="/safe/path/shijian-release.jks"
export SHIJIAN_RELEASE_STORE_PASSWORD="…"
export SHIJIAN_RELEASE_KEY_ALIAS="shijian-release"
export SHIJIAN_RELEASE_KEY_PASSWORD="…"

JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:testDebugUnitTest :app:assembleRelease'
```

把 `android/app/build/outputs/apk/release/app-release.apk` 上传为 GitHub Release 附件，命名必须是 `Shijian-v<versionName>-<versionCode>-release.apk`，标签必须是 `v<versionName>`。GitHub 会在 Release API 提供附件的 `sha256` 摘要；App 会拒绝没有摘要、资产名称/地址异常、包信息不匹配或签名证书不同的更新。安装绝不会静默执行：用户要先在 App 中确认下载，再在 Android 系统安装页确认安装。

第一版正式签名包不能覆盖 Debug 签名的旧 APK。测试用户需先卸载 Debug APK，再安装正式包并重新登录；之后使用同一 keystore 签名的版本可以正常覆盖升级。

## 本地 H5 PoC

```bash
python3 -m poc.server
```

打开 `http://127.0.0.1:8765`。H5 页面中的 FNS API token 只保留在当前内存中，不会写入浏览器存储。

## 部署

Docker Compose、PocketBase 管理和日常维护说明见 [deploy/README.md](deploy/README.md)。若希望让 AI 代理连接 VPS 完成 Docker 与 Nginx 部署，请使用 [deploy/AI_DEPLOYMENT.md](deploy/AI_DEPLOYMENT.md)。不要提交 `.env`、FNS token 或签名密钥。
