# 微信公众号转存

项目保留一个本地 H5 PoC，并提供可分发的 Android APK v1：受邀请码保护的用户通过 APK 登录，配置自己的 Fast Note Sync 后，可从微信系统分享菜单把公众号文章转存到 Obsidian。

生产部署、创建邀请码和 APK 构建方式见 [deploy/README.md](deploy/README.md)。

## 本地 H5 PoC

启动本地 H5 调试页：

```bash
python3 -m poc.server
```

打开 `http://127.0.0.1:8765`，从 Fast Note Sync 管理面板复制 API 配置 JSON，填写公众号文章链接和目标目录后提交。

页面只在内存中使用 `apiToken`，不会写入浏览器存储或本地文件。服务默认只监听本机；不要在未增加鉴权的情况下暴露到公网。
