#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/gateway.env}"
BACKUP_DIR="/root/ec20-gateway-backups/$(date +%Y%m%d-%H%M%S)"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_value() {
  local name="$1"
  local value="${!name:-}"
  [[ -n "${value}" && "${value}" != replace_* && "${value}" != cli_replace_* ]] ||
    die "Fill ${name} in ${ENV_FILE} first."
}

[[ "${EUID}" -eq 0 ]] || die "Run with sudo: sudo bash install.sh"
[[ -f "${ENV_FILE}" ]] || die "Copy gateway.env.example to gateway.env and fill it first."

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

need_value BARK_DEVICE_KEY
need_value BARK_ENCRYPTION_KEY
need_value BARK_ENCRYPTION_IV
need_value FEISHU_APP_ID
need_value FEISHU_APP_SECRET
need_value FEISHU_BIND_CODE

[[ "${#BARK_ENCRYPTION_KEY}" -eq 16 ]] || die "BARK_ENCRYPTION_KEY must be 16 ASCII characters."
[[ "${#BARK_ENCRYPTION_IV}" -eq 16 ]] || die "BARK_ENCRYPTION_IV must be 16 ASCII characters."
[[ "${FEISHU_BIND_CODE}" =~ ^[0-9]{6}$ ]] || die "FEISHU_BIND_CODE must be six digits."
[[ -d /etc/asterisk ]] || die "Asterisk is not installed. Finish docs/03-voice-groundwire.md first."
command -v asterisk >/dev/null || die "Asterisk CLI not found."

printf 'Installing packages...\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates openssl python3 python3-pip sqlite3
python3 -m pip install --quiet --disable-pip-version-check -r "${ROOT_DIR}/requirements.txt"

mkdir -p "${BACKUP_DIR}" /usr/local/lib/ec20 /var/lib/ec20-notify
chown asterisk:asterisk /var/lib/ec20-notify
chmod 0750 /var/lib/ec20-notify

for path in \
  /usr/local/sbin/ec20-sms-bark \
  /usr/local/sbin/ec20-feishu-bot \
  /usr/local/sbin/ec20-feishu-cleanup \
  /usr/local/lib/ec20/feishu_common.py \
  /etc/ec20-bark.conf \
  /etc/ec20-feishu.conf; do
  [[ -e "${path}" ]] && cp -a "${path}" "${BACKUP_DIR}/"
done

install -o root -g root -m 0755 "${ROOT_DIR}/bark_sms_notify.py" /usr/local/sbin/ec20-sms-bark
install -o root -g root -m 0755 "${ROOT_DIR}/feishu_bot.py" /usr/local/sbin/ec20-feishu-bot
install -o root -g root -m 0755 "${ROOT_DIR}/feishu_cleanup.py" /usr/local/sbin/ec20-feishu-cleanup
install -o root -g root -m 0644 "${ROOT_DIR}/feishu_common.py" /usr/local/lib/ec20/feishu_common.py

umask 077
cat > /etc/ec20-bark.conf <<EOF
BARK_SERVER=${BARK_SERVER:-https://api.day.app}
BARK_DEVICE_KEY=${BARK_DEVICE_KEY}
BARK_ENCRYPTION_KEY=${BARK_ENCRYPTION_KEY}
BARK_ENCRYPTION_IV=${BARK_ENCRYPTION_IV}
EOF
chown root:asterisk /etc/ec20-bark.conf
chmod 0640 /etc/ec20-bark.conf

cat > /etc/ec20-feishu.conf <<EOF
FEISHU_APP_ID=${FEISHU_APP_ID}
FEISHU_APP_SECRET=${FEISHU_APP_SECRET}
FEISHU_BIND_CODE=${FEISHU_BIND_CODE}
EOF
chown root:asterisk /etc/ec20-feishu.conf
chmod 0640 /etc/ec20-feishu.conf

install -o root -g root -m 0644 "${ROOT_DIR}/ec20-feishu.service" /etc/systemd/system/ec20-feishu.service
install -o root -g root -m 0644 "${ROOT_DIR}/ec20-feishu-cleanup.service" /etc/systemd/system/ec20-feishu-cleanup.service
install -o root -g root -m 0644 "${ROOT_DIR}/ec20-feishu-cleanup.timer" /etc/systemd/system/ec20-feishu-cleanup.timer

if [[ "${INSTALL_DIALPLAN:-no}" == yes ]]; then
  [[ "${REPLACE_EXTENSIONS_CUSTOM:-no}" == yes ]] ||
    die "Set REPLACE_EXTENSIONS_CUSTOM=yes after reading docs/06-install-and-verify.md."
  cp -a /etc/asterisk/extensions_custom.conf "${BACKUP_DIR}/extensions_custom.conf" 2>/dev/null || true
  install -o asterisk -g asterisk -m 0640 "${ROOT_DIR}/extensions_custom.conf" /etc/asterisk/extensions_custom.conf
  asterisk -rx "dialplan reload" >/dev/null
fi

if [[ "${ENABLE_DNSPOD_DDNS:-no}" == yes ]]; then
  need_value DNSPOD_LOGIN_TOKEN
  need_value DOMAIN
  need_value SUBDOMAIN
  need_value NETWORK_INTERFACE
  install -o root -g root -m 0700 "${ROOT_DIR}/scripts/ec20-ddns.py" /usr/local/sbin/ec20-ddns
  cat > /etc/ec20-ddns.conf <<EOF
DNSPOD_LOGIN_TOKEN=${DNSPOD_LOGIN_TOKEN}
DOMAIN=${DOMAIN}
SUBDOMAIN=${SUBDOMAIN}
INTERFACE=${NETWORK_INTERFACE}
EOF
  chmod 0600 /etc/ec20-ddns.conf
  install -o root -g root -m 0644 "${ROOT_DIR}/systemd/ec20-ddns.service" /etc/systemd/system/ec20-ddns.service
  install -o root -g root -m 0644 "${ROOT_DIR}/systemd/ec20-ddns.timer" /etc/systemd/system/ec20-ddns.timer
fi

if [[ "${ENABLE_FIREWALL:-no}" == yes ]]; then
  need_value HOME_IPV4_LAN
  command -v nft >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y nftables
  cp -a /etc/nftables.conf "${BACKUP_DIR}/nftables.conf" 2>/dev/null || true
  sed "s|@@HOME_IPV4_LAN@@|${HOME_IPV4_LAN}|g" \
    "${ROOT_DIR}/templates/nftables.conf" > /etc/nftables.conf
  systemctl enable --now nftables.service
  nft -f /etc/nftables.conf
fi

python3 -m py_compile \
  /usr/local/sbin/ec20-sms-bark \
  /usr/local/sbin/ec20-feishu-bot \
  /usr/local/sbin/ec20-feishu-cleanup \
  /usr/local/lib/ec20/feishu_common.py

systemctl daemon-reload
systemctl enable --now ec20-feishu.service ec20-feishu-cleanup.timer
if [[ "${ENABLE_DNSPOD_DDNS:-no}" == yes ]]; then
  systemctl enable --now ec20-ddns.timer
  /usr/local/sbin/ec20-ddns --force
fi

printf '\nInstalled. Backup: %s\n' "${BACKUP_DIR}"
printf 'Next: send "绑定 %s" to your Feishu robot, then run: sudo bash verify.sh\n' "${FEISHU_BIND_CODE}"

