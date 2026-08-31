# B 站直播监控（Apprise / x86 NAS 版）

本分支在上游 `NateScarlet/bilibili-live-notification` 的基础上增加：

- 轮询补偿下播事件，长连接丢消息时仍能发现状态变化；
- SQLite 状态持久化，容器重启后不会把已有直播重复当作新开播；
- 连续状态确认，降低接口瞬时异常导致的误报；
- 内置 Apprise，可配置邮件、企业微信机器人及其他通知服务；
- 首次启动在状态数据库同目录生成 `.env`，默认监控直播间 `22747736`；
- Linux `amd64` 镜像构建和 `.tar` 导出脚本。

## 生成 NAS 配置

复制 Compose 文件到部署目录：

```text
deployments/docker-compose.nas.yml  -> docker-compose.yml
```

容器首次启动会在部署目录自动生成：

```text
data/state.db
data/.env
data/logs/bilibili-live-notification.log
```

默认 `.env` 监控直播间 `22747736`。需要修改直播间或增加通知渠道时，编辑
`data/.env` 后重启容器。也可以在首次启动前将
`deployments/.env.nas.example` 复制为 `data/.env`。容器管理界面中直接设置的
环境变量优先于该文件。

企业微信群机器人只需配置：

```env
APPRISE_URL_1=wecombot://企业微信机器人KEY
```

邮件 URL 的完整格式因服务商而异。QQ 邮箱的常见形式为：

```env
APPRISE_URL_2=mailtos://QQ号:SMTP授权码@qq.com/收件人@qq.com
```

用户名、授权码或地址含特殊字符时必须进行 URL 编码。可参考
[Apprise 通知服务文档](https://appriseit.com/services/)。

## 构建并导出 x86_64 镜像

### GitHub Actions（推荐）

推送 `agent/nas-apprise` 分支后，工作流
`.github/workflows/nas-amd64-tar.yml` 会依次运行测试、构建 `linux/amd64`
镜像并上传构建产物。也可以在 GitHub 仓库的 Actions 页面手动运行
`NAS amd64 image tar`。

工作流成功后下载产物：

```text
bilibili-live-notification-apprise-amd64
```

解压下载的 artifact ZIP 后会得到镜像 tar 和对应的 SHA256 文件。产物默认
保留 30 天。

### 本机构建

Windows PowerShell：

```powershell
.\scripts\build-amd64-tar.ps1
```

Linux：

```sh
./scripts/build-amd64-tar.sh
```

默认输出：

```text
dist/bilibili-live-notification-apprise-amd64.tar
```

即使构建电脑不是 x86_64，脚本也会显式请求 `linux/amd64`。这种情况下
Docker BuildKit 需要启用对应的 QEMU 模拟支持。

## 导入 NAS

将 tar、`.env` 和 `docker-compose.yml` 上传到 NAS。通过 SSH 导入：

```sh
docker load -i bilibili-live-notification-apprise-amd64.tar
docker compose up -d
docker compose logs -f bilibili-live-notification
```

群晖 Container Manager、威联通 Container Station 等界面也可以使用
“映像/镜像 -> 导入”选择该 tar。导入后的镜像名是：

```text
bilibili-live-notification-apprise:latest
```

## 状态检测策略

程序同时运行 B 站直播长连接与定时轮询：

- 长连接收到 `LIVE` 或 `PREPARING` 时立即处理；
- 轮询发现状态连续变化达到 `BILIBILI_POLLING_CONFIRMATIONS` 次后补发事件；
- 两条路径共用 SQLite 状态去重；
- 首次启动默认只建立状态基线，不通知已经开始的直播。将
  `BILIBILI_NOTIFY_ON_INITIAL_LIVE=true` 可改变该行为。

建议轮询间隔设置为 60～120 秒，不要过度请求 B 站接口。

## 接口保护与日志

默认情况下，房间信息请求 15 秒超时，失败后最多尝试 3 次并指数退避；B站
返回 `-352` 风控后，所有房间的接口刷新会冷却 30 分钟，期间只使用已有缓存，
不会把缓存状态当作新的开播或下播。请求速率默认限制为每秒 1 次、突发 2 次。
可在 `data/.env` 中调整：

```env
BILIBILI_API_TIMEOUT_SECS=15
BILIBILI_API_RETRY_ATTEMPTS=3
BILIBILI_API_RETRY_BASE_SECS=2
BILIBILI_API_RETRY_MAX_SECS=30
BILIBILI_API_RISK_COOLDOWN_SECS=1800
BILIBILI_API_RATE_LIMIT_BURST=2
BILIBILI_API_RATE_LIMIT_PER_SECOND=1
```

应用日志同时输出到容器控制台和 `/data/logs`。文件每天午夜轮转，默认最多保留
当天及此前 6 天，共 7 天：

```env
LOG_DIR=/data/logs
LOG_RETENTION_DAYS=7
```

通知发送会记录“开始、服务接受或失败”，但不会把通知 URL、密码或机器人 Key
写入日志。Docker 自己的容器控制台日志轮转仍需在 NAS 的容器管理器中单独设置。

## 重复通知排查

程序会自动去除 `APPRISE_URLS` 和 `APPRISE_URL_n` 中完全相同的通知 URL；直播
状态变化还会通过 SQLite 原子认领，长连接、轮询以及共享同一 `state.db` 的多个
进程不会重复发送。

如果邮件和企业微信仍同时收到两份，请在 NAS 上检查是否运行了两个使用不同
数据目录的旧、新容器。不同数据库之间无法互相去重：

```sh
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}'
```

应只保留一个 `bilibili-live-notification` 实例，并确认它挂载的是预期的
`/data/state.db`。启动日志中的 `configured N Apprise notification target(s)`
也应与实际配置的渠道数量一致；当前邮件加企业微信通常应显示 `2`。
