# 08. 音频问题复盘：从 UAC 切到串口 PCM

本章记录一次实机排障后的公开版结论。所有真实地址、号码、账号、密钥和模块身份信息均已省略。

## 现象

系统曾出现过这样的表现：

- Groundwire 可以注册，来电也有 Push。
- 通话接通后，手机端可以听到对方。
- 对方听不到手机端说话，或只能听到异常电流声、爆音。
- Groundwire 的 Asterisk 回声测试正常，说明手机麦克风、SIP 客户端到 Asterisk 的 RTP 链路基本正常。

这类问题很容易误判为 SIP、RTP、IPv6、防火墙或 Groundwire 配置问题。实际排查时要先把链路拆开。

## 排查方法

### 1. 先验证 SIP 客户端到 Asterisk

如果 Asterisk 回声测试正常，说明：

- iPhone 麦克风能被 Groundwire 正常采集。
- Groundwire 到 Asterisk 的上行 RTP 正常。
- 公网音频入口不应作为第一怀疑对象。

### 2. 绕过 Groundwire，直接测 Asterisk 到 EC20

使用 Asterisk 让 EC20 直接拨出并播放系统语音：

```bash
sudo asterisk -rx "channel originate Quectel/quectel0/<test_number> application Playback demo-congrats"
```

如果这一步已经无声、爆音或电流声，问题就不在 Groundwire，而在 Asterisk 到 EC20 的音频路径。

### 3. 观察 UAC 音频状态

UAC 模式下，EC20 会作为 USB Audio 设备暴露给 Linux。异常时常见表现是：

- ALSA playback 方向 underrun / xrun。
- Asterisk 看似接通，实际送到 EC20 的播放流异常。
- 重启 Asterisk、快照恢复、USB 设备重新枚举后问题表现可能变化。

这说明配置文件没有变化，并不代表实时音频流状态一定稳定。

## 根因判断

在该实机组合中，EC20 的 UAC 音频路径不可靠。问题发生在：

```text
Asterisk -> chan_quectel -> EC20 USB Audio -> SIM/eSIM
```

而不是：

```text
Groundwire -> SIP/RTP -> Asterisk
```

PVE 快照、虚拟机暂停恢复、Asterisk 重载、USB 直通设备重新初始化，都可能改变 USB Audio/ALSA 的运行态。快照能保存虚拟机磁盘状态，但不能保证外部 USB 音频设备的实时流状态被可靠恢复。

## 最终解决方案

放弃 UAC 音频，改用 EC20 串口 PCM 音频：

```ini
[defaults]
rxgain=0
txgain=-5

[quectel0]
audio=/dev/ec20-audio
data=/dev/ec20-at
;quec_uac=1
;alsadev=hw:CARD=Android,DEV=0
```

说明：

- `txgain=-5` 是实机调出的示例值，不是所有设备的固定答案。
- 如果仍有轻微削峰或音量过大，可在 `-4`、`-5`、`-6` 附近微调。
- 不建议为了音频问题反复切 TCP/UDP 或扩大防火墙端口，除非已经证明 RTP 不通。

## 固化优化

### 固定串口别名

不要长期依赖 `/dev/ttyUSB1`、`/dev/ttyUSB2` 这种编号。重启或重新插拔后编号可能变化。

使用 udev 固定别名：

```text
/dev/ec20-audio
/dev/ec20-at
```

接口号可用下面命令确认：

```bash
udevadm info --query=property --name=/dev/ttyUSB1 | grep ID_USB_INTERFACE_NUM
udevadm info --query=property --name=/dev/ttyUSB2 | grep ID_USB_INTERFACE_NUM
```

### Asterisk 启动前等待设备

如果 Asterisk 比 USB 设备更早启动，`chan_quectel` 可能加载失败或绑定到错误状态。建议添加 systemd override，让 Asterisk 启动前等待 `/dev/ec20-audio` 和 `/dev/ec20-at`。

本仓库提供：

```text
scripts/ec20-wait-devices
scripts/ec20-health
templates/99-ec20-quectel.rules
systemd/asterisk-ec20-devices.conf
```

### 健康检查

后续排障先运行：

```bash
sudo ec20-health
```

正常时应看到：

- `/dev/ec20-audio` 和 `/dev/ec20-at` 都存在。
- `asterisk active`。
- Asterisk 使用的是固定别名。
- `Voice: Yes`、`SMS: Yes`。

## 经验结论

如果遇到“配置没改，但快照后或一段时间后声音异常”，不要先假设网络问题。先用 Asterisk 直接播放系统语音，把问题分成两段：

```text
手机/SIP 到 Asterisk
Asterisk 到 EC20
```

这次问题属于第二段。串口 PCM 比 UAC 更适合作为长期放置的默认方案。
