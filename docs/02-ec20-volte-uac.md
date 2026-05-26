# 02. EC20、VoLTE 与 UAC 音频

本章的 AT 配置来自 EC20 + Asterisk 电话路线的公开教程，并在实机通话中验证。
不同固件、不同网络环境可能返回不同结果。操作前记录当前状态，不要反复随机刷参数。

## 先确认 SIM 与注册

进入 AT 端口：

```bash
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

## 开启 USB Audio Class 音频

本方案使用 UAC，把 EC20 音频暴露为 Linux 声卡：

```text
AT+QCFG="usbcfg",0x2C7C,0x0125,1,1,1,1,1,0,1
AT+CFUN=1,1
```

模块重新枚举后，在 Debian 执行：

```bash
aplay -l
arecord -l
```

预期出现类似 `Android` 或 USB 音频设备名称。实际 Asterisk 配置中需要使用机器
显示出的名称，不要假设固定编号。

## `quectel.conf` 样例

安装 `chan_quectel` 后，核心配置类似：

```ini
[general]
smsdb=/var/lib/asterisk/smsdb

[defaults]
context=incoming-mobile
autodeletesms=yes
disablesms=no

[quectel0]
data=/dev/ttyUSB2
quec_uac=1
alsadev=hw:CARD=Android,DEV=0
```

核验：

```bash
sudo asterisk -rx "quectel show devices"
```

模块状态应显示为 `Free` 或可用状态。

## 已知风险

当前验证使用的 `chan_quectel` 配置中提示：通话进行期间如果收到短信，模块可能异常。
这是底层驱动风险，不是 Bark/飞书层能解决的问题。上线后应观察：

```bash
sudo journalctl -u asterisk --since today
sudo asterisk -rx "quectel show devices"
```
