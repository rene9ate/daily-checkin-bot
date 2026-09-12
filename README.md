# GLaDOS_Checkin

GLaDOS 每日自动签到，绕过 CloudFlare 反爬，由 GitHub Actions 定时执行。

## 配置

在 `Settings → Secrets and variables → Actions` 中添加：

| Secret | 必填 | 说明 |
|---|---|---|
| `GLADOS_COOKIE` | ✅ | GLaDOS 的 Cookie，多账号用 `&&` 分隔 |
| `PUSHPLUS_TOKEN` | | Pushplus 的 token |
| `SERVERCHAN_SENDKEY` | | Server酱的 SendKey |
| `WECOM_WEBHOOK` | | 企业微信群机器人 Webhook（需含 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?` 前缀） |
| `BARK_DEVICEKEY` | | Bark 的 DeviceKey |

**获取 Cookie**：登录 [glados.rocks](https://glados.rocks/) 后打开开发者工具，刷新页面，复制请求头里的 `Cookie` 值（带不带 `Cookie:` 前缀都可以）。

推送渠道均为可选，不配置就不推送。受第三方 IP 限制，企业微信**应用**消息暂不支持在 Actions 环境中推送，群机器人 Webhook 可以。

## 启用

`Actions` → `glados` → `Run workflow`。之后每天 UTC 16:30（北京时间 00:30）自动执行。

## 保活机制

GitHub 会在仓库**连续 60 天没有任何提交活动**时停用 scheduled workflow，而 workflow 的运行本身**不算**活动。本仓库曾因此空档：2026-07-29 之后直到 2026-09-11 才恢复，中间停了一个多月。

现在签到任务会在每次运行末尾检查距上次提交的天数，超过阈值就提交一次 `.github/heartbeat.txt`，形成「签到 → 产生提交 → 仓库有活动 → 定时任务不会被停 → 继续签到」的闭环。**不需要外部服务，也不需要 PAT。**

- 带有 `if: always()`，即使签到失败也会执行
- 默认阈值 `HEARTBEAT_MAX_AGE_DAYS = 20` 天，远低于 60 天停用线
- 由 `GITHUB_TOKEN` 产生的提交不会触发新的运行，无递归风险
- 手动验证：`Actions` → `glados` → `Run workflow`，把 `heartbeat_days` 填 `0` 即可强制立即心跳

## 本地运行

```bash
pip install -r glados/requirements.txt
python glados/main.py --cookie_string "你的Cookie"
```

## 文件

```
glados/
  main.py                       入口：遍历账号、汇总结果、推送
  glados.py                     签到核心
  messageSender.py              消息推送（Pushplus / Server酱 / 企业微信 / Bark）
  requirements.txt
.github/workflows/glados.yml    Actions 配置
```

## 致谢

- [yaoysyao](https://github.com/yaoysyao) — Pushplus 推送
- [AstbReal](https://github.com/AstbReal) — Server酱 / 企业微信推送、status 解析策略
