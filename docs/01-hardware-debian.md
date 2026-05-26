# 01. 硬件、Debian 与 USB 直通

## 你要准备什么

| 物品 | 说明 |
| --- | --- |
| EC20 模块 | 需要支持 SIM 所需的 LTE/VoLTE 能力；实测方案使用 EC20F 类模块 |
| mini-PCIe 转 USB 底板 | 带 SIM 卡槽与稳定供电 |
| 天线 | 不要在无天线状态下长期注册或通话 |
| 一张 SIM | 先确认在手机中能正常通话、收发短信、已开通 VoLTE |
| 常开主机/虚拟机 | 本教程采用 Debian 11 `amd64` |
| iPhone | 安装 Groundwire 与 Bark |
| 飞书账号 | 创建企业自建应用机器人 |

`amd64` 适用于 Intel/AMD x86-64 处理器，例如常见小主机或台式机 CPU；不是指 AMD
品牌专用。树莓派等 ARM 设备需要使用对应的 `arm64` 系统，本文未做全流程验证。

## 安装 Debian 11

推荐使用 Debian 11 netinst `amd64` 镜像。安装时按下列选择：

1. 启动菜单选 `Install` 或 `Graphical install`。
2. 语言按需选择；时区按实际所在地设置，例如 `Asia/Shanghai`。
3. 设置普通用户和密码；同时确保后续可用 `sudo`。
4. 磁盘为专用虚拟机时可选 `Guided - use entire disk`。
5. 软件选择只保留 `SSH server` 与 `standard system utilities`；不需要桌面环境。
6. 安装 GRUB，完成后重启。

首次进入系统后：

```bash
su -
apt update
apt install -y sudo curl git usbutils minicom
usermod -aG sudo your_user
```

## 如果使用 PVE 虚拟机

把 EC20 USB 设备直通给 Debian VM：

1. 在 PVE 主机执行 `lsusb`，找到 `Quectel Wireless Solutions` 设备。
2. VM -> `Hardware` -> `Add` -> `USB Device`。
3. 优先按 USB 物理端口直通，避免模块重启后设备编号变化。
4. 重启 VM，再在 Debian 内执行：

```bash
lsusb
ls /dev/ttyUSB*
```

预期能看到 Quectel 设备以及多个 `/dev/ttyUSB*` 端口。通常 AT 控制端口为
`/dev/ttyUSB2`，但必须通过命令确认，不能只照抄。

## 确认模块能响应

```bash
sudo minicom -D /dev/ttyUSB2
```

输入：

```text
ATI
AT+CPIN?
AT+COPS?
AT+CSQ
```

预期：

- `ATI` 返回模块型号。
- `AT+CPIN?` 返回 `READY`。
- `AT+COPS?` 返回网络注册状态。
- `AT+CSQ` 返回信号强度，而不是持续无信号。

退出 `minicom`：`Ctrl+A`，再按 `X`。

## 隐私提示

不要把以下命令的完整输出截图上传到公开仓库：

```text
ATI
AT+CGSN
AT+CIMI
quectel show devices
```

输出可能包含 IMEI、IMSI 或电话号码相关身份信息。
