#!/usr/bin/env bash
set -euo pipefail

pass() { printf '[OK] %s\n' "$*"; }
warn() { printf '[CHECK] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run with sudo: sudo bash verify.sh"

systemctl is-active --quiet asterisk && pass "Asterisk is running" || fail "Asterisk is not running"
systemctl is-active --quiet ec20-feishu.service && pass "Feishu bot is running" || fail "Feishu bot is not running"
systemctl is-active --quiet ec20-feishu-cleanup.timer && pass "Seven-day cleanup timer is active" || fail "Cleanup timer is inactive"

asterisk -rx "core show application TrySystem" >/dev/null && pass "Asterisk TrySystem is available" || fail "TrySystem is unavailable"
asterisk -rx "dialplan show sms@incoming-mobile" | grep -q ec20-sms-bark &&
  pass "Inbound SMS dialplan calls ec20-sms-bark" ||
  warn "SMS dialplan is not installed yet; see docs/06-install-and-verify.md"

if asterisk -rx "quectel show devices" 2>/dev/null | grep -q quectel0; then
  pass "Quectel device is visible in Asterisk"
else
  warn "quectel0 is not shown; verify EC20 USB pass-through and chan_quectel"
fi

if command -v ec20-health >/dev/null && [[ -e /dev/ec20-audio || -e /dev/ec20-at ]]; then
  EC20_DEVICE="${EC20_DEVICE:-quectel0}" \
  EC20_EXPECTED_TXGAIN="${EC20_EXPECTED_TXGAIN:-}" \
    ec20-health || warn "EC20 serial PCM health check needs attention"
else
  warn "EC20 serial PCM health check not installed/enabled; see docs/08-audio-stability-v0.2.0.md"
fi

python3 - <<'PY'
import sqlite3
from pathlib import Path
p = Path("/var/lib/ec20-notify/sms.sqlite3")
if not p.exists():
    print("[CHECK] SQLite will be created after the first incoming SMS.")
else:
    db = sqlite3.connect(p)
    print("[OK] SQLite archive available, records:", db.execute("select count(*) from sms").fetchone()[0])
PY

journalctl -u ec20-feishu.service --no-pager -n 20 | grep -q "connected to wss://" &&
  pass "Feishu WebSocket connection observed" ||
  warn "No WebSocket connection logged yet; check Feishu event mode and app permissions"

if systemctl is-enabled --quiet ec20-ddns.timer 2>/dev/null; then
  systemctl is-active --quiet ec20-ddns.timer && pass "DNSPod IPv6 DDNS timer is active" || warn "DDNS timer enabled but inactive"
fi

printf '\nManual acceptance checks:\n'
printf '1. Receive one SMS and confirm Bark/Feishu route.\n'
printf '2. Send "短信统计" to the Feishu robot.\n'
printf '3. Send an SMS through the robot using its two-step confirmation.\n'
printf '4. Call both directions and confirm audio.\n'
