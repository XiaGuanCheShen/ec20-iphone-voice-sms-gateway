#!/usr/bin/env python3
"""Update a DNSPod AAAA record with the gateway global IPv6 address."""

import ipaddress
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

CONF = "/etc/ec20-ddns.conf"
STATE_DIR = "/var/lib/ec20-ddns"
STATE_FILE = os.path.join(STATE_DIR, "last_ipv6")
API_BASE = "https://dnsapi.cn/"


def load_conf():
    values = {}
    with open(CONF, "r", encoding="utf-8") as config:
        for raw_line in config:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip()
    for name in ("DNSPOD_LOGIN_TOKEN", "DOMAIN", "SUBDOMAIN", "INTERFACE"):
        if not values.get(name):
            raise RuntimeError("missing configuration: " + name)
    return values


def public_ipv6(interface):
    output = subprocess.check_output(
        ["ip", "-6", "-o", "addr", "show", "dev", interface, "scope", "global"],
        text=True,
    )
    for line in output.splitlines():
        try:
            address = ipaddress.IPv6Address(line.split()[3].split("/", 1)[0])
        except (IndexError, ValueError):
            continue
        if address.is_global:
            return str(address)
    raise RuntimeError("no global IPv6 found on " + interface)


def request(action, token, parameters):
    payload = {
        "login_token": token,
        "format": "json",
        "lang": "cn",
        "error_on_empty": "no",
        **parameters,
    }
    http_request = urllib.request.Request(
        API_BASE + action,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"User-Agent": "ec20-gateway/1.0"},
    )
    with urllib.request.urlopen(http_request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("status", {}).get("code") != "1":
        raise RuntimeError(action + " failed: " + result.get("status", {}).get("message", "unknown"))
    return result


def main():
    force = "--force" in sys.argv[1:]
    config = load_conf()
    address = public_ipv6(config["INTERFACE"])
    if not force:
        try:
            with open(STATE_FILE, "r", encoding="ascii") as state:
                if state.read().strip() == address:
                    print("unchanged: " + address)
                    return 0
        except FileNotFoundError:
            pass

    result = request(
        "Record.List",
        config["DNSPOD_LOGIN_TOKEN"],
        {"domain": config["DOMAIN"], "sub_domain": config["SUBDOMAIN"]},
    )
    records = [
        record
        for record in result.get("records", [])
        if record.get("name") == config["SUBDOMAIN"] and record.get("type") == "AAAA"
    ]
    if records:
        record = records[0]
        if record.get("value", "").lower() != address.lower():
            request(
                "Record.Modify",
                config["DNSPOD_LOGIN_TOKEN"],
                {
                    "domain": config["DOMAIN"],
                    "record_id": record["id"],
                    "sub_domain": config["SUBDOMAIN"],
                    "record_type": "AAAA",
                    "record_line_id": record.get("line_id", "0"),
                    "value": address,
                },
            )
            print("dns updated: " + address)
        else:
            print("dns already current: " + address)
    else:
        request(
            "Record.Create",
            config["DNSPOD_LOGIN_TOKEN"],
            {
                "domain": config["DOMAIN"],
                "sub_domain": config["SUBDOMAIN"],
                "record_type": "AAAA",
                "record_line": "\u9ed8\u8ba4",
                "value": address,
            },
        )
        print("dns created: " + address)

    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    temporary = STATE_FILE + ".tmp"
    with open(temporary, "w", encoding="ascii") as state:
        state.write(address + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATE_FILE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ec20-ddns error: " + str(exc), file=sys.stderr)
        raise SystemExit(1)

