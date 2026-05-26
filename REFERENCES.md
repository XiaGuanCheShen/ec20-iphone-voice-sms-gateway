# 来源、致谢与实现差异

## 基础方案来源

### AmorXxx/iPhone_air_esim_tutorial

- 链接：[GitHub repository](https://github.com/AmorXxx/iPhone_air_esim_tutorial)
- 借鉴内容：EC20 模块、Debian 11、Issabel/Asterisk、`asterisk-chan-quectel`、
  Groundwire SIP 客户端和托管 SIM 的整体可行路径。
- 本项目差异：短信不采用 Telegram；改为 Bark 即时通知 + 飞书历史与指令；
  增加 IPv6 公网接入、DDNS、防火墙、ICE、加密、分类、七日清理和部署脚本。

原项目提供了关键的硬件与电话路线，本仓库是在该路线之上的独立增强实现，不声称原创
原始 EC20 电话方案。

## 组件与协议文档

### asterisk-chan-quectel

- 链接：[tg11/asterisk-chan-quectel](https://github.com/tg11/asterisk-chan-quectel)
- 用途：EC20 与 Asterisk 的语音和短信通道；本项目使用其
  `quectel sms <device> <number> <message>` 发送命令和 `SMS_BASE64` 入站变量。
- 风险：其示例配置提示通话中接收 SMS 可能引发模块异常；本项目在运维文档中保留
  该风险提示。

### Bark

- 链接：[Bark](https://github.com/Finb/Bark)
- 加密文档：[encryption.md](https://raw.githubusercontent.com/Finb/Bark/master/docs/encryption.md)
- 用途：iPhone 即时短信提醒；本项目使用 Bark 的 AES-128-CBC 加密推送。
- 差异说明：`passive` 只降低通知打扰，并不能实现“只保存在 Bark 内而不出现在
  iOS 通知列表”；因此营销短信最终改为仅飞书归档。

### 飞书开放平台

- 链接：[开放平台文档](https://open.feishu.cn/document/home/index)
- 用途：企业自建应用机器人、WebSocket 长连接收事件、发送/撤回机器人消息。
- 采用理由：长连接由家庭服务器主动发起，不要求开放新的公网回调端口；同时支持
  短信历史查看和从聊天中发短信。

### DNSPod

- 链接：[DNSPod API](https://docs.dnspod.cn/api/)
- 用途：家庭宽带公网 IPv6 前缀变化时更新 SIP 域名的 AAAA 记录。

## 短信分类参考

### SmsForwarder

- 链接：[pppscn/SmsForwarder](https://github.com/pppscn/SmsForwarder)
- 用途：参考其短信转发场景中的验证码/动态口令识别范围和按规则转发思路。

### FBS SMS Dataset

- 链接：[Cypher-Z/FBS_SMS_Dataset](https://github.com/Cypher-Z/FBS_SMS_Dataset)
- 用途：参考垃圾短信实际类别，包括贷款、房地产、零售、推广营销、金融诈骗与
  银行钓鱼等。
- 注意：数据集提供分类样本，不是可直接部署的拦截规则。本项目采用保守规则，只在
  高置信营销场景下取消 Bark 提醒，完整内容仍保存在飞书与本地数据库中。

## 许可与发布提示

- 本仓库的脚本与文档应使用自己的许可声明发布。
- 引用外部项目时仅引用思路、公开接口和链接，不复制对方大段受版权保护的文字内容。
- 使用前请分别确认 EC20 模块、SIP 客户端、飞书应用与 Bark 的许可及服务条款。
