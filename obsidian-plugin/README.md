# 拾笺同步（Shijian Sync）

从拾笺后端（微信公众号剪藏服务）定时拉取已抓取的 Markdown 文章与附件，自动写入 Obsidian Vault。

## 功能

- 每 N 秒（默认 5 秒）轮询后端 `/v1/sync/changes`，增量同步。
- 自动下载文章里的微信公众号图片到本地，并把 Markdown 中的图片链接替换为 Vault 内相对路径。
- 自动下载附件（PDF、Office 等）到附件目录，保留原文件名。
- 同步成功后调用 `/v1/sync/ack` 通知后端清理。
- 提供「立即同步」命令和 Ribbon 图标，可在设置里关闭自动轮询。

## 安装

1. 在本目录运行 `npm install && npm run build`，得到 `main.js`。
2. 在 Obsidian Vault 中创建目录：`<Vault>/.obsidian/plugins/shijian-sync/`。
3. 将以下文件复制到该目录：
   - `main.js`
   - `manifest.json`
4. 在 Obsidian 设置 → 第三方插件中启用「拾笺同步」。

## 配置

在插件设置页填写：

| 配置项 | 说明 | 默认 |
| --- | --- | --- |
| 后端服务地址 | 拾笺后端的 HTTPS 地址，如 `https://wechat.example.com` | 空 |
| 邮箱 | 注册账号的邮箱 | 空 |
| 密码 | 账号密码（**明文保存在 data.json**） | 空 |
| 文章目录 | 文章保存的 Vault 目录 | `公众号收藏` |
| 附件目录 | 图片与附件保存的 Vault 目录 | `公众号收藏/assets` |
| 轮询间隔（秒） | 范围 5-300 | `5` |
| 自动同步 | 关闭后只响应手动「立即同步」命令 | 开 |

## 隐私

- 邮箱、密码以**明文**形式保存在 Obsidian 插件数据目录的 `data.json` 中。请确保设备安全，或使用专用低权限账号。
- 通信使用 HTTPS。Token 仅缓存在内存，重启后失效。

## 已知限制

- 图片命名采用 URL 的 SHA-256 前 12 位（6 字节 hex），避免重名，但同一 URL 重复同步会直接复用已有文件。
- 不做差异同步：文章已存在（按文件路径判断）则跳过，不会更新内容。如需重新抓取，请先删除 Vault 内对应文件。
- 附件单条上限 20 MiB（后端限制）。
- 不依赖也不参考 Remotely Save，没有完整的双向同步能力，只能从后端单向拉到 Vault。

## 后端 API

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/v1/auth/login` | 邮箱密码登录，返回 token |
| GET | `/v1/sync/changes?since=<ISO>&limit=<int>` | 增量拉取笔记列表 |
| GET | `/v1/sync/notes/{id}/attachment` | 下载附件原始字节 |
| POST | `/v1/sync/ack` | 确认已写入 Vault |
