# 02. EC20、VoLTE 与音频路径

本章的 AT 配置来自 EC20 + Asterisk 电话路线的公开教程，并在实机通话中验证。
不同固件、不同网络环境可能返回不同结果。操作前记录当前状态，不要反复随机刷参数。

## 先确认 SIM 与注册

进入 AT 端口。常见是 `/dev/ttyUSB2`，但不要假设所有机器都一样：

```bash
ls -l /dev/ttyUSB*
sudo minicom -D /dev/ttyUSB2
```

执行：

```text
ATI
AT+CPIN?
AT+COPS?
AT+CSQ
```

只有 SIM 已识别并可注册网络后，才继续配置 VoLTE。

## 可选：重置来源不明的二手模块配置

仅当模块为二手、参数来源不明或始终无法注册时考虑：

```text
AT+QPRTPARA=3
AT+CFUN=1,1
```

模块会重启。重连 AT 端口后重新确认 SIM 与网络注册。

## 启用 IMS / VoLTE

```text
AT+QCFG="ims",1
AT+QMBNCFG="AutoSel",0
AT+QMBNCFG="deactivate"
AT+QMBNCFG="select","ROW_Generic_3GPP"
AT+CFUN=1,1
```

模块重启后核验：

```text
AT+QCFG="ims"
AT+QMBNCFG="list"
```

如果 SIM 未开通或不支持 VoLTE 服务，即使模块配置正确也可能无法完成通话。

## 音频路径：推荐串口 PCM，不推荐 UAC 作为长期默认

EC20 常见有两类音频接入方式：

| 方式 | 优点 | 风险 |
| --- | --- | --- |
| 串口 PCM | `chan_quectel` 原有链路更稳定，适合长期放置 | 需要确认哪个 ttyUSB 是音频口 |
| UAC / USB Audio | 配置看起来直观，Linux 会出现 USB 声卡 | 实机出现过无声、电流声、爆音、快照后状态漂移 |

本项目当前推荐 **串口 PCM**。UAC 可以作为调试选项，但不建议作为默认生产方案。

## 固定 EC20 串口别名

不要长期把 Asterisk 写死到 `/dev/ttyUSB1`、`/dev/ttyUSB2`。重启、重新插拔或 USB
直通重枚举后，数字编号可能变化。

先查看接口号：

```bash
for dev in /dev/ttyUSB*; do
  echo "== $dev =="
  udevadm info --query=property --name="$dev" |
    grep -E '^(DEVNAME|ID_VENDOR_ID|ID_MODEL_ID|ID_USB_INTERFACE_NUM|ID_USB_DRIVER|ID_PATH)='
done
```

实机验证过的一组常见结果是：

| 用途 | 接口号 | 固定别名 |
| --- | --- | --- |
| PCM 音频 | `01` | `/dev/ec20-audio` |
| AT 数据 | `02` | `/dev/ec20-at` |

使用模板创建 udev 规则：

```bash
sudo sed \
  -e 's|@@EC20_VENDOR_ID@@|2c7c|g' \
  -e 's|@@EC20_MODEL_ID@@|0125|g' \
  -e 's|@@EC20_AUDIO_INTERFACE@@|01|g' \
  -e 's|@@EC20_AT_INTERFACE@@|02|g' \
  templates/99-ec20-quectel.rules |
  sudo tee /etc/udev/rules.d/99-ec20-quectel.rules

sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/ec20-*
```

如果你的接口号不同，以现场 `udevadm` 输出为准。

## `quectel.conf` 推荐样例

安装 `chan_quectel` 后，核心配置类似：

```ini
[general]
smsdb=/var/lib/asterisk/smsdb

[defaults]
context=incoming-mobile
autodeletesms=yes
disablesms=no
rxgain=0
txgain=-5

[quectel0]
audio=/dev/ec20-audio
data=/dev/ec20-at
```

`txgain=-5` 是实机排障后得到的示例值，用于降低送往 SIM/eSIM 侧的音频电平，避免声音过大导致轻微削峰或爆音。不同模块和环境可以在 `-4`、`-5`、`-6` 附近微调。

核验：

```bash
sudo asterisk -rx "quectel show devices"
sudo asterisk -rx "quectel show device settings quectel0"
```

模块状态应显示为 `Free` 或可用状态，且 Audio/Data 应指向 `/dev/ec20-audio`、`/dev/ec20-at`。

## Asterisk 启动前等待 EC20 设备

如果 Asterisk 比 USB 设备更早启动，`chan_quectel` 可能加载失败或绑定到错误状态。
建议安装启动等待脚本和 systemd override：

```bash
sudo install -o root -g root -m 0755 scripts/ec20-wait-devices /usr/local/sbin/ec20-wait-devices
sudo install -o root -g root -m 0755 scripts/ec20-health /usr/local/sbin/ec20-health
sudo mkdir -p /etc/systemd/system/asterisk.service.d
sudo install -o root -g root -m 0644 systemd/asterisk-ec20-devices.conf \
  /etc/systemd/system/asterisk.service.d/10-ec20-devices.conf
sudo systemctl daemon-reload
sudo systemctl restart asterisk
sudo ec20-health
```

## UAC 仅作为可选调试

如果你明确要测试 UAC，可以让 EC20 暴露为 USB Audio：

```text
AT+QCFG="usbcfg",0x2C7C,0x0125,1,1,1,1,1,0,1
AT+CFUN=1,1
```

模块重新枚举后，在 Debian 执行：

```bash
aplay -l
arecord -l
```

UAC 对应的 `quectel.conf` 通常类似：

```ini
[quectel0]
data=/dev/ttyUSB2
quec_uac=1
alsadev=hw:CARD=Android,DEV=0
```

但如果出现无声、电流声、爆音、快照恢复后状态变化，优先切回串口 PCM。具体迭代说明见
[08. v0.2.0 音频稳定性迭代：串口 PCM 与启动固化](08-audio-stability-v0.2.0.md)。

## 已知风险

当前验证使用的 `chan_quectel` 配置中提示：通话进行期间如果收到短信，模块可能异常。
这是底层驱动风险，不是 Bark/飞书层能解决的问题。上线后应观察：

```bash
sudo journalctl -u asterisk --since today
sudo asterisk -rx "quectel show devices"
sudo ec20-health
```
