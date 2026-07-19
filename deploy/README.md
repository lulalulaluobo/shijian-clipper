# 个人部署与分发

这个部署会启动 PocketBase、Python API、顺序 Worker 和 Caddy。只有 Caddy 对外开放；APK 只访问你的 HTTPS 域名，不会直接访问 PocketBase。

## 首次部署

1. 给 VPS 配置一个域名 A/AAAA 记录，并放行 TCP 80、443。
2. 在仓库根目录复制配置：`cp deploy/.env.example deploy/.env`。
3. 在 `deploy/.env` 填写 `DOMAIN`、一个新的管理员邮箱/长密码，并生成 Fernet 密钥：

   ```sh
   python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   将输出填入 `FNS_ENCRYPTION_KEY`。这个值丢失后，已保存的 FNS token 无法解密；请备份到密码管理器。
4. 启动服务：`docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build`。
5. 等待 Caddy 签发证书后访问 `https://你的域名/healthz`，应得到 `{"status":"ok"}`。

## 创建邀请码

邀请码只在创建时显示一次，数据库只保存它的 SHA-256 哈希。每个注册码只能成功注册一次。

```sh
docker compose -f deploy/compose.yaml --env-file deploy/.env exec api python -m backend.scripts.create_invite
```

把输出的完整字符串单独发给用户。用户首次打开 APK 时填入服务地址、邀请码、邮箱和密码；之后只需登录。

## 构建 APK

在有 Android SDK 的机器上执行：

```sh
gradle -p android :app:assembleDebug
```

产物在 `android/app/build/outputs/apk/debug/app-debug.apk`。这是调试签名包；正式分发前请配置自己的 release 签名，并把后端域名告知用户。

## 日常运维

- 查看运行状态：`docker compose -f deploy/compose.yaml --env-file deploy/.env ps`
- 查看日志：`docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f api worker`
- 用户 FNS 配置由 API 以 `FNS_ENCRYPTION_KEY` 加密保存，API 响应、任务记录和 APK 均不回显 token。
- 首版仅允许微信公众号文章 URL，Worker 单进程顺序处理。图片保持原始 URL；不会下载或上传图片。
