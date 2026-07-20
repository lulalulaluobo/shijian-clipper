# 拾笺 v0.3.0 本地测试手册

本文档用于在**你的 Mac 本地**完整测试 v0.3.0 的同步链路：本地 Docker 后端 + 本地 Obsidian 插件 + 真实公众号文章。

不需要 VPS，全程在 Mac 上完成。

---

## ⚠️ 重要前置说明

### 你的环境现状

- Obsidian Vault：`/Users/luluen/Documents/obsidian/`
- 已启用 FNS 插件，指向 `https://obsync.lucc.fun`，正在同步 153+ 篇笔记
- 本地端口 80 被占用（其他服务）

### 测试期间必须注意的两件事

1. **FNS 与新插件会冲突**：FNS 也在同步整个 Vault。测试期间必须**临时禁用 FNS 插件**（不是卸载，是 Obsidian 设置里关闭开关），否则两个插件会同时改文件，行为不可预测。测完可以再开回来。

2. **测试目录建议隔离**：新插件默认把文章写到 `公众号收藏/`。你的 Vault 已经有 `00_Inbox/微信公众号/`（FNS 写的）。建议插件配置时**用一个新的测试目录名**（如 `shijian-test`），测完手动删除该目录即可，不污染主 Vault。

   或者更稳的做法：建一个**测试 Vault**（见末尾「方案 B」）。

---

## 准备工作

### 工具检查

```bash
# Docker
docker --version  # 需要 ≥ 20.x
docker compose version  # 需要 v2+

# Node（构建插件用）
node --version  # 需要 ≥ 18

# Python（跑测试用）
python3 --version  # 需要 ≥ 3.10

# Obsidian 桌面端已安装
ls /Applications/Obsidian.app
```

### 找一篇测试文章

准备一篇**真实的、公开可访问的**微信公众号文章 URL（你自己常看的公众号任意一篇都行）：
```
https://mp.weixin.qq.com/s/<文章ID>
```

记下这个 URL，后面要用。

---

## 第一步：启动本地后端

### 1.1 进入 worktree

```bash
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin
```

### 1.2 配置 .env（如已存在可跳过）

```bash
ls deploy/.env 2>/dev/null && echo "已存在" || cat > deploy/.env <<'EOF'
DOMAIN=localhost
POCKETBASE_ADMIN_EMAIL=admin@shijian.local
POCKETBASE_ADMIN_PASSWORD=local-test-long-pwd-12345
WORKER_POLL_INTERVAL_SECONDS=2
EOF
chmod 600 deploy/.env
```

> 本地测试**不需要** `FNS_ENCRYPTION_KEY`（v0.3.0 已移除）。

### 1.3 启动服务

在本地测试中，`deploy/compose.yaml` 默认会将 API 服务暴露在 `http://127.0.0.1:18000`，PocketBase 暴露在 `http://127.0.0.1:18090`。

```bash
# 先清理任何残留
docker compose -f deploy/compose.yaml --env-file deploy/.env down -v 2>&1 | tail -3

# 启动服务
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build 2>&1 | tail -10
```

**预期**：3 个容器 Up，`pocketbase` 显示 `healthy`。

### 1.4 健康检查

```bash
# 等约 5 秒让 PocketBase 状态变为 healthy
sleep 5

# 直接测试 API 健康状态
curl -fsS http://localhost:18000/healthz
# 预期：{"status":"ok"}
```

现在后端地址是 `http://localhost:18000`。

### 1.7 生成首个邀请码

```bash
INVITE=$(docker compose -f deploy/compose.yaml --env-file deploy/.env \
  exec -T api python -m backend.scripts.create_invite 2>&1 | tail -1 | tr -d '[:space:]')
echo "邀请码: $INVITE"
# 记下这个邀请码，例如：j_YbsfaPqgRGicJ1QCOZkh3f
```

---

## 第二步：curl 验证后端链路

> 在装插件之前，先用 curl 把接口跑一遍，确认后端没问题。

### 2.1 注册并登录

```bash
BASE=http://localhost:18000

# 注册
curl -fsS -X POST "$BASE/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$INVITE\",\"email\":\"local@test.com\",\"password\":\"long-password-123\"}"
# 预期：{"id":"...","email":"local@test.com"}

# 登录拿 token
TOKEN=$(curl -fsS -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"local@test.com","password":"long-password-123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "TOKEN=$TOKEN"
```

### 2.2 提交文章并等待抓取

```bash
# 替换为你准备的真实公众号文章 URL
ARTICLE_URL="https://mp.weixin.qq.com/s/<你的文章ID>"

curl -fsS -X POST "$BASE/v1/clips" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"url\":\"$ARTICLE_URL\"}"
# 预期：{"id":"task-...","status":"queued","source_url":"..."}

# 等 worker 抓取（10-20 秒）
sleep 20

# 查任务状态
curl -fsS "$BASE/v1/clips" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# 预期：status=succeeded，title 字段填了文章标题
```

**如果 status=failed**：
```bash
# 看错误
docker compose -f deploy/compose.yaml --env-file deploy/.env logs worker --tail 30
```
常见原因：
- `validate`：URL 格式不对，必须是 `https://mp.weixin.qq.com/s*`
- `fetch`：抓取失败，可能文章被删/反爬/网络
- `extract`：页面结构异常，HTML parser 没找到正文

### 2.3 验证插件拉取接口

```bash
curl -fsS "$BASE/v1/sync/changes?limit=50" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**预期响应**：
```json
{
  "notes": [{
    "id": "<15字符 base32 id>",
    "kind": "article",
    "source_url": "https://mp.weixin.qq.com/s/...",
    "title": "<文章标题>",
    "filename": "<安全文件名>.md",
    "content_md": "# <标题>\n\n<Markdown 正文>",
    "images": ["https://mmbiz.qpic.cn/...", ...],
    "attachment_filename": "",
    "attachment_mime": "",
    "created": null
  }],
  "last_id": "<本批次最大 note id>",
  "server_time": "2026-07-20T..."
}
```

记下 `notes[0].id`，下一步要用。

### 2.4 测试 ack

```bash
NOTE_ID=<上一步拿到的 id>

curl -fsS -X POST "$BASE/v1/sync/ack" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"note_ids\":[\"$NOTE_ID\"]}"
# 预期：{"acked":1}

# ack 后再拉，应该空了
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期：{"notes":[], ...}
```

> 注意：如果你现在 ack 了，后面插件测试时就拉不到这条了。如果想给插件留一条测，**跳过本步**，直接进第三步。

---

## 第三步：安装 Obsidian 插件

### 3.1 ⚠️ 先禁用 FNS 插件

打开 Obsidian → 设置 → 第三方插件 → 找到 `Fast Note Sync` → **关闭开关**（不是卸载）。

**不要**卸载 FNS 插件，测完还要开回来继续同步你原来的笔记。

### 3.2 复制插件文件

```bash
PLUGIN_DIR="/Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync"
mkdir -p "$PLUGIN_DIR"

cp /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin/obsidian-plugin/main.js "$PLUGIN_DIR/"
cp /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin/obsidian-plugin/manifest.json "$PLUGIN_DIR/"

ls -la "$PLUGIN_DIR/"
# 预期：main.js + manifest.json 两个文件
```

### 3.3 在 Obsidian 启用插件

1. Obsidian → 设置 → 第三方插件
2. 找到「拾笺同步」（如果没看到，按 Ctrl/Cmd+R 重启 Obsidian）
3. **开启开关**

**如果提示"插件加载失败"**：
```bash
# 看 Obsidian 控制台（Ctrl/Cmd+Option+I）
# 常见原因：main.js 没复制对，或 manifest.json 的 minAppVersion 高于你的 Obsidian 版本
cat "$PLUGIN_DIR/manifest.json"
```

### 3.4 配置插件

Obsidian → 设置 → 拾笺同步，按以下填：

| 字段 | 值 |
|---|---|
| 后端服务地址 | `http://localhost:18000` |
| 邮箱 | `local@test.com` |
| 密码 | `long-password-123` |
| 文章目录 | `shijian-test`（**用测试目录，不污染主 Vault**） |
| 附件目录 | `shijian-test/assets` |
| 轮询间隔（秒） | `5` |
| 自动同步 | 开启 |

---

## 第四步：观察同步

### 4.1 提交新文章

如果第二步你 ack 了那条文章，现在需要提交一篇新的：

```bash
ARTICLE_URL2="https://mp.weixin.qq.com/s/<另一篇文章ID>"

curl -fsS -X POST "$BASE/v1/clips" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"url\":\"$ARTICLE_URL2\"}"

sleep 20
curl -fsS "$BASE/v1/clips" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# 确认 status=succeeded
```

### 4.2 回到 Obsidian 观察

5 秒内你应该看到：

1. **右上角 Notice**：`拾笺已同步 1 篇`
2. **左侧文件树**：出现新目录 `shijian-test/`
3. **目录下**：出现 `<文章标题>.md`
4. **打开文件**，内容应该是：
   ```markdown
   ---
   title: "<文章标题>"
   source: "https://mp.weixin.qq.com/s/..."
   clipped: ""
   shijian_id: "<note id>"
   ---

   # <文章标题>

   <正文 Markdown>

   ![](shijian-test/assets/a1b2c3d4.jpg)
   ```
5. **`shijian-test/assets/`** 下出现下载的图片（sha256 前 6 字节命名）

### 4.3 验证 ack 状态

回到终端：

```bash
curl -fsS "$BASE/v1/sync/changes?limit=50" -H "Authorization: Bearer $TOKEN"
# 预期：{"notes":[], ...}（插件已自动 ack）
```

在 PocketBase 里看（可选）：

```bash
# 启动 PocketBase 管理界面（容器里直接跑）
docker compose -f deploy/compose.yaml --env-file deploy/.env exec -T pocketbase \
  /pb/pocketbase admin serve --http=0.0.0.0:8090 &

# 浏览器打开 http://localhost:8090/_/
# 用 admin@shijian.local / local-test-long-pwd-12345 登录
# notes 集合 → 该 note 的 delivered 字段应为 1
```

---

## 第五步：测附件上传

### 5.1 curl 上传

```bash
echo "测试附件内容" > /tmp/test-attachment.txt

curl -fsS -X POST "$BASE/v1/clips/files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test-attachment.txt;type=text/plain"
# 预期：{"id":"...","filename":"test-attachment.txt"}
```

### 5.2 Obsidian 端观察

5 秒内：
1. Notice：`拾笺已同步 1 篇`
2. `shijian-test/assets/` 下出现 `test-attachment.txt`

打开文件确认内容是 `测试附件内容`。

---

## 第六步：测错误场景

### 6.1 网络断开

```bash
# 停掉后端
docker compose -f deploy/compose.yaml --env-file deploy/.env stop api
```

回到 Obsidian，等 5-10 秒（下一次轮询）：
- Notice：`网络错误，无法连接后端`

控制台（Ctrl/Cmd+Option+I）会看到错误堆栈。

恢复：
```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env start api
```

下次轮询应自动恢复。

### 6.2 密码错误

在插件设置里把密码改一个字符，保存。等下次轮询：
- Notice：`登录失败，请检查邮箱密码`

改回正确密码，恢复。

### 6.3 图片下载失败

找一篇带**已过期图片**的文章（或手动改 markdown 里的图片 URL 为无效地址）：
- 文章仍写入 Vault（不阻塞）
- 失败图片保留**原始远程 URL**（不替换）
- 控制台警告：`[shijian-sync] 图片下载失败:`

### 6.4 cursor 卡住

如果插件一直拉不到新内容，可能是 cursor 卡住了：

```bash
# 看 cursor 当前值
cat /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync/data.json
# {"lastSyncCursor":"<某 note id>"}
```

重置：
```bash
# 方式 1：删 data.json（重启插件后从头拉取所有未交付的 note）
rm /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync/data.json

# 然后在 Obsidian 里禁用并重新启用插件
```

---

## 第七步：测速（轮询间隔）

在插件设置里改"轮询间隔（秒）"：
- 改为 `60`，保存
- 提交文章后观察：约 1 分钟才同步
- 改回 `5`，观察：5 秒内同步

确认插件会自动重启定时器（不需要重启 Obsidian）。

---

## 清理：测试完成后

### 8.1 在 Obsidian 禁用 shijian-sync 插件

设置 → 第三方插件 → 拾笺同步 → 关闭

### 8.2 重新启用 FNS 插件

设置 → 第三方插件 → Fast Note Sync → 开启

### 8.3 删除测试目录

```bash
# 删除测试期间产生的目录（如果不再需要）
rm -rf /Users/luluen/Documents/obsidian/shijian-test
```

### 8.4 删除测试插件文件（可选）

```bash
rm -rf /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync
```

### 8.5 停掉本地后端

```bash
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin
docker compose -f deploy/compose.yaml --env-file deploy/.env down -v
# -v 会同时删除 PocketBase 数据卷，下次启动是全新数据库
```

### 8.6 清理临时文件

```bash
rm -f /tmp/test-attachment.txt
```

---

## 方案 B：用测试 Vault（更安全）

如果你担心在主 Vault 测试有风险，可以建一个独立的测试 Vault：

### B.1 创建测试 Vault

打开 Obsidian → 点击 vault 列表左下角的「管理 vault」→ 「Create new vault」→ 选「Create new vault」：

- Vault 名称：`shijian-test-vault`
- 路径：`/Users/luluen/Documents/shijian-test-vault`

### B.2 切到测试 Vault 后安装插件

```bash
PLUGIN_DIR="/Users/luluen/Documents/shijian-test-vault/.obsidian/plugins/shijian-sync"
mkdir -p "$PLUGIN_DIR"
cp /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin/obsidian-plugin/{main.js,manifest.json} "$PLUGIN_DIR/"
```

在测试 Vault 里启用插件，配置同第三步。

### B.3 测完删除测试 Vault

直接删目录：
```bash
rm -rf /Users/luluen/Documents/shijian-test-vault
```

主 Vault 完全不受影响。

---

## 一键自检脚本

把下面的内容存为 `/tmp/shijian-selftest.sh`：

```bash
#!/bin/bash
set -e
BASE=http://localhost:18000

echo "=== 1. 健康检查 ==="
curl -fsS "$BASE/healthz" && echo

echo "=== 2. 生成邀请码 ==="
INVITE=$(docker compose -f deploy/compose.yaml --env-file deploy/.env \
  exec -T api python -m backend.scripts.create_invite 2>&1 | tail -1 | tr -d '[:space:]')
echo "邀请码: $INVITE"

echo "=== 3. 注册 ==="
curl -fsS -X POST "$BASE/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$INVITE\",\"email\":\"selftest@test.com\",\"password\":\"long-password-123\"}" && echo

echo "=== 4. 登录 ==="
TOKEN=$(curl -fsS -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"selftest@test.com","password":"long-password-123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "TOKEN: ${TOKEN:0:20}..."

echo "=== 5. 拉取（应为空）==="
curl -fsS "$BASE/v1/sync/changes" -H "Authorization: Bearer $TOKEN" && echo

echo "=== 6. 上传附件 ==="
echo "test content" > /tmp/shijian-selftest.pdf
curl -fsS -X POST "$BASE/v1/clips/files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/shijian-selftest.pdf;type=application/pdf" && echo

echo "=== 7. 拉取（应有 1 条 attachment）==="
curl -fsS "$BASE/v1/sync/changes" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20

echo "=== ✅ 后端自检通过 ==="
```

运行：
```bash
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin
bash /tmp/shijian-selftest.sh
```

---

## 故障排查

### 插件设置页打不开 / Obsidian 卡死

```bash
# 看 Obsidian 日志
# macOS：~/Library/Application Support/obsidian/obsidian.log
tail -50 ~/Library/Application\ Support/obsidian/obsidian.log

# 临时解决：删插件目录，重启 Obsidian
rm -rf /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync
```

### 插件一直"加载中"不显示设置

确认 `main.js` 和 `manifest.json` 在同一目录，且 `manifest.json` 的 `id` 字段与目录名一致（`shijian-sync`）：

```bash
cat /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync/manifest.json
# 应该有 "id": "shijian-sync"
```

### Docker 容器起不来

```bash
# 看每个容器的日志
docker compose -f deploy/compose.yaml --env-file deploy/.env logs pocketbase --tail 30
docker compose -f deploy/compose.yaml --env-file deploy/.env logs api --tail 30
docker compose -f deploy/compose.yaml --env-file deploy/.env logs worker --tail 30

# 完全重来
docker compose -f deploy/compose.yaml --env-file deploy/.env down -v
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
```

### PocketBase 报 migration 错误

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env logs pocketbase | grep -i error | tail -10
```

常见错误及解决：

| 错误 | 原因 | 解决 |
|---|---|---|
| `no such column: created` | 跑的是旧 migration（索引引用了 created） | 确认 worktree 代码是最新：`git pull` |
| `Failed to create index idx_notes_*` | 同上 | 同上 |
| `validation_required: delivered` | migration 用了 `required: true` 的 bool 字段 | 同上 |
| `failed to apply migration` | 数据库状态不一致 | `docker compose down -v` 清数据卷重来 |

### 浏览器 / Obsidian 报 CORS 错误

本地 API 默认不开 CORS。Obsidian 插件用的是 `requestUrl`（绕过 CORS），不会遇到这个问题。如果你在浏览器里测，会失败——这是预期的。

API 容器端口没暴露。检查 `deploy/compose.yaml` 中 api 服务的 ports 映射是否配置正确，然后 `docker compose up -d` 重启。

---

## 验收清单

本地测试完成后，对照打勾：

### 后端
- [ ] 3 个 Docker 容器 Up，PocketBase healthy
- [ ] `curl http://localhost:18000/healthz` 返回 ok
- [ ] 注册新用户成功
- [ ] 登录拿到 token
- [ ] POST /v1/clips 文章 URL，10-20 秒后 status=succeeded
- [ ] GET /v1/sync/changes 返回文章 Markdown + 图片 URL
- [ ] POST /v1/sync/ack 后再拉为空
- [ ] POST /v1/clips/files 上传附件成功
- [ ] GET /v1/sync/notes/{id}/attachment 下载字节

### Obsidian 插件
- [ ] 插件在「第三方插件」列表显示
- [ ] 设置页 8 个字段可填
- [ ] 5 秒内 Notice 提示同步成功
- [ ] `shijian-test/` 目录出现文章 .md
- [ ] frontmatter 含 title/source/shijian_id
- [ ] 图片下载到 `shijian-test/assets/`
- [ ] markdown 里图片 URL 已替换为本地路径
- [ ] 附件同步到 `shijian-test/assets/`
- [ ] 网络断开 → Notice 错误；恢复后自动追上
- [ ] 密码错误 → Notice 提示登录失败
- [ ] 改轮询间隔后定时器自动重置

### 整体
- [ ] 测试目录 `shijian-test/` 内容可手动删除而不影响 Vault
- [ ] FNS 插件测完已重新启用
- [ ] Docker 服务已停（`docker compose down`）

---

## 进阶：调试技巧

### 看插件实时日志

Obsidian → 显示开发者工具（Ctrl/Cmd+Option+I）→ Console 标签

所有插件日志都带 `[shijian-sync]` 前缀，过滤这个字符串可以看到：
- 同步开始/结束
- 单条失败原因
- 图片下载失败警告

### 手动触发同步

不用等轮询，点 Obsidian 左侧栏的下载图标，或命令面板（Ctrl/Cmd+P）→ 输入「拾笺同步：立即同步」。

### 修改插件代码后热重载

```bash
# 1. 在 obsidian-plugin/ 目录跑 watch 模式
cd /Users/luluen/ai-project/wechat_article/.worktrees/fns-to-plugin/obsidian-plugin
npm run dev  # 自动监听 src/ 变化并重新构建

# 2. 改 src/*.ts，main.js 会自动更新

# 3. 复制到插件目录
cp main.js /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync/

# 4. Obsidian 里禁用并重新启用插件（或按 Ctrl/Cmd+R 重启）
```

### 用 mitmproxy 抓插件请求

如果想看插件实际发了什么请求：

```bash
# 装 mitmproxy
brew install mitmproxy

# 启动代理
mitmproxy --listen-port 8888

# Obsidian 设置 → 第三方插件 → 拾笺同步 → 后端地址改为
# http://localhost:18000
# （Obsidian 的 requestUrl 会走系统代理）

# 或在 .obsidian/plugins/shijian-sync/data.json 里直接改 baseUrl
```

---

## 常见问题

**Q：能不能用同一个 PocketBase 实例测多用户？**

可以。每个邀请码注册一个新用户，用户数据完全隔离（见 docs/e2e-test-guide.md 第 2.6 节）。

**Q：本地测试的文章和真实部署的文章有什么区别？**

没区别。后端抓取和 Markdown 转换逻辑完全相同。本地测通了，线上只需换后端地址即可。

**Q：测试期间我原来的 FNS 同步会受影响吗？**

只要在 Obsidian 里**禁用 FNS 插件**，就不会同步。测完再开回来。你的 Vault 历史 md 文件不会被任何插件改动（shijian-sync 只创建新文件，不修改现有文件）。

**Q：插件密码是明文存的吗？**

是。Obsidian 没有 keychain API，密码以明文存在 `.obsidian/plugins/shijian-sync/data.json`。文件权限默认 644，建议改成 600：

```bash
chmod 600 /Users/luluen/Documents/obsidian/.obsidian/plugins/shijian-sync/data.json
```

**Q：图片下载到 Vault 后，下次同步会不会重复下载？**

不会。插件用图片 URL 的 sha256 前 6 字符作文件名，写入前会 `vault.exists()` 检查。已存在的图片直接跳过下载，但仍会替换 markdown 里的 URL。

**Q：为什么我的 Obsidian 移动端拉不到笔记？**

移动端 Obsidian 必须 App 在前台才会触发 `registerInterval` 定时器。锁屏或后台时不轮询。这是 Obsidian 的限制，不是插件 bug。
