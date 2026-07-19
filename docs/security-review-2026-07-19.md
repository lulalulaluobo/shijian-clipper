# 拾笺安全审查报告

- 审查日期：2026-07-19
- 审查提交：`057b1d4`（Shijian 1.0.1）
- 范围：Android 客户端、FastAPI、PocketBase 迁移、Worker/FNS、Docker/Caddy/Nginx、H5 PoC、GitHub 仓库设置。
- 方法：静态代码审查、部署暴露面检查、依赖清单检查、当前工作树/可达 Git 历史/本地不可达对象的常见密钥模式扫描。
- 不在范围：已部署 VPS、Cloudflare、Fast Note Sync 实例的运行时配置与渗透测试。

## 结论

当前版本适合受控的小范围使用，但**不建议在修复 H-01 和 H-02 前向不受信任的多人公开分发**。没有发现可直接利用的未鉴权数据库暴露或硬编码生产密钥；最重要的风险来自已登录用户让服务端访问任意 FNS 地址，以及所有公开接口缺少限流。

| 优先级 | 数量 | 结论 |
| --- | ---: | --- |
| 高 | 2 | 上线多人服务前修复 |
| 中 | 6 | 下一轮发布前处理或接受风险 |
| 低 | 3 | 纳入维护计划 |

## 高优先级

### H-01：FNS 配置可形成服务端请求伪造（SSRF）

证据：[`backend/app/fns.py`](../backend/app/fns.py#L6-L23) 仅检查 FNS `api` 是非空字符串；[`backend/app/service.py`](../backend/app/service.py#L84-L109) 保存并使用该地址；[`backend/app/worker.py`](../backend/app/worker.py#L27-L35) 会带着请求向该地址写入。底层 `urlopen` 默认跟随重定向。

影响：任何已注册用户可将 FNS 地址设为攻击者控制的 HTTPS 站点，再重定向到 VPS 内网、云元数据地址或其他管理服务。Worker 还可能向重定向后的目标发送写入请求，造成内网探测、请求伪造或资源消耗。

最小修复：

1. 只允许 `https` URL，解析域名后拒绝 loopback、link-local、私网、保留网段与 IPv6 等价地址。
2. 使用不跟随重定向的 HTTP 客户端；每次请求前校验实际连接 IP，防止 DNS rebinding。
3. 在 VPS 出站防火墙拒绝容器访问元数据与私网网段；若用户确实需要内网 FNS，采用明确的管理员白名单，而不是默认放行。
4. 为 FNS 响应设置最大字节数与总超时。

### H-02：认证、抓取和 FNS 检查接口没有限流与配额

证据：[`backend/app/api.py`](../backend/app/api.py#L49-L87) 的登录、注册、FNS 检查、创建任务与重试端点均没有限流；每次受保护请求还会触发 PocketBase token 刷新。文章抓取与 FNS HTTP 请求均使用 30 秒超时，但没有响应体大小限制（[`poc/wechat.py`](../poc/wechat.py#L46-L50)、[`backend/app/worker.py`](../backend/app/worker.py#L27-L35)）。

影响：公网可暴力尝试登录、耗尽 PocketBase/CPU 连接；已注册用户可批量提交抓取任务，消耗 VPS 带宽、Worker 和第三方服务配额。

最小修复：

1. 在 Nginx/Caddy 增加 IP 限流：登录/注册最严格，普通 API 次之。
2. 在 API 增加按用户的任务创建与重试配额，并限制同时排队任务数。
3. 限制请求体、抓取 HTML、FNS 响应的最大大小；对失败任务采用有上限的退避重试。
4. 为登录失败与任务创建记录不含凭据的审计事件。

## 中优先级

### M-01：公开发布的是 Debug 签名 APK

证据：当前 GitHub Release 附件名为 `Shijian-v1.0.1-debug.apk`；构建配置只有 Debug 交付路径（[`android/app/build.gradle.kts`](../android/app/build.gradle.kts#L9-L18)）。

影响：Debug 变体不应作为长期分发渠道；它会启用调试属性，且没有受控的发布签名和密钥轮换流程。

建议：建立 release signing 配置，将 keystore 放在密码管理器/CI Secret；发布仅使用 release APK 或 AAB，并在 Release 中提供 SHA-256。

### M-02：仓库供应链保护不足

仓库目前是公开仓库；GitHub Secret Scanning 与 Push Protection 已启用，但 Dependabot Security Updates 已禁用，`main` 没有分支保护。Python 依赖使用范围而非锁定版本（[`backend/requirements.txt`](../backend/requirements.txt)），容器基础镜像也没有 digest 固定（[`backend/Dockerfile`](../backend/Dockerfile)、[`deploy/compose.yaml`](../deploy/compose.yaml#L1-L16)）。

影响：直接推送、依赖漂移或上游镜像变化都会提高供应链风险。

建议：保护 `main`、要求状态检查；启用 Dependabot；固定 Python/容器依赖到可审核版本或 digest；在 CI 中运行依赖漏洞扫描与 GitHub secret scan。

### M-03：部署报告要求回显超级管理员密码

证据：[`deploy/AI_DEPLOYMENT.md`](../deploy/AI_DEPLOYMENT.md) 要求最终报告包含管理员密码。

影响：AI 对话、终端转录或部署报告存档会成为管理员凭据的副本。

建议：报告只给管理员账号与管理地址；密码通过用户的密码管理器或一次性安全通道交付。若必须在报告中显示，首次登录后立即轮换，且不要把报告保存到仓库或工单系统。

### M-04：Worker 容器拥有过宽的主机网络与 root 默认权限

证据：[`deploy/compose.vps.yaml`](../deploy/compose.vps.yaml#L3-L45) 的 PocketBase、API、Worker 都使用 `network_mode: host`，Dockerfile 没有切换非 root 用户（[`backend/Dockerfile`](../backend/Dockerfile)）。

影响：一旦 API/Worker 被利用，攻击者可见的主机网络面更大；root 容器也减少了隔离层。

建议：优先使用 bridge 网络并只发布 `127.0.0.1` 端口；为 API/Worker 使用非 root 用户、只读根文件系统、最小 Linux capabilities 和资源限制。

### M-05：公开管理端点缺少附加硬化

证据：Caddy 仅做反向代理（[`deploy/Caddyfile`](../deploy/Caddyfile)）；Nginx 管理模板直接代理 PocketBase，未设置安全响应头、访问控制或限流。

影响：若启用公网 PocketBase 后台，暴力尝试、点击劫持和管理面暴露风险会上升。

建议：保持 SSH 隧道作为默认后台方式。若必须公开，至少启用 HTTPS/HSTS、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、管理域名的限流与 IP allowlist/VPN；PocketBase 登录仍可保持唯一身份验证层。

### M-06：文章标题未作为文件名净化

证据：[`poc/fns.py`](../poc/fns.py#L21-L28) 将不受信任的公众号标题直接拼入目标路径。

影响：恶意标题可包含路径分隔符、控制字符或 `..`。若 Fast Note Sync 未在服务端做路径约束，可能写到用户选择目录之外或导致文件覆盖。

建议：在客户端与后端共同把标题规范化为安全文件名；拒绝路径分隔符、控制字符、`.`/`..` 段，并在 FNS 服务端强制目标路径位于目标目录下。

## 低优先级与条件性风险

### L-01：H5 PoC 被以非本地地址启动时没有认证

默认绑定 `127.0.0.1` 是安全的（[`poc/server.py`](../poc/server.py#L126-L133)），但命令行允许改为 `0.0.0.0`。一旦这样运行，任意访问者都可以把自己的 FNS token 发给该服务并触发抓取。

建议：在 README 明确“仅本机调试，不可公网部署”；或当 host 不是 loopback 时要求显式危险开关与随机本地口令。

### L-02：邀请码明文列是刻意的数据权衡

App 生成的邀请码会同时保存 `code` 和 `code_hash`（[`backend/app/service.py`](../backend/app/service.py#L74-L82)）。这满足后台查看真实邀请码的需求，但数据库超级管理员或备份泄露时可直接使用尚未消费的邀请码。

建议：默认只存 hash 并只在生成时显示；若确需后台展示，将明文列限制给超级管理员、在使用后清空，并记录查看/导出操作。

### L-03：多 Worker 扩容会重复领取同一任务

[`backend/app/service.py`](../backend/app/service.py#L136-L141) 先查询再更新任务，当前单 Worker 部署没有问题；扩容为多个 Worker 时会出现竞态，导致重复写入笔记。

建议：扩容前改用 PocketBase 条件更新/事务或引入队列的原子 claim。

## 已验证的正向控制

- Android 会话 token 使用 `EncryptedSharedPreferences` 与 Android Keystore 保护（[`SessionStore.kt`](../android/app/src/main/java/com/lulalulaluobo/wechatclipper/SessionStore.kt#L7-L35)）。
- FNS token 仅以 Fernet 密文保存，摘要接口不返回 token（[`backend/app/service.py`](../backend/app/service.py#L84-L105)）。
- 除注册、登录与健康检查外，API 路由均要求 PocketBase Bearer token，并在后端检查用户使用期限（[`backend/app/api.py`](../backend/app/api.py#L40-L87)、[`backend/app/service.py`](../backend/app/service.py#L171-L180)）。
- 默认 VPS Compose 将 API 与 PocketBase 绑定到 `127.0.0.1`，外部入口是反向代理（[`deploy/compose.vps.yaml`](../deploy/compose.vps.yaml#L18-L30)）。
- `.env`、构建产物和本地数据库文件已忽略。当前工作树、所有可达 Git 历史和本地不可达 blob 的常见 AWS/GitHub/JWT/私钥模式扫描均未命中；本地存在 86 个不可达 Git 对象，但未发现上述模式或 dotenv 内容。

## APK 自动更新功能的安全前提

该功能尚未实现。推荐只读取 GitHub Release API 的 HTTPS 元数据，比较 `versionCode`，高亮提示后由用户点击下载。不得静默安装或接受任意下载地址。

上线前必须先完成 release signing：Android 系统安装器应验证新 APK 与已安装 App 使用同一发布证书；用户仍需确认安装并授予“安装未知应用”权限。下载后还应比对 GitHub Release 中公布的 SHA-256。没有受控 release 签名时，不应实现应用内更新。

## 建议修复顺序

1. 修复 FNS SSRF、重定向和响应大小限制（H-01）。
2. 增加反向代理/API 限流与用户任务配额（H-02）。
3. 建立 release signing，再实现 GitHub Release 更新提示（M-01）。
4. 处理标题路径净化、后台凭据交付和公网管理面硬化（M-03、M-05、M-06）。
5. 启用仓库保护与依赖自动安全更新，随后做一次真实 VPS 配置复审（M-02、M-04）。

## 修复状态（2026-07-19）

已完成：

- H-01：FNS 服务端请求现要求 HTTPS 根地址、固定到解析出的公网 IP、拒绝重定向，并限制响应为 5 MiB。仅绑定本机的 H5 PoC 允许本地代理地址，以兼容开发机网络代理。
- H-02：登录/注册、FNS 检查、创建与重试任务已加入内存限流；入口请求体、FNS 配置字段和远程响应均有大小上限。
- M-03：AI 部署报告不再回显 PocketBase 管理员密码。
- M-04：VPS Compose 已移除 host 网络；API/PocketBase 仅映射到回环地址，API 与 PocketBase 镜像改为非 root 用户并移除 Linux capabilities。
- M-05：Caddy 与 Nginx 模板加入请求体上限、安全响应头，且反向代理覆盖而非拼接客户端转发地址。
- M-06、L-01：笔记文件名已净化；H5 PoC 默认拒绝绑定非 loopback 地址，除非显式传入 `--allow-network`。
- M-02（部分）：已加入 Dependabot 配置，并启用 GitHub Dependabot Security Updates。

仍需用户决策：

- M-01：建立发布签名 keystore 后才能发布可安全升级的 release APK；从当前 Debug APK 迁移到新的 release 证书时，现有测试用户需要卸载旧包后重新安装。
- M-02（部分）：`main` 分支保护会改变当前直推发布流程，需先决定是否改为 Pull Request + CI 审核。
- L-02：保留邀请码明文 `code` 是后台查看真实邀请码的产品需求，属于已知取舍；L-03 仅在多 Worker 扩容前需要处理。
