# 拾笺 v0.3.0 线上测试手册

本文档用于在真实环境（VPS 部署 + Android/iOS 客户端 + Obsidian 桌面/移动端）中端到端验证 FNS → Obsidian 插件同步改造是否正常工作。

适用范围：v0.3.0 破坏性版本，覆盖 `/v1/sync/*` 新接口、附件上传 `/v1/clips/files`、Obsidian 同步插件全部行为。

---

## 准备工作

### 必备条件

- [ ] 一台公网 VPS，已开放 TCP 80、443，已配置解析到该 VPS 的域名（如 `wechat.example.com`）
- [ ] 本地仓库（worktree `.worktrees/fns-to-plugin/`），分支 `feat/fns-to-plugin`
- [ ] VPS 上已安装 Docker 与 Docker Compose
- [ ] 一个或多个真实微信公众号文章 URL（公开可访问的 `https://mp.weixin.qq.com/s/...`）
- [ ] 桌面端 Obsidian（macOS/Windows/Linux 任一），用于安装本地构建的插件
- [ ] （可选）Android 设备 + 调试 APK
- [ ] （可选）iPhone + Safari，用于测 PWA + 快捷指令

### 构建产物清单

在本地 worktree 完成以下构建：

```bash
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin

# 1. Obsidian 插件（产出 main.js）
cd obsidian-plugin && npm install && npm run build && cd ..

# 2.（可选）Android 调试 APK
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
sh -c 'cd android && ./gradlew :app:assembleDebug'
# 产物：android/app/build/outputs/apk/debug/app-debug.apk

# 3. 跑一遍 Python 测试确认本地代码 OK
source .venv/bin/activate && PYTHONPATH=$(pwd) python -m pytest backend/tests tests
```

---

## 第一阶段：VPS 部署

### 1.1 推送代码到 VPS

把 `feat/fns-to-plugin` 分支推到 GitHub，然后在 VPS 上拉取：

```bash
# 本地
git push origin feat/fns-to-plugin

# VPS（SSH 登录后）
cd /path/to/shijian-deploy-dir
git fetch origin && git checkout feat/fns-to-plugin && git pull
```

### 1.2 配置 .env

在 VPS 的部署目录里编辑 `deploy/.env`（权限 600）。v0.3.0 已移除 `FNS_ENCRYPTION_KEY`：

```dotenv
DOMAIN=wechat.example.com
POCKETBASE_ADMIN_EMAIL=admin@your-domain.com
POCKETBASE_ADMIN_PASSWORD=<生成一个 32 位长密码>
WORKER_POLL_INTERVAL_SECONDS=2
```

> 不再需要 `FNS_ENCRYPTION_KEY`，也不需要 Fernet 密钥。如果你升级旧部署，请从 `.env` 里删除该行。

### 1.3 启动服务

```bash
cd /path/to/shijian-deploy-dir
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
```

**预期**：
- 4 个容器 Up：`caddy`、`pocketbase`（healthy）、`api`、`worker`
- 首次启动会自动应用两个新 migration：
  - `1710000005_create_notes_table.js`（创建 notes collection）
  - `1710000006_drop_fns_settings.js`（删除 fns_settings collection）

### 1.4 健康检查

```bash
# 内网（VPS 上）
curl -fsS http://localhost/healthz
# 预期：{"status":"ok"}

# 外网（你本地的电脑）
curl -fsS https://wechat.example.com/healthz
# 预期：{"status":"ok"}
```

如果外网失败，检查：DNS 是否解析到 VPS IP、Caddy 是否已签发证书（看 `docker logs deploy-caddy-1`）、防火墙是否放行 80/443。

### 1.5 创建首个邀请码

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env exec api \
  python -m backend.scripts.create_invite
```

**记下输出的一行邀请码**（如 `a7ahgCv1_15twPD_hBt8axij`），数据库只保存其 SHA-256 哈希，关掉终端就找不回了。

---

## 第二阶段：后端 API 链路验证

> 目的：用 curl 把所有新接口跑一遍，确认后端契约正确，再上客户端。

### 2.1 注册 + 登录

```bash
BASE=https://wechat.example.com
INVITE=<上一步生成的邀请码>

# 注册
curl -fsS -X POST "$BASE/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$INVITE\",\"email\":\"test@example.com\",\"password\":\"long-password-123\"}"
# 预期：{"id":"...","email":"test@example.com"}

# 登录拿 token
TOKEN=$(curl -fsS -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"long-password-123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "TOKEN=$TOKEN"
```

### 2.2 提交文章 URL（触发抓取任务）

```bash
curl -fsS -X POST "$BASE/v1/clips" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://mp.weixin.qq.com/s/<你的测试文章ID>"}'
# 预期：{"id":"task-...","status":"queued","source_url":"..."}

# 查任务列表（等待 5-15 秒让 worker 处理）
sleep 15
curl -fsS "$BASE/v1/clips" -H "Authorization: Bearer $TOKEN"
# 预期：status 从 queued → processing → succeeded，title/path 字段被填
```

如果 `status` 停在 `failed`：
- `error_stage=validate`：URL 不是 `mp.weixin.qq.com/s*` 开头
- `error_stage=fetch`：抓取失败，看 `docker logs deploy-worker-1`（可能是文章被删、反爬、网络）
- `error_stage=worker`：未知异常，看 worker 日志栈

### 2.3 插件视角：拉取已抓取的笔记

模拟 Obsidian 插件每 5 秒调用的接口：

```bash
# 首次拉取（cursor 为空）
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期响应：
# {
#   "notes": [{
#     "id":"...", "kind":"article",
#     "source_url":"https://mp.weixin.qq.com/s/...",
#     "title":"<文章标题>",
#     "filename":"<安全文件名>.md",
#     "content_md":"# 标题\n\n<Markdown 正文>",
#     "images":["https://mmbiz.qpic.cn/...", ...],
#     "attachment_filename":"", "attachment_mime":"",
#     "created":null
#   }],
#   "last_id":"<本批次最大 note id>",
#   "server_time":"2026-07-20T..."
# }
```

**关键检查点**：
- `notes[]` 含 `kind=article` 的条目
- `content_md` 是有效 Markdown
- `images[]` 含微信图片 URL（`mmbiz.qpic.cn`）
- 响应里**不含** `attachment_b64`（附件字节单独下载）
- 记下 `last_id`，下一步要用

### 2.4 确认同步（ack）

```bash
NOTE_ID=<上一步 notes[0].id>

curl -fsS -X POST "$BASE/v1/sync/ack" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"note_ids\":[\"$NOTE_ID\"]}"
# 预期：{"acked":1}

# ack 后再拉，应该看不到这条了
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期：notes 数组为空（或只有 ack 之后新产生的）
```

### 2.5 附件上传 + 下载链路

```bash
# 上传一个测试 PDF
echo "%PDF-1.4 test content" > /tmp/test.pdf
UPLOAD=$(curl -fsS -X POST "$BASE/v1/clips/files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.pdf;type=application/pdf")
echo "$UPLOAD"
# 预期：{"id":"...","filename":"test.pdf"}

ATT_ID=$(echo "$UPLOAD" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 拉取附件 note
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期：notes[] 里多一条 kind=attachment，attachment_filename="test.pdf"

# 下载附件字节
curl -fsS "$BASE/v1/sync/notes/$ATT_ID/attachment" \
  -H "Authorization: Bearer $TOKEN" -o /tmp/downloaded.pdf
diff /tmp/test.pdf /tmp/downloaded.pdf && echo "✅ 附件字节一致"

# ack 后再下载应该 404
curl -fsS -X POST "$BASE/v1/sync/ack" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"note_ids\":[\"$ATT_ID\"]}"

curl -i "$BASE/v1/sync/notes/$ATT_ID/attachment" -H "Authorization: Bearer $TOKEN"
# 预期：HTTP 404（字节已被清理）
```

### 2.6 用户隔离测试（重要）

注册第二个用户，确认看不到第一个用户的数据：

```bash
# 管理员授予第一个用户生成邀请码权限（可选，或直接用 backend.scripts.create_invite）
# 这里直接在 VPS 上生成第二个邀请码
INVITE2=$(docker compose -f deploy/compose.yaml --env-file deploy/.env exec -T api \
  python -m backend.scripts.create_invite | tail -1)

# 注册第二个用户
curl -fsS -X POST "$BASE/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$INVITE2\",\"email\":\"other@example.com\",\"password\":\"long-password-456\"}"

TOKEN2=$(curl -fsS -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"other@example.com","password":"long-password-456"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 第二个用户拉取，应该是空的
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN2"
# 预期：{"notes":[], ...}

# 第二个用户尝试下载第一个用户的附件 → 404
curl -i "$BASE/v1/sync/notes/$ATT_ID/attachment" -H "Authorization: Bearer $TOKEN2"
# 预期：HTTP 404
```

### 2.7 限流验证（可选）

```bash
# /v1/sync/* 限流：每 token 60 秒 30 次
for i in $(seq 1 35); do
  curl -s -o /dev/null -w "%{http_code} " "$BASE/v1/sync/changes" -H "Authorization: Bearer $TOKEN"
done
# 预期：前 30 个返回 200，之后返回 429
```

---

## 第三阶段：Obsidian 插件端到端

> 目的：用真实插件验证从同步到 Vault 写入的完整链路。

### 3.1 安装插件到 Vault

```bash
# 本地 worktree
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin/obsidian-plugin

# 确认 main.js 已生成
ls -lh main.js manifest.json

# 复制到 Obsidian Vault 的插件目录
VAULT_PLUGIN_DIR="<你的 Vault 路径>/.obsidian/plugins/shijian-sync"
mkdir -p "$VAULT_PLUGIN_DIR"
cp main.js manifest.json "$VAULT_PLUGIN_DIR/"
```

### 3.2 启用插件

1. 打开 Obsidian（建议先开一个**测试 Vault**，避免污染主 Vault）
2. 设置 → 第三方插件 → 关闭"安全模式"→ 启用「拾笺同步」
3. 点「拾笺同步」的设置图标

### 3.3 配置插件

在插件设置页填：

| 字段 | 值 |
|---|---|
| 后端服务地址 | `https://wechat.example.com` |
| 邮箱 | `test@example.com` |
| 密码 | `long-password-123` |
| 文章目录 | `公众号收藏`（或自定义） |
| 附件目录 | `公众号收藏/assets`（或自定义） |
| 轮询间隔（秒） | `5` |
| 自动同步 | 开启 |

### 3.4 提交新文章并观察同步

```bash
# VPS 或本地，提交一篇**新的**文章 URL（第二阶段 ack 过的不会再同步）
curl -fsS -X POST "$BASE/v1/clips" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://mp.weixin.qq.com/s/<新文章ID>"}'

# 等 worker 抓取（5-15 秒）
sleep 15
curl -fsS "$BASE/v1/clips" -H "Authorization: Bearer $TOKEN"
# 确认 status=succeeded
```

回到 Obsidian，**5 秒内**应该观察到：

1. 右上角出现 Notice：`拾笺已同步 1 篇`
2. Vault 左侧文件树出现新目录 `公众号收藏/`
3. 目录下出现 `<文章标题>.md`
4. 打开 .md 文件，内容结构：
   ```markdown
   ---
   title: "<标题>"
   source: "<原 URL>"
   clipped: ""
   shijian_id: "<note id>"
   ---

   # <标题>

   <Markdown 正文，图片链接已替换为本地相对路径>
   ```
5. `公众号收藏/assets/` 下出现图片文件（sha256 前 6 字符命名，如 `a1b2c3d4.jpg`）

### 3.5 验证同步后的状态

```bash
# 插件同步成功后，note 应该已 ack
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期：notes 数组为空（已交付）

# 在 PocketBase 管理后台查看（需 SSH 隧道）
# ssh -L 18081:127.0.0.1:18081 your-vps
# 浏览器打开 http://127.0.0.1:18081/_/ → notes 集合
# 该 note 的 delivered 字段应为 1（已交付）
```

### 3.6 附件同步验证

在 Obsidian 还开着的状态下，从客户端上传一个附件：

```bash
echo "测试附件内容" > /tmp/note.txt
curl -fsS -X POST "$BASE/v1/clips/files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/note.txt;type=text/plain"
```

5 秒内 Obsidian 应该：
1. Notice：`拾笺已同步 1 篇`
2. `公众号收藏/assets/` 下出现 `note.txt`

### 3.7 验证错误处理

测试几种失败场景：

**场景 A：图片下载失败（断网图片）**

提交一篇图片 URL 已失效的文章。预期：
- 文章 .md 仍写入 Vault
- 失败的图片保留**原始远程 URL**（不替换）
- 控制台（Ctrl+Shift+I）打印 `[shijian-sync] 图片下载失败:` 警告

**场景 B：后端临时不可用**

```bash
# VPS 上停掉 API
docker compose -f deploy/compose.yaml stop api
```

回到 Obsidian，等待下一次轮询：
- Notice：`网络错误，无法连接后端`
- 插件不停重试，恢复后自动追上

```bash
# 恢复
docker compose -f deploy/compose.yaml start api
```

**场景 C：账号密码错误**

在 Obsidian 插件设置里把密码改错一个字符，等下次轮询：
- Notice：`登录失败，请检查邮箱密码`
- 改回正确密码后恢复

### 3.8 移动端 Obsidian 验证（可选）

如果你在手机上也装了 Obsidian：
1. 把同一个测试 Vault 用 iCloud / Obsidian Sync 同步到手机
2. 手机端 Obsidian 也会启用插件，独立轮询
3. **注意**：两个设备可能同时 ack 同一条 note。服务端 ack 是幂等的（已交付的不重复计入），不会出错；但两端可能都尝试写入同一个 .md，因 `writeNote` 用 `vault.exists()` 去重，后写的一端会跳过

---

## 第四阶段：Android 客户端验证

### 4.1 安装调试 APK

```bash
# 本地 worktree 已构建
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

### 4.2 验证 FNS UI 已移除

打开「拾笺」App → 设置：
- ❌ 不应再看到 "Fast Note Sync" 标题
- ❌ 不应看到 FNS JSON 输入框、转存目录、附件目录输入框
- ❌ 不应看到"保存配置""检测连接"按钮
- ✅ 应看到"Obsidian 同步"说明卡片，引导用户安装插件
- ✅ 成员邀请、服务端切换、关于、检查更新等功能保留

### 4.3 系统分享 URL

1. 打开微信，进入一篇公众号文章
2. 右上角 ⋯ → 分享到「拾笺」
3. App 自动跳转，显示任务 queued
4. 主界面下拉刷新，等 status → succeeded
5. 回到 Obsidian，5 秒内文章应同步到 Vault

### 4.4 系统分享附件

1. 文件管理器选一个 PDF 或图片
2. 分享到「拾笺」
3. App 显示 Toast：`<filename> 已上传，等待 Obsidian 同步`
4. Obsidian 端 5 秒内出现该文件

---

## 第五阶段：iOS PWA + 快捷指令验证

### 5.1 PWA 安装

1. iPhone Safari 打开 `https://wechat.example.com`
2. 分享 → 添加到主屏幕
3. 桌面图标启动 App，登录

**验证项**：
- ❌ 设置页不应有 FNS 配置卡片
- ✅ 应有"Obsidian 同步"说明卡片
- ✅ URL 投递、附件上传、任务列表正常

### 5.2 快捷指令：URL 转存

按 README_CN 指南创建快捷指令「拾笺 URL 转存」：
- 接受类型：仅"链接"
- POST `https://wechat.example.com/v1/clips`
- Headers: `Content-Type: application/json`、`Authorization: Bearer <token>`
- Body JSON: `{"url":"快捷指令输入"}`

在微信里打开文章 → 分享 → 拾笺 URL 转存 → 任务入队。

### 5.3 快捷指令：附件转存

创建快捷指令「拾笺 附件转存」：
- 接受类型：仅"文件"和"图像"
- POST `https://wechat.example.com/v1/clips/files`（**注意：v0.3.0 改名了，不是 /v1/clips/attachments**）
- Headers: `Authorization: Bearer <token>`
- Body Form: `file` = 快捷指令输入

在文件管理器选文件 → 分享 → 拾笺 附件转存 → 上传成功。

---

## 第六阶段：升级老部署（仅老用户）

> 如果你已经在 v0.2.x 部署运行，按本节升级到 v0.3.0。

### 6.1 备份

```bash
# VPS 上备份 PocketBase 数据卷
docker compose -f deploy/compose.yaml --env-file deploy/.env stop
docker run --rm -v deploy_pocketbase_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/pb_data_backup_$(date +%Y%m%d).tar.gz /data
```

### 6.2 拉取新代码并清理 .env

```bash
git checkout feat/fns-to-plugin && git pull

# 编辑 deploy/.env，删除 FNS_ENCRYPTION_KEY 这一行
vi deploy/.env
```

### 6.3 启动（自动迁移）

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
```

启动时会自动应用 migration 005（建 notes 表）和 006（删 fns_settings 表）。老的 `clip_tasks` 数据保留，老的 `fns_settings` 数据**会被删除**。

### 6.4 老用户的 FNS 数据迁移

**注意**：v0.2.x 抓取过的文章的 Markdown 内容**不会自动迁移**到 notes 表，因为它们只存在 FNS Service 的存储里。如需让新插件重新同步这些文章：

1. 在 APK 任务列表里找到那些 `succeeded` 任务
2. 点「重试」（会让 worker 重新抓取并落 notes 表）
3. 等新插件轮询拉取

详见 [docs/migration-fns-to-plugin.md](migration-fns-to-plugin.md)。

### 6.5 卸载 FNS Service

确认新插件工作正常后，可以：
- 在 Obsidian 禁用并卸载 Fast Note Sync 插件
- 停止 FNS Service 进程（不再需要）

---

## 常见问题排查

### Q1：sync/changes 一直返回空，但 clip_tasks 显示 succeeded

**原因 1**：cursor 卡住了。检查 Obsidian 插件目录 `.obsidian/plugins/shijian-sync/data.json`，看 `lastSyncCursor` 是否指向一个不存在的 id。

**解决**：删除 `data.json`（或手动改 `lastSyncCursor` 为 `""`），重启插件，会从头拉取所有未交付的 note。

**原因 2**：worker 没把文章落 notes 表。在 VPS 上：
```bash
docker compose -f deploy/compose.yaml logs worker --tail 50
```
看是否有 error_stage。

### Q2：Obsidian Notice 显示"登录失败"

- 检查插件设置里的邮箱密码是否正确
- 检查 `access_expires_at` 是否过期（PocketBase 管理后台 `users` 集合查看）
- 在 VPS 测试登录：`curl -X POST $BASE/v1/auth/login -H "Content-Type: application/json" -d '{...}'`

### Q3：文章写入了 Vault，但图片是远程 URL（没下载到本地）

**原因**：图片下载失败。打开 Obsidian 控制台（Ctrl+Shift+I）看 `[shijian-sync] 图片下载失败:` 警告，常见原因：
- 微信图片 URL 失效（CDN 时效）
- 网络问题
- 图片需要 Referer 头（当前实现没带，可能被微信拒绝）

**临时解决**：手动下载图片到 `公众号收藏/assets/`，在 .md 里替换 URL。

### Q4：附件下载返回 404

**原因**：附件 note 已被 ack，服务端清空了 `attachment_b64` 释放空间。这是设计行为——附件只保留到首次成功同步。

**解决**：重新上传附件（`POST /v1/clips/files`）。

### Q5：PocketBase 启动失败，报 migration 错误

查看具体错误：
```bash
docker compose -f deploy/compose.yaml logs pocketbase --tail 30
```

常见情况：
- `no such column: created`：说明你跑的是旧版 migration（索引引用了 created 字段）。确认代码已更新到最新 commit
- `Failed to create index`：同上
- `bool field required`：说明 migration 005 还在用 `required: true`，确认已更新

如果数据库损坏，可以重建（**会丢所有用户数据**）：
```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env down -v
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d
```

### Q6：Android APK 上传附件后 Obsidian 没反应

- 确认 Obsidian 桌面端开着（插件只在 App 运行时轮询）
- 确认插件设置里"自动同步"开启
- 点 Obsidian 左侧栏的拾笺图标（或命令面板 → "拾笺同步：立即同步"）手动触发
- 看控制台是否有错误

### Q7：v0.3.0 老用户报"邀请码无效"

v0.3.0 的注册流程不变，邀请码逻辑相同。但如果你重建了数据库（down -v），所有邀请码和用户都丢了，需要重新生成。

---

## 验收清单

完成全部阶段后，对照下表打勾：

### 后端
- [ ] `curl https://<域名>/healthz` 返回 ok
- [ ] 注册新用户成功
- [ ] 登录拿到 token
- [ ] POST /v1/clips 任务从 queued → succeeded
- [ ] GET /v1/sync/changes 返回文章 Markdown + 图片清单
- [ ] POST /v1/sync/ack 后再拉为空
- [ ] POST /v1/clips/files 上传附件成功
- [ ] GET /v1/sync/notes/{id}/attachment 下载字节一致
- [ ] ack 后附件字节清理（再下载 404）
- [ ] 用户隔离：B 看不到 A 的数据
- [ ] 限流：超过 30 次/分钟返回 429

### Obsidian 插件
- [ ] 插件在 Obsidian 第三方插件列表中出现
- [ ] 设置页 8 个字段可配置
- [ ] 自动轮询：5 秒内同步新文章
- [ ] 文章 .md 出现在 `公众号收藏/`，frontmatter 完整
- [ ] 图片下载到 `公众号收藏/assets/`，URL 替换为本地路径
- [ ] 附件同步到 `公众号收藏/assets/`
- [ ] ribbon 图标 + "立即同步"命令可用
- [ ] 失败场景：网络断开 → Notice 错误；恢复后追上
- [ ] 失败场景：密码错误 → Notice"登录失败"
- [ ] cursor 持久化：Obsidian 重启后从上次位置继续

### Android 客户端
- [ ] APK 安装成功
- [ ] 设置页无 FNS UI，有 Obsidian 同步说明卡片
- [ ] 系统分享 URL → 任务入队 → succeeded
- [ ] 系统分享附件 → Toast "已上传，等待 Obsidian 同步"
- [ ] 任务列表显示历史

### iOS PWA + 快捷指令
- [ ] Safari 添加到主屏幕后 PWA 启动正常
- [ ] PWA 设置页无 FNS UI
- [ ] 快捷指令 URL 转存可用（POST /v1/clips）
- [ ] 快捷指令附件转存可用（POST /v1/clips/files）

### 升级（仅老用户）
- [ ] 升级前数据库已备份
- [ ] 升级后 .env 已删除 FNS_ENCRYPTION_KEY
- [ ] migration 005/006 自动应用成功
- [ ] 老用户能登录，使用期限保留
- [ ] FNS Service 已卸载

---

## 紧急回滚

如果 v0.3.0 出现严重问题，回滚到 v0.2.x：

```bash
# VPS 上
docker compose -f deploy/compose.yaml --env-file deploy/.env down

# 切回主分支（v0.2.x 代码）
git checkout main

# 恢复 .env 里的 FNS_ENCRYPTION_KEY（从密码管理器找）
vi deploy/.env

# 用备份恢复 PocketBase 数据（migration 006 已删了 fns_settings，需恢复）
docker volume rm deploy_pocketbase_data
docker volume create deploy_pocketbase_data
docker run --rm -v deploy_pocketbase_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/pb_data_backup_<日期>.tar.gz -C /

# 启动旧版
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
```

回滚后客户端需要：
- Android：卸载 v0.3.0 APK，装回 v0.2.x
- Obsidian：禁用 shijian-sync 插件，重新启用 FNS 插件
