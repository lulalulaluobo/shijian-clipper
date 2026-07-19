# Shijian · 拾笺

[English](README.md)

拾笺是一个将个人信息转存到 Obsidian 的工具。将微信公众号文章从系统分享面板发送到 Android App，或粘贴文章链接，服务端便会抓取文章、转为 Markdown，并写入你自己的 Fast Note Sync 仓库。产品后续可逐步扩展到文本、图片及更多信息类型。

建议的 GitHub 仓库名：`shijian-clipper`。

## Android App

- 应用名：拾笺（Shijian）
- 默认服务：`https://wechat.lucc.fun`
- 自部署：在「设置」中修改服务地址，然后重新登录。
- 输入：在系统分享面板分享微信公众号文章，或粘贴 HTTPS 文章链接。
- 输出：文章 Markdown 会写入配置的 Fast Note Sync 仓库与 Obsidian 目录；图片保留原始链接。
- 状态：任务排队或执行时，首页会自动刷新状态；完成、失败后会停止刷新并显示最终状态。

账户通过邀请码注册。邀请码在注册前不会过期；注册后默认可使用 30 天。PocketBase 管理员可在 `users` 集合编辑 `access_expires_at`，延长指定用户的使用期限。

## 构建 APK

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug'
```

Debug APK 位于 `android/app/build/outputs/apk/debug/app-debug.apk`。

## 本地 H5 PoC

```bash
python3 -m poc.server
```

打开 `http://127.0.0.1:8765`。H5 页面中的 FNS API token 只保留在当前内存中，不会写入浏览器存储。

## 部署

Docker Compose、PocketBase 管理和日常维护说明见 [deploy/README.md](deploy/README.md)。若希望让 AI 代理连接 VPS 完成 Docker 与 Nginx 部署，请使用 [deploy/AI_DEPLOYMENT.md](deploy/AI_DEPLOYMENT.md)。不要提交 `.env`、FNS token 或签名密钥。
