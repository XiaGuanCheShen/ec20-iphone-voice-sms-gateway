# 04. 公网 IPv6、DDNS 与防火墙

## 为什么使用 IPv6

家庭宽带没有公网 IPv4 时，公网 IPv6 可以让 Groundwire/SIPIS 直接连接家中的
Asterisk。前提是：

- 家庭路由器获得公网 IPv6 前缀并正确下发给 Debian。
- 光猫/路由器没有拦截 IPv6 入站。
- Debian 防火墙仅放行必要端口。
- 手机当前网络具有 IPv6 可达性。

如果经常处在仅 IPv4 网络中，应另外考虑 VPS/中继方案，本项目未把它做成默认路径。

## 找到 Debian 的公网 IPv6

```bash
ip -6 addr show scope global
```

只在自己环境中记录地址，不要把真实地址发布到公开 Issue 或截图。

## DNSPod AAAA DDNS

家庭 IPv6 前缀可能变化，因此用域名指向网关。创建 DNSPod API Token 后，在
`gateway.env` 中配置：

```bash
ENABLE_DNSPOD_DDNS=yes
DNSPOD_LOGIN_TOKEN='replace_with_id_comma_token'
DOMAIN=example.com
SUBDOMAIN=sip
NETWORK_INTERFACE=ens18
```

安装器会创建 `ec20-ddns.timer`，每分钟检测一次 IPv6 变化，只有变化时调用 DNSPod
更新 AAAA 记录。

核验：

```bash
systemctl status ec20-ddns.timer
sudo /usr/local/sbin/ec20-ddns --force
dig AAAA sip.example.com @1.1.1.1 +short
```

## Debian 最小防火墙

`templates/nftables.conf` 的公网规则只开放：

| 端口 | 协议 | 用途 |
| --- | --- | --- |
| `5160` | TCP/UDP over IPv6 | SIP 信令 |
| `10000-10010` | UDP over IPv6 | RTP 音频 |

Web 管理、SSH 仅允许家庭内网 IPv4 网段访问。

启用前，先把 `HOME_IPV4_LAN` 改为自己家的网段，并确保你有 PVE/本地控制台回退方式：

```bash
ENABLE_FIREWALL=yes
HOME_IPV4_LAN=192.168.1.0/24
```

防火墙生效后核验：

```bash
sudo nft list ruleset
```

## 最简单的公网连通性排障

当 SIP 注册失败时，不要一开始就反复改 Groundwire。先临时启动一个非敏感测试端口来
证明 IPv6 入站是否可达，例如使用端口 `18080` 返回固定文字；测试完成立即关闭该
端口。只有入站可达后，才继续看 SIP 端口、账号和媒体设置。

