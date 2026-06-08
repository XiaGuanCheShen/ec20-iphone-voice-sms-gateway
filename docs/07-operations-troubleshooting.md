# 07. 日常运维与故障定位

## 常用查看命令

```bash
sudo systemctl status asterisk ec20-feishu.service ec20-feishu-cleanup.timer ec20-ddns.timer
sudo journalctl -u ec20-feishu.service --since today
sudo journalctl -u ec20-feishu-cleanup.service --since today
sudo journalctl -u ec20-ddns.service --since today
sudo asterisk -rx "quectel show devices"
sudo asterisk -rx "pjsip show contacts"
sudo ec20-health
```

查看本地短信条数，不打印正文：

```bash
sudo -u asterisk sqlite3 /var/lib/ec20-notify/sms.sqlite3 \
  'select category, count(*) from sms group by category;'
```

## 飞书命令

```text
最近 5
查短信 今天
查短信 7天
查短信 号码 10086
查短信 关键词 流量
查短信 分类 营销
查短信 2026-05-01 2026-05-31
短信统计
发短信 10086 查询余额
```

## 故障定位表

| 现象 | 优先检查 |
| --- | --- |
| 模块不见了 | PVE USB 直通、`lsusb`、`/dev/ttyUSB*`、供电 |
| 电话能响但无声音 | 先跑 `sudo ec20-health`；再分段检查 Groundwire 回声测试、Asterisk 直接 Playback、RTP IPv6 防火墙端口 |
| 对方听不到你或有电流声/爆音 | 优先怀疑 EC20 UAC 音频路径；按 [08 音频复盘](08-audio-issue-postmortem.md) 切到串口 PCM |
| 公网 SIP 无法注册 | AAAA 是否更新、IPv6 入站、防火墙 `5160`、Groundwire TCP |
| Bark 无通知 | Device Key 是否取自推送 URL、Key/IV 是否两端一致 |
| 飞书不回命令 | 机器人权限、`im.message.receive_v1` 事件、应用版本发布、长连接日志 |
| 营销短信仍进 Bark | 飞书是否已绑定成功；未绑定时系统故意回退 Bark |
| 七日消息未清除 | 飞书管理员撤回时限、`ec20-feishu-cleanup.service` 日志 |

## 备份

至少备份：

```text
/etc/asterisk/
/etc/udev/rules.d/99-ec20-quectel.rules
/etc/systemd/system/asterisk.service.d/
/usr/local/sbin/ec20-wait-devices
/usr/local/sbin/ec20-health
/etc/ec20-bark.conf
/etc/ec20-feishu.conf
/etc/ec20-ddns.conf
/var/lib/ec20-notify/sms.sqlite3
```

配置文件含密钥，备份必须加密。SQLite 包含短信正文，也属于敏感数据。

## 升级和改规则

不要直接在服务器上改正在运行的脚本后遗忘来源。推荐：

1. 在仓库中修改规则。
2. 执行 `bash scripts/privacy-scan.sh`。
3. 更新服务器前备份现有脚本。
4. 用真实但可控的短信做一次 Bark/飞书/营销路由回归测试。
