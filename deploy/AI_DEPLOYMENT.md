# AI 代理 VPS 部署手册（Docker + Nginx）

此文件用于让 Codex 等 AI 代理执行拾笺的首次部署或版本升级。它约束代理的执行范围，避免猜测 VPS、域名、镜像仓库或覆盖已有服务。

## 必须先向用户确认的输入

开始任何远程写入前，代理必须取得并复述以下信息：

1. VPS 的 SSH 连接别名或主机地址，以及明确的部署目录；不要猜测服务器。
2. 已经解析到该 VPS 公网 IP 的 API 域名，例如 `clip.example.com`。代理应以 `dig +short` 或等效方式确认解析结果包含该 VPS IP；若 DNS 尚未生效，应暂停在这里，不能代为修改 DNS。
3. Docker 镜像仓库命名空间，以及是否允许代理推送镜像。生产环境必须使用不可变镜像标签。
4. 新的 PocketBase 管理员邮箱、强密码和 `FNS_ENCRYPTION_KEY`。这些仅写入远程 `.env`，不得显示、提交或回传。
5. 是否需要将 PocketBase 管理界面公开到独立域名。默认不公开：PocketBase 只监听 `127.0.0.1:18081`，通过 SSH 隧道管理。

若用户没有提供域名，或域名尚未解析到目标 VPS，代理只能完成本地构建与远程预检，不能配置 Nginx/TLS。

## 当前项目的生产拓扑

`deploy/compose.vps.yaml` 使用 Linux 主机网络：

- API：`127.0.0.1:18080`
- PocketBase：`127.0.0.1:18081`
- Worker：无公网端口
- Nginx：唯一对外入口，转发 API 域名到 `127.0.0.1:18080`

因此不要将 18080 或 18081 加入防火墙公网规则，也不要在未获得明确授权时删除 Docker 容器、卷、Nginx 站点或 DNS 记录。

## 代理执行流程

### 1. 预检与回滚点

1. 读取目标 VPS 的 Docker、Docker Compose、Nginx、可用磁盘和端口 80/443 状态。
2. 读取已有部署目录中的 `compose.vps.yaml` 与 `.env`，只报告非敏感字段；若已有服务，记录当前 `APP_IMAGE` 和 `POCKETBASE_IMAGE` 作为回滚版本。
3. 在本地运行项目测试；macOS 构建给 x86 VPS 时必须使用 `linux/amd64`。
4. 确认本次版本对应的 Git 短提交号，并把它用作镜像不可变 tag。

### 2. 构建并推送镜像

在仓库根目录构建 API 和 PocketBase 镜像。将占位符替换为用户确认的镜像地址与不可变 tag：

```bash
docker build --platform linux/amd64 \
  -f backend/Dockerfile \
  -t <registry>/shijian-api:<git-short-sha> .
docker build --platform linux/amd64 \
  -f deploy/pocketbase/Dockerfile \
  -t <registry>/shijian-pocketbase:<git-short-sha> .
docker push <registry>/shijian-api:<git-short-sha>
docker push <registry>/shijian-pocketbase:<git-short-sha>
```

### 3. 在 VPS 部署 Docker 服务

1. 在用户指定目录保存 `deploy/compose.vps.yaml`，并创建权限为 `600` 的 `.env`：

   ```dotenv
   APP_IMAGE=<registry>/shijian-api:<git-short-sha>
   POCKETBASE_IMAGE=<registry>/shijian-pocketbase:<git-short-sha>
   POCKETBASE_ADMIN_EMAIL=<secret>
   POCKETBASE_ADMIN_PASSWORD=<secret>
   FNS_ENCRYPTION_KEY=<secret>
   ```

2. 仅拉取和重建本项目服务：

   ```bash
   docker compose -f compose.vps.yaml --env-file .env pull
   docker compose -f compose.vps.yaml --env-file .env up -d
   docker compose -f compose.vps.yaml --env-file .env ps
   curl -fsS http://127.0.0.1:18080/healthz
   ```

3. 若失败，恢复预检时记录的两个镜像 tag，再次执行 `pull` 和 `up -d`；不要删除 `pocketbase_data` 卷。

### 4. 配置 Nginx 与 HTTPS

在域名已确认解析后，将 [Nginx HTTP 模板](nginx/shijian-api.http.conf.template) 中的 `__API_DOMAIN__` 替换为用户给出的 API 域名，写入 Nginx 站点目录。先执行 `nginx -t`，确认通过后才 reload Nginx。

模板把 API 代理到本机 `127.0.0.1:18080`。随后使用目标服务器既有的证书方式签发 HTTPS；若采用 Certbot，可在 HTTP 站点已加载后执行：

```bash
certbot --nginx -d <api-domain> --redirect
```

最后从 VPS 外部验证：

```bash
curl -fsS https://<api-domain>/healthz
```

应返回 `{"status":"ok"}`。若证书签发或公网检查失败，保留服务和日志，报告 DNS、端口 80/443、防火墙或证书错误；不要绕过 TLS，也不要猜测修改其他站点。

## 验收与交付

代理完成后必须报告：部署的 Git 提交与镜像 tag、容器状态、内网与公网 `/healthz` 结果、Nginx 配置检查结果，以及可用的回滚 tag。任何密钥、密码、FNS token、SSH 私钥或完整 `.env` 内容都不得出现在输出中。
