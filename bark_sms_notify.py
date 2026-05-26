#!/usr/bin/env python3
"""Persist an inbound EC20 SMS and send a policy-controlled Bark notification."""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, "/usr/local/lib/ec20")

try:
    from feishu_common import archive_sms
except ImportError:
    archive_sms = None


CONFIG_PATH = Path("/etc/ec20-bark.conf")
DB_PATH = Path("/var/lib/ec20-notify/sms.sqlite3")
PUSH_TIMEOUT_SECONDS = 8

OTP_PATTERN = re.compile(
    r"(?:(?:\u9a8c\u8bc1\u7801|\u6388\u6743\u7801|\u6821\u9a8c\u7801|"
    r"\u68c0\u9a8c\u7801|\u786e\u8ba4\u7801|\u6fc0\u6d3b\u7801|"
    r"\u52a8\u6001\u7801|\u5b89\u5168\u7801|\u8ba4\u8bc1\u7801|"
    r"\u8bc6\u522b\u7801|\u77ed\u4fe1\u53e3\u4ee4|\u52a8\u6001\u5bc6\u7801|"
    r"\u4ea4\u6613\u7801|\u4e0a\u7f51\u5bc6\u7801|\u52a8\u6001\u53e3\u4ee4|"
    r"\u968f\u673a\u7801|\u4e00\u6b21\u6027\u5bc6\u7801|"
    r"\u6821\u9a8c\u4fe1\u606f|verification\s*(?:code)?|\bcode\b|\botp\b)"
    r".{0,32}?(?<!\d)\d{4,8}(?!\d)|"
    r"(?<!\d)\d{4,8}(?!\d).{0,16}?"
    r"(?:\u9a8c\u8bc1\u7801|\u6388\u6743\u7801|\u6821\u9a8c\u7801|"
    r"\u52a8\u6001\u7801|\u8ba4\u8bc1\u7801|\u77ed\u4fe1\u53e3\u4ee4|"
    r"verification\s*(?:code)?|\bcode\b|\botp\b))",
    re.IGNORECASE | re.DOTALL,
)
FINANCE_PROMO_WORDS = (
    "\u8d37\u6b3e",
    "\u501f\u6b3e",
    "\u6388\u4fe1",
    "\u989d\u5ea6",
    "\u5206\u671f",
    "\u4fe1\u7528\u5361",
)
MARKETING_WORDS = (
    "\u7533\u8bf7",
    "\u9886\u53d6",
    "\u70b9\u51fb",
    "\u5229\u7387",
    "\u653e\u6b3e",
    "\u9000\u8ba2",
    "\u56de\u590dT",
    "\u56deT",
    "\u54a8\u8be2",
    "\u62a5\u540d",
    "\u62a2\u8d2d",
    "\u4f18\u60e0",
    "\u7279\u4ef7",
    "\u4fc3\u9500",
    "\u514d\u8d39\u529e\u7406",
)
REAL_ESTATE_PROMO_WORDS = (
    "\u697c\u76d8",
    "\u5f00\u76d8",
    "\u8d2d\u623f",
    "\u5546\u94fa",
    "\u516c\u5bd3",
    "\u770b\u623f",
    "\u8ba4\u7b79",
)
INSURANCE_PROMO_WORDS = (
    "\u4fdd\u9669",
    "\u91cd\u75be\u9669",
    "\u8f66\u9669",
    "\u5bff\u9669",
    "\u533b\u7597\u9669",
)
EDUCATION_PROMO_WORDS = (
    "\u57f9\u8bad",
    "\u8bfe\u7a0b",
    "\u8865\u4e60",
    "\u5b66\u5386\u63d0\u5347",
    "\u62db\u751f",
)
RETAIL_PROMO_WORDS = (
    "\u6ee1\u51cf",
    "\u4f18\u60e0\u5238",
    "\u4f1a\u5458\u65e5",
    "\u79d2\u6740",
    "\u9650\u65f6\u7279\u60e0",
)
TELECOM_PROMO_WORDS = (
    "\u5347\u7ea7\u5957\u9910",
    "\u4f18\u60e0\u5305",
    "\u52a0\u9910\u5305",
    "\u5bbd\u5e26\u529e\u7406",
)
URGENT_WORDS = (
    "\u6b20\u8d39",
    "\u505c\u673a",
    "\u5df2\u7528\u5c3d",
    "\u5373\u5c06\u7528\u5c3d",
    "\u5373\u5c06\u5230\u671f",
    "\u903e\u671f",
    "\u98ce\u9669",
    "\u5f02\u5e38",
    "\u767b\u5f55",
)
SERVICE_WORDS = (
    "\u6d41\u91cf",
    "\u5957\u9910",
    "\u4f59\u989d",
    "\u8d26\u5355",
    "\u6263\u8d39",
    "\u7f34\u8d39",
    "\u5230\u671f",
    "\u7528\u91cf",
    "\u5145\u503c",
)


def load_config() -> dict[str, str]:
    values: dict[str, str] = {}
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        for raw_line in config_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()

    values.setdefault("BARK_SERVER", "https://api.day.app")
    values["BARK_SERVER"] = values["BARK_SERVER"].rstrip("/")
    if not values.get("BARK_DEVICE_KEY"):
        raise RuntimeError("BARK_DEVICE_KEY is missing")
    return values


def decode_argument(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii"), validate=False).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("invalid base64 SMS argument") from exc


def contains_any(body: str, words: tuple[str, ...]) -> bool:
    return any(word.lower() in body.lower() for word in words)


def classify_sms(body: str) -> tuple[str, str, str]:
    """Return category, push policy, and Bark interruption level."""
    if OTP_PATTERN.search(body):
        return "otp", "push", "timeSensitive"
    if contains_any(body, URGENT_WORDS):
        return "urgent", "push", "timeSensitive"
    if contains_any(body, FINANCE_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "finance_promo", "feishu_only", "passive"
    if contains_any(body, REAL_ESTATE_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "real_estate_promo", "feishu_only", "passive"
    if contains_any(body, INSURANCE_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "insurance_promo", "feishu_only", "passive"
    if contains_any(body, EDUCATION_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "education_promo", "feishu_only", "passive"
    if contains_any(body, RETAIL_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "retail_promo", "feishu_only", "passive"
    if contains_any(body, TELECOM_PROMO_WORDS) and contains_any(body, MARKETING_WORDS):
        return "telecom_promo", "feishu_only", "passive"
    if contains_any(body, SERVICE_WORDS):
        return "service", "push", "active"
    return "normal", "push", "active"


def ensure_column(connection: sqlite3.Connection, name: str, declaration: str) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(sms)").fetchall()
    }
    if name not in columns:
        connection.execute(f"ALTER TABLE sms ADD COLUMN {name} {declaration}")


def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            bark_status TEXT NOT NULL DEFAULT 'pending',
            bark_error TEXT,
            bark_sent_at TEXT
        )
        """
    )
    ensure_column(connection, "category", "TEXT NOT NULL DEFAULT 'unclassified'")
    ensure_column(connection, "push_policy", "TEXT NOT NULL DEFAULT 'push'")
    ensure_column(connection, "bark_level", "TEXT NOT NULL DEFAULT 'active'")
    ensure_column(connection, "feishu_status", "TEXT NOT NULL DEFAULT 'pending'")
    ensure_column(connection, "feishu_error", "TEXT")
    ensure_column(connection, "feishu_sent_at", "TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS sms_received_at_idx ON sms(received_at)"
    )
    connection.commit()
    os.chmod(DB_PATH, 0o640)
    return connection


def encrypt_payload(payload: dict[str, str], key: str, iv: str) -> str:
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")
    if len(key_bytes) != 16:
        raise RuntimeError("BARK_ENCRYPTION_KEY must contain exactly 16 UTF-8 bytes")
    if len(iv_bytes) != 16:
        raise RuntimeError("BARK_ENCRYPTION_IV must contain exactly 16 UTF-8 bytes")
    result = subprocess.run(
        [
            "/usr/bin/openssl",
            "enc",
            "-aes-128-cbc",
            "-K",
            key_bytes.hex(),
            "-iv",
            iv_bytes.hex(),
        ],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return base64.b64encode(result.stdout).decode("ascii")


def send_bark(
    config: dict[str, str], sender: str, body: str, category: str, level: str
) -> tuple[bool, str]:
    label = {
        "otp": "SMS Verification Code",
        "urgent": "SMS Important Notice",
        "service": "SMS Service Notice",
        "normal": "New SMS",
    }.get(category, "New SMS")
    payload = {
        "title": f"{label} - {sender}" if sender else label,
        "body": body,
        "group": "EC20 SMS",
        "level": level,
        "isArchive": "1",
    }
    encryption_key = config.get("BARK_ENCRYPTION_KEY", "")
    encryption_iv = config.get("BARK_ENCRYPTION_IV", "")
    if encryption_key or encryption_iv:
        if not encryption_key or not encryption_iv:
            raise RuntimeError("Bark encryption requires both key and IV")
        ciphertext = encrypt_payload(payload, encryption_key, encryption_iv)
        data = urlencode({"ciphertext": ciphertext, "iv": encryption_iv}).encode("ascii")
        request = Request(
            f"{config['BARK_SERVER']}/{config['BARK_DEVICE_KEY']}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
    else:
        payload["device_key"] = config["BARK_DEVICE_KEY"]
        request = Request(
            f"{config['BARK_SERVER']}/push",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urlopen(request, timeout=PUSH_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and result.get("code") == 200:
                return True, ""
            return False, f"HTTP {response.status}, API code {result.get('code')}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, TimeoutError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        return False, type(exc).__name__


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: ec20-sms-bark <sender-base64> <message-base64>", file=sys.stderr)
        return 2

    try:
        sender = decode_argument(sys.argv[1]) or "unknown"
        body = decode_argument(sys.argv[2])
        category, push_policy, bark_level = classify_sms(body)
        received_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with open_database() as database:
            cursor = database.execute(
                """
                INSERT INTO sms
                    (received_at, sender, body, category, push_policy, bark_level)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (received_at, sender, body, category, push_policy, bark_level),
            )
            sms_id = cursor.lastrowid
            database.commit()

            feishu_delivered, feishu_error = (
                archive_sms(sender, body, category, received_at)
                if archive_sms is not None
                else (False, "not_installed")
            )
            feishu_sent_at = (
                datetime.now().astimezone().isoformat(timespec="seconds")
                if feishu_delivered
                else None
            )
            database.execute(
                """
                UPDATE sms SET feishu_status = ?, feishu_error = ?, feishu_sent_at = ?
                WHERE id = ?
                """,
                (
                    "sent" if feishu_delivered else "pending",
                    feishu_error or None,
                    feishu_sent_at,
                    sms_id,
                ),
            )
            database.commit()

            if push_policy == "feishu_only" and feishu_delivered:
                database.execute(
                    "UPDATE sms SET bark_status = 'routed_feishu' WHERE id = ?", (sms_id,)
                )
                database.commit()
                print(f"ec20-sms-bark: record {sms_id} routed to Feishu only ({category})")
                return 0

            delivered, error = send_bark(
                load_config(), sender, body, category, bark_level
            )
            sent_at = (
                datetime.now().astimezone().isoformat(timespec="seconds")
                if delivered
                else None
            )
            database.execute(
                """
                UPDATE sms
                SET bark_status = ?, bark_error = ?, bark_sent_at = ?
                WHERE id = ?
                """,
                ("sent" if delivered else "failed", error or None, sent_at, sms_id),
            )
            database.commit()
    except (OSError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"ec20-sms-bark: processing failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if not delivered:
        print(f"ec20-sms-bark: notification failed for record {sms_id}: {error}", file=sys.stderr)
        return 1
    print(f"ec20-sms-bark: notification sent for record {sms_id} ({category})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
