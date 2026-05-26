#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
status=0

check() {
  local description="$1"
  local pattern="$2"
  if grep -RInE --exclude-dir=.git --exclude-dir=__pycache__ --exclude='*.pyc' \
      --exclude='gateway.env.example' "${pattern}" "${ROOT}" >/tmp/ec20-privacy-hit 2>/dev/null; then
    printf '[FAIL] Possible %s:\n' "${description}" >&2
    cat /tmp/ec20-privacy-hit >&2
    status=1
  fi
}

check "private IPv4 from a live environment" '192\.168\.50\.'
check "Chinese telecom public IPv6 prefix from a live environment" '240[eE]:'
check "Bark push key URL" 'api\.day\.app/[A-Za-z0-9]{15,}'
check "Feishu production App ID" 'cli_[A-Za-z0-9]{12,}'
check "DNSPod token-style credential" '[0-9]{5,},[A-Za-z0-9_-]{20,}'
check "IMEI or IMSI-sized numeric identity" '[^0-9][0-9]{15}[^0-9]'

rm -f /tmp/ec20-privacy-hit
if [[ "${status}" -ne 0 ]]; then
  exit "${status}"
fi
printf '[OK] No obvious live secrets or device identities found.\n'

