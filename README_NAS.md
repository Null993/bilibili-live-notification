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
