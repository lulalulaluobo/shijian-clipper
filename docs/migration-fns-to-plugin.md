# 从 Fast Note Sync 迁移到 Obsidian 同步插件（v0.3.0）

v0.3.0 是破坏性版本，移除了 Fast Note Sync (FNS) 集成，改用自研 Obsidian 同步插件。

## 谁需要迁移

- 任何使用 v0.2.x 且部署了 FNS Service 的用户

## 迁移步骤

### 1. 升级后端

更新到 v0.3.0 后，PocketBase 会自动应用两个新 migration：
- `1710000005_create_notes_table.js`：新建 notes collection
- `1710000006_drop_fns_settings.js`：删除 fns_settings collection

老的 clip_tasks 数据保留，可继续在 APK 任务列表查看。

### 2. 移除 .env 中的 FNS_ENCRYPTION_KEY

```diff
- FNS_ENCRYPTION_KEY=...
```

重启服务：
```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d
```

### 3. 卸载 FNS Service（可选）

不再需要 Obsidian Fast Note Sync 插件和 Service。可以：
- 在 Obsidian 中禁用并卸载 FNS 插件
- 停止 FNS Service 进程

### 4. 构建并安装拾笺同步插件

```bash
cd obsidian-plugin
npm install
npm run build
```

把 `main.js` 和 `manifest.json` 复制到 Obsidian Vault 的 `.obsidian/plugins/shijian-sync/`，在 Obsidian 第三方插件里启用「拾笺同步」。

### 5. 配置插件

在插件设置页填后端地址、邮箱、密码、目录，5 秒内即可开始同步。

## 数据丢失风险

- ✅ 已抓取的文章（clip_tasks succeeded）：保留为历史记录，**但 Markdown 内容不会自动迁移到 notes 表**。如需重新同步到新插件，对失败或需要重新同步的任务点击「重试」。
- ✅ 邀请码、用户、使用期限：完全保留。
- ❌ FNS 配置（base_url / vault / token）：已删除，不可恢复。
