# FNS 附件转存 PoC

此 PoC 只验证 FNS 附件上传与拾笺 VPS 暂存清理，不开放 Android 上传接口，也不会写入 PocketBase 任务记录。

## 前提

- FNS Service 需支持 `POST /api/file` 的 multipart 上传接口。
- 准备一个非重要的 PNG、PDF 或 XLSX 文件。
- 将 FNS 管理页面复制的 JSON 保存到仓库外的受保护文件；其中必须有 `api`、`apiToken`、`vault`，不得提交到 Git。

## 运行

```sh
python -m backend.scripts.poc_fns_attachment \
  --fns-config /secure/fns.json \
  --file /secure/sample.pdf \
  --target-path '00_Inbox/附件/PoC/sample.pdf'
```

成功时输出 FNS 写入路径，`/tmp/shijian-fns-poc` 中的暂存副本会被删除。失败时暂存副本保留，以便检查或重试；完成验证后应手动删除该目录。

## 验收

1. FNS Web 管理页或本地 Obsidian Vault 中出现目标附件。
2. 文件 SHA-256 与原文件一致。
3. `/tmp/shijian-fns-poc` 不保留成功任务的副本。
4. 断网或故意填写错误 FNS 地址时，命令失败且暂存副本仍存在。
