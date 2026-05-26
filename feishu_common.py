#!/usr/bin/env python3
"""Small Feishu API client shared by EC20 SMS scripts."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CONFIG_PATH = Path("/etc/ec20-feishu.conf")
STATE_PATH = Path("/var/lib/ec20-notify/feishu_state.json")
DB_PATH = Path("/var/lib/ec20-notify/sms.sqlite3")
API_ROOT = "https://open.feishu.cn/open-apis"
REQUEST_TIMEOUT = 10


def load_config() -> dict[str, str]:
    values: dict[str, str] = {}
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        for raw_line in config_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if not values.get("FEISHU_APP_ID") or not values.get("FEISHU_APP_SECRET"):
        raise RuntimeError("Feishu application credentials are missing")
    return values


def load_state() -> dict[str, object]:
    try:
        with STATE_PATH.open("r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except FileNotFoundError:
        return {}


def save_state(state: dict[str, object]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, ensure_ascii=True, indent=2)
    os.chmod(temporary, 0o600)
    temporary.replace(STATE_PATH)
    os.chmod(STATE_PATH, 0o600)


def _request_json(
    method: str, url: str, payload: dict[str, object] | None = None, token: str = ""
) -> dict[str, object]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        ),
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Feishu HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Feishu request failed: {type(exc).__name__}") from exc


def _post_json(url: str, payload: dict[str, object], token: str = "") -> dict[str, object]:
    return _request_json("POST", url, payload, token)


def tenant_access_token() -> str:
    config = load_config()
    result = _post_json(
        f"{API_ROOT}/auth/v3/tenant_access_token/internal",
        {
            "app_id": config["FEISHU_APP_ID"],
            "app_secret": config["FEISHU_APP_SECRET"],
        },
    )
    if result.get("code") != 0 or not result.get("tenant_access_token"):
        raise RuntimeError(f"Feishu token rejected: {result.get('code')}")
    return str(result["tenant_access_token"])


def bound_open_id() -> str:
    return str(load_state().get("admin_open_id", ""))


def _message_database() -> sqlite3.Connection:
    database = sqlite3.connect(DB_PATH, timeout=5)
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS feishu_messages (
            message_id TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL,
            purpose TEXT NOT NULL,
            recalled_at TEXT,
            recall_error TEXT
        )
        """
    )
    database.commit()
    return database


def track_message(message_id: str, purpose: str) -> None:
    if not message_id:
        return
    with _message_database() as database:
        database.execute(
            """
            INSERT OR REPLACE INTO feishu_messages (message_id, sent_at, purpose)
            VALUES (?, ?, ?)
            """,
            (
                message_id,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                purpose,
            ),
        )
        database.commit()


def send_text(text: str, open_id: str = "", purpose: str = "bot_reply") -> tuple[bool, str]:
    recipient = open_id or bound_open_id()
    if not recipient:
        return False, "not_bound"
    try:
        token = tenant_access_token()
        result = _post_json(
            f"{API_ROOT}/im/v1/messages?{urlencode({'receive_id_type': 'open_id'})}",
            {
                "receive_id": recipient,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            token,
        )
    except RuntimeError as exc:
        return False, str(exc)
    if result.get("code") == 0:
        data = result.get("data")
        message_id = str(data.get("message_id", "")) if isinstance(data, dict) else ""
        track_message(message_id, purpose)
        return True, ""
    return False, f"API code {result.get('code')}"


def recall_expired_messages(retention_days: int = 7) -> tuple[int, int]:
    cutoff = datetime.now().astimezone() - timedelta(days=retention_days)
    with _message_database() as database:
        messages = database.execute(
            """
            SELECT message_id FROM feishu_messages
            WHERE recalled_at IS NULL AND sent_at < ?
            ORDER BY sent_at LIMIT 200
            """,
            (cutoff.isoformat(timespec="seconds"),),
        ).fetchall()
        if not messages:
            return 0, 0
        token = tenant_access_token()
        recalled = failed = 0
        for (message_id,) in messages:
            try:
                result = _request_json(
                    "DELETE", f"{API_ROOT}/im/v1/messages/{message_id}", token=token
                )
                if result.get("code") == 0:
                    database.execute(
                        """
                        UPDATE feishu_messages
                        SET recalled_at = ?, recall_error = NULL WHERE message_id = ?
                        """,
                        (
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                            message_id,
                        ),
                    )
                    recalled += 1
                else:
                    database.execute(
                        "UPDATE feishu_messages SET recall_error = ? WHERE message_id = ?",
                        (f"API code {result.get('code')}", message_id),
                    )
                    failed += 1
            except RuntimeError as exc:
                database.execute(
                    "UPDATE feishu_messages SET recall_error = ? WHERE message_id = ?",
                    (str(exc), message_id),
                )
                failed += 1
        database.commit()
        return recalled, failed


def archive_sms(sender: str, body: str, category: str, received_at: str) -> tuple[bool, str]:
    label = {
        "otp": "\u9a8c\u8bc1\u7801",
        "urgent": "\u91cd\u8981\u901a\u77e5",
        "service": "\u670d\u52a1\u901a\u77e5",
        "finance_promo": "\u8425\u9500-\u8d37\u6b3e\u91d1\u878d",
        "real_estate_promo": "\u8425\u9500-\u623f\u4ea7",
        "insurance_promo": "\u8425\u9500-\u4fdd\u9669",
        "education_promo": "\u8425\u9500-\u6559\u80b2\u57f9\u8bad",
        "retail_promo": "\u8425\u9500-\u4fc3\u9500",
        "telecom_promo": "\u8425\u9500-\u901a\u4fe1\u4e1a\u52a1",
        "normal": "\u666e\u901a\u77ed\u4fe1",
    }.get(category, category)
    if category == "otp":
        content = (
            f"[\u77ed\u4fe1/{label}]\n"
            f"\u65f6\u95f4: {received_at}\n"
            f"\u6765\u6e90: {sender}\n"
            "\u6b63\u6587: \u5df2\u8131\u654f\uff0c\u8bf7\u67e5\u770b Bark \u52a0\u5bc6\u65f6\u6548\u901a\u77e5"
        )
    else:
        content = (
            f"[\u77ed\u4fe1/{label}]\n"
            f"\u65f6\u95f4: {received_at}\n"
            f"\u6765\u6e90: {sender}\n"
            f"\u5185\u5bb9: {body}"
        )
    return send_text(content, purpose="sms_archive")
