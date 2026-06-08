# 06. 一键安装与验收

## 安装前提

一键脚本针对“电话基础已可用”的机器，必须先满足：

```bash
sudo asterisk -rx "quectel show devices"
sudo asterisk -rx "pjsip show endpoints"
```

EC20 应可见，手机分机应已在 Issabel 创建。

如果你采用推荐的串口 PCM 音频方案，建议先读
[02. EC20、VoLTE 与音频路径](02-ec20-volte-uac.md)，确认 `/dev/ec20-audio`
和 `/dev/ec20-at` 的接口号。

## 下载并填写配置

```bash
git clone https://github.com/XiaGuanCheShen/ec20-iphone-voice-sms-gateway.git
cd ec20-iphone-voice-sms-gateway
cp gateway.env.example gateway.env
chmod 600 gateway.env
nano gateway.env
```

含密钥的值建议使用单引号：

```bash
BARK_DEVICE_KEY='your_key'
FEISHU_APP_SECRET='your_secret'
```

`gateway.env` 已被 `.gitignore` 排除，禁止提交。

## 关于拨号入口替换

本项目需要修改 `/etc/asterisk/extensions_custom.conf` 以接收短信。如果这台虚拟机只
用于 EC20 网关，可以启用：

```bash
INSTALL_DIALPLAN=yes
REPLACE_EXTENSIONS_CUSTOM=yes
```

安装脚本会自动备份原文件。若机器中已有其他自定义业务，请保持
`REPLACE_EXTENSIONS_CUSTOM=no`，手工合并 `extensions_custom.conf` 中的
`sms` 处理段。

## 执行安装

```bash
sudo bash install.sh
sudo bash verify.sh
```

安装脚本执行内容：

- 安装 Python/OpenSSL/SQLite 和飞书 SDK。
- 创建权限受限的 Bark/飞书配置文件。
- 安装短信脚本、飞书机器人服务、七日清理 timer。
- 可选安装 EC20 串口固定别名、Asterisk 启动等待和 `ec20-health`。
- 可选部署 DNSPod DDNS 与 nftables 规则。
- 备份被替换的配置到 `/root/ec20-gateway-backups/`。

如果要安装 EC20 设备固化项，在 `gateway.env` 中启用：

```bash
ENABLE_EC20_DEVICE_GUARD=yes
EC20_VENDOR_ID=2c7c
EC20_MODEL_ID=0125
EC20_AUDIO_INTERFACE=01
EC20_AT_INTERFACE=02
EC20_EXPECTED_TXGAIN=-5
```

脚本只安装 udev 规则、等待脚本和健康检查，不会自动改写 `quectel.conf`。确认接口号后，
手动把 `/etc/asterisk/quectel.conf` 指向 `/dev/ec20-audio` 和 `/dev/ec20-at`。

## 绑定飞书

安装结束会显示一次性绑定命令，例如：

```text
绑定 123456
```

向飞书机器人私聊发送该命令。机器人回复已绑定后，营销短信才会正式切换为仅飞书
归档；绑定前仍回退到 Bark，防止漏消息。

## 验收清单

### Bark

给 SIM 发送普通测试短信：

- Bark 收到通知。
- 锁屏未解锁时不显示正文。
- 通知正文能正确解密。

### 飞书

发送：

```text
短信统计
查短信 今天
```

应返回本地 SQLite 查询结果。

### 营销路由

用明确的测试内容发送到 SIM，例如同时含有“贷款额度”“申请”“退订”：

- 飞书能查看全文。
- Bark 不出现通知。

### 从飞书发送 SMS

```text
发短信 10086 查询余额
```

机器人返回确认码后：

```text
确认 123456
```

确认服务回复能按分类规则重新进入系统。

### 电话

最后重新测一次来电与去电，确认安装短信服务后没有影响语音。

如果安装了 EC20 设备固化项，先运行：

```bash
sudo ec20-health
```

再做真实来电和去电测试。
