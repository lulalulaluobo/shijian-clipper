# 个人部署与分发

这个部署会启动 PocketBase、Python API、顺序 Worker 和 Caddy。只有 Caddy 对外开放；APK 只访问你的 HTTPS 域名，不会直接访问 PocketBase。

## 首次部署

1. 给 VPS 配置一个域名 A/AAAA 记录，并放行 TCP 80、443。
2. 在仓库根目录复制配置：`cp deploy/.env.example deploy/.env`。
3. 在 `deploy/.env` 填写 `DOMAIN` 和一个新的 PocketBase 管理员邮箱/长密码。
4. 启动服务：`docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build`。
5. 等待 Caddy 签发证书后访问 `https://你的域名/healthz`，应得到 `{"status":"ok"}`。

## 创建邀请码

命令行创建的邀请码只在创建时显示一次，数据库只保存它的 SHA-256 哈希。每个注册码只能成功注册一次。用户在 APK 内生成的邀请码会同时保存 `code` 和 SHA-256 `code_hash`，便于超级管理员在 PocketBase 中管理。

```sh
docker compose -f deploy/compose.yaml --env-file deploy/.env exec api python -m backend.scripts.create_invite
```

把输出的完整字符串单独发给用户。用户首次打开 APK 时填入服务地址、邀请码、邮箱和密码；之后只需登录。

## 用户期限与邀请权限

- 邀请码被首次注册后，用户默认获得 30 天使用期限。
- 在 PocketBase 的 `users` 集合编辑 `access_expires_at` 可调整该用户的到期时间。
- 在 `users` 集合将 `can_create_invites` 设为 `true`，该用户即可在 APK「设置 → 成员邀请」生成一次性邀请码。

## 构建 APK

在有 Android SDK 的机器上执行：

```sh
gradle -p android :app:assembleDebug
```

产物在 `android/app/build/outputs/apk/debug/app-debug.apk`。这是调试签名包；正式分发前请配置自己的 release 签名，并把后端域名告知用户。

正式发布请遵循仓库根目录 [README](../README.md#build-and-publish-a-signed-release) 的签名构建流程。APK 内的更新功能只接受同一 GitHub 仓库中、与安装包使用相同签名证书的正式 Release；用户确认下载后，Android 系统仍会再次确认安装。

## 日常运维

- 查看运行状态：`docker compose -f deploy/compose.yaml --env-file deploy/.env ps`
- 查看日志：`docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f api worker`
- 用户不再需要服务端配置；文章由后端抓取后，等待 Obsidian 插件轮询同步到本地 Vault。
- Worker 单进程顺序处理；图片 URL 由插件下载到本地 Vault。

## Obsidian 插件同步

用户在 Obsidian 中安装 `shijian-sync` 插件即可把抓取到的文章同步到本地 Vault。插件源码位于仓库的 [`obsidian-plugin/`](../obsidian-plugin/) 目录，构建后把 `main.js` 和 `manifest.json` 复制到 Obsidian Vault 的 `.obsidian/plugins/shijian-sync/` 目录，然后在 Obsidian 设置的第三方插件里启用「拾笺同步」。

在插件设置页填后端服务地址、注册时的邮箱和密码，即可开始同步。插件每 5 秒轮询 `/v1/sync/changes` 拉取新内容，写入 Vault 后通过 `/v1/sync/ack` 确认。详细使用说明见仓库根目录 [README_CN.md](../README_CN.md#obsidian-同步插件)。
