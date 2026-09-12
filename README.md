# GLaDOS_Checkin
GLaDOS automatic check-in bypassing CloudFlare using github action

## 功能描述
1. 每日自动进行签到（本项目可通过CloudFlare反爬机制）
2. 支持多用户签到，多个Cookie之间采用`&&`手动分割
3. 【可选】支持将签到消息推送至Server酱，Pushplus，企业微信，Bark
4. 本项目可触发Github Notifications，出现Cookie过期/签到失败等可自动发送Email
5. 内置**自维持心跳**保活机制，可防止 GitHub Actions 定时任务因仓库长期无提交而被自动停用（详见下方「保活机制」）

## 使用方法

### 1. 添加 Cookie 至 Secrets
- 登陆[GLaDOS](https://glados.rocks/)后，F12打开开发者工具。
- 刷新网页，并在浏览器中提取复制`Cookie`项（本程序可处理`Cookie:`前缀，使用者复制该项时是否具有前缀均可)

<p align="center">
  <img src="imgs/Step1.png" />
</p>

- 在项目页面，依次点击`Settings`-->`Secrets`-->`Actions`-->`New repository secret`
<p align="center">
  <img src="imgs/Step2.png" />
</p>

- 建立名为`GLADOS_COOKIE`的 secret，值为复制的`Cookie`内容，最后点击`Add secret`
- secret名字必须为`GLADOS_COOKIE`，大小写敏感
- 支持多用户签到，多个Cookie之间采用`&&`手动分割完成后填入`GLADOS_COOKIE`即可
- 为保护隐私，不在日志中输出任何Id信息，请自行分辨账号顺序

<p align="center">
  <img src="imgs/Step3.png" />
</p>

### 2. 启用 Actions
- 在项目页面，依次点击`Actions`-->`glados`-->`Run workflow`-->`Run workflow`以激活Actions

<p align="center">
  <img src="imgs/Step4.png" />
</p>

- Workflow开启后，每日0时30分自动执行。

## 3. 消息推送 （可选）
本项目支持将签到消息推送至第三方平台，用户选择其希望推送的平台并配置相关token即可。若用户不需要将消息推送至某个（些）平台，则无需对作作出任何配置。

### 3.1 Pushplus
将消息推送至[Pushplus](https://www.pushplus.plus)需手动配置`token`，并在本仓库创建名为`PUSHPLUS_TOKEN`的secret，将`token`作为`PUSHPLUS_TOKEN`的值。

### 3.2 Server酱
将消息推送至[Server酱](https://sct.ftqq.com/sendkey)需手动配置`SendKey`，并在本仓库创建名为`SERVERCHAN_SENDKEY`的secret，将`SendKey`作为`SERVERCHAN_SENDKEY`的值。

### 3.3 企业微信
将消息推送至[企业微信](https://sct.ftqq.com/sendkey)需手动配置群聊机器人`Webhook地址`，并在本仓库创建名为`WECOM_WEBHOOK`的secret，将`Webhook地址`作为`WECOM_WEBHOOK`的值。

- 此处请输入<b>完整</b>的Webhook地址，包含`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?`前缀，无需手动去除，切勿仅输入`key`值。
- 受制于第三方开发者ip访问限制，本项目暂不支持在Github Actions环境中将消息推送至企业微信应用。

### 3.4 Bark
将消息推送至[Bark](https://github.com/Finb/Bark)需手动配置`DeviceKey`，并在本仓库创建名为`BARK_DEVICEKEY`的secret，将`DeviceKey`作为`BARK_DEVICEKEY`的值。

## 保活机制（Keepalive）

GitHub 会在仓库**连续 60 天没有任何提交活动**时自动停用 scheduled workflow，
而 workflow 的运行本身**不算**仓库活动。因此一个只靠定时跑、长期不提交代码的仓库，
定时任务会在某天静默停摆 —— 本仓库就曾因此空档：2026-07-29 之后直到 2026-09-11
才恢复运行，中间停了一个多月。

解决办法是**自维持心跳**：签到任务在每次运行末尾检查距上一次提交的天数，
超过阈值就提交一次 `.github/heartbeat.txt`。这样「签到 → 产生提交 → 仓库有活动 →
定时任务不会被停 → 继续签到」形成闭环，**无需任何外部服务，也不需要 PAT**。

要点：

- 心跳 step 带 `if: always()`，即使签到失败也会执行
- 仅在距上次提交超过 `HEARTBEAT_MAX_AGE_DAYS`（默认 20 天）时才提交，日常开发时零噪音
- 由 `GITHUB_TOKEN` 产生的提交不会触发新的 workflow 运行，无递归风险
- 阈值 20 天远小于停用线 60 天，留有 40 天缓冲

### 手动验证

`Actions` → `glados` → `Run workflow`，把 `heartbeat_days` 填 `0`，
即可强制本次运行立即产生一次心跳提交，用来确认保活链路是通的。

### 若定时任务已被停用

推送一次提交通常会自动重新激活。若没有，到 `Actions` → `glados` 页面点击
**Enable workflow** 手动恢复。

## 鸣谢
- 感谢[yaoysyao](https://github.com/yaoysyao)支持将消息推送至Pushplus的相关内容
- 感谢[AstbReal](https://github.com/AstbReal)支持将消息推送至Server酱和企业微信的相关内容及GLaDOS用户status的解析策略
