#!/usr/bin/env python3
"""Feishu long-connection bot for EC20 history access and outbound SMS."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/ec20")

import lark_oapi as lark
from feishu_common import load_config, load_state, save_state, send_text


DB_PATH = Path("/var/lib/ec20-notify/sms.sqlite3")
SMS_DEVICE = "quectel0"
SEND_PATTERN = re.compile(r"^(?:\u53d1\u77ed\u4fe1|\u53d1\u9001\u77ed\u4fe1)\s+(\+?\d{3,20})\s+(.{1,500})$", re.DOTALL)
CONFIRM_PATTERN = re.compile(r"^\u786e\u8ba4\s+(\d{6})$")
QUERY_PATTERN = re.compile(r"^\u67e5\u77ed\u4fe1(?:\s+(.+))?$", re.DOTALL)
CATEGORY_NAMES = {
    "\u9a8c\u8bc1\u7801": "otp",
    "\u91cd\u8981": "urgent",
    "\u670d\u52a1": "service",
    "\u8425\u9500": "promo",
    "\u8d37\u6b3e": "finance_promo",
    "\u623f\u4ea7": "real_estate_promo",
    "\u4fdd\u9669": "insurance_promo",
    "\u6559\u80b2": "education_promo",
    "\u4fc3\u9500": "retail_promo",
    "\u901a\u4fe1\u8425\u9500": "telecom_promo",
    "\u666e\u901a": "normal",
}
PROMO_CATEGORIES = (
    "finance_promo",
    "real_estate_promo",
    "insurance_promo",
    "education_promo",
    "retail_promo",
    "telecom_promo",
)


def bot_reply(open_id: str, text: str) -> None:
    delivered, error = send_text(text, open_id)
    if not delivered:
        raise RuntimeError(f"reply failed: {error}")


def bind_if_requested(open_id: str, text: str) -> bool:
    config = load_config()
    state = load_state()
    if state.get("admin_open_id"):
        return False
    binding = re.fullmatch(r"\s*\u7ed1\u5b9a\s*(\d{6})\s*", text)
    if not binding:
        return False
    if binding.group(1) != config.get("FEISHU_BIND_CODE", ""):
        bot_reply(open_id, "\u7ed1\u5b9a\u7801\u65e0\u6548\u3002")
        return True
    state["admin_open_id"] = open_id
    state["bound_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_state(state)
    bot_reply(
        open_id,
        "\u5df2\u7ed1\u5b9a EC20 \u77ed\u4fe1\u52a9\u624b\u3002\n"
        "\u547d\u4ee4\uff1a\n"
        "\u6700\u8fd1 5\n"
        "\u67e5\u77ed\u4fe1 7\u5929 / \u5173\u952e\u8bcd / \u53f7\u7801 / \u5206\u7c7b\n"
        "\u53d1\u77ed\u4fe1 <\u53f7\u7801> <\u5185\u5bb9>\n"
        "\u53d1\u77ed\u4fe1\u9700\u518d\u6b21\u786e\u8ba4\u624d\u4f1a\u53d1\u51fa\u3002",
    )
    return True


def recent_messages(open_id: str, count: int) -> None:
    count = max(1, min(count, 20))
    with sqlite3.connect(DB_PATH) as database:
        rows = database.execute(
            """
            SELECT received_at, sender, body, category
            FROM sms ORDER BY id DESC LIMIT ?
            """,
            (count,),
        ).fetchall()
    if not rows:
        bot_reply(open_id, "\u6682\u65e0\u77ed\u4fe1\u8bb0\u5f55\u3002")
        return
    lines = [f"\u6700\u8fd1 {len(rows)} \u6761\u77ed\u4fe1\uff1a"]
    for received_at, sender, body, category in rows:
        display_body = (
            "\u6b63\u6587\u5df2\u8131\u654f\uff0c\u8bf7\u67e5 Bark"
            if category == "otp"
            else body
        )
        lines.append(f"\n[{received_at}] {sender} / {category}\n{display_body}")
    bot_reply(open_id, "\n".join(lines))


def format_sms_rows(rows: list[tuple[str, str, str, str]], heading: str) -> str:
    lines = [heading]
    for received_at, sender, body, category in rows:
        display_body = (
            "\u6b63\u6587\u5df2\u8131\u654f\uff0c\u8bf7\u67e5 Bark"
            if category == "otp"
            else body
        )
        lines.append(f"\n[{received_at}] {sender} / {category}\n{display_body}")
    return "\n".join(lines)


def query_messages(open_id: str, expression: str) -> None:
    query = expression.strip()
    where = "1=1"
    params: list[str] = []
    label = query or "\u6700\u8fd1"
    now = datetime.now().astimezone()
    if query in {"", "\u6700\u8fd1"}:
        pass
    elif query == "\u4eca\u5929":
        where = "received_at >= ?"
        params.append(now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat())
    elif re.fullmatch(r"\d{1,3}\u5929", query):
        days = max(1, min(int(query[:-1]), 365))
        where = "received_at >= ?"
        params.append((now - timedelta(days=days)).isoformat())
    elif query.startswith("\u53f7\u7801 "):
        where = "sender LIKE ?"
        params.append(f"%{query[3:].strip()}%")
    elif query.startswith("\u5173\u952e\u8bcd "):
        where = "body LIKE ?"
        params.append(f"%{query[4:].strip()}%")
    elif query.startswith("\u5206\u7c7b "):
        name = query[3:].strip()
        category = CATEGORY_NAMES.get(name, name)
        if category == "promo":
            where = f"category IN ({','.join('?' for _ in PROMO_CATEGORIES)})"
            params.extend(PROMO_CATEGORIES)
        else:
            where = "category = ?"
            params.append(category)
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{4}-\d{2}-\d{2}", query):
        start, end = query.split()
        where = "received_at >= ? AND received_at < ?"
        params.extend([f"{start}T00:00:00", f"{end}T23:59:59"])
    else:
        bot_reply(
            open_id,
            "\u67e5\u8be2\u683c\u5f0f\uff1a\n"
            "\u67e5\u77ed\u4fe1 \u4eca\u5929\n"
            "\u67e5\u77ed\u4fe1 7\u5929\n"
            "\u67e5\u77ed\u4fe1 \u53f7\u7801 10086\n"
            "\u67e5\u77ed\u4fe1 \u5173\u952e\u8bcd \u6d41\u91cf\n"
            "\u67e5\u77ed\u4fe1 \u5206\u7c7b \u8425\u9500\n"
            "\u67e5\u77ed\u4fe1 2026-05-01 2026-05-31",
        )
        return
    with sqlite3.connect(DB_PATH) as database:
        count = database.execute(
            f"SELECT count(*) FROM sms WHERE {where}", params
        ).fetchone()[0]
        rows = database.execute(
            f"""
            SELECT received_at, sender, body, category
            FROM sms WHERE {where} ORDER BY id DESC LIMIT 10
            """,
            params,
        ).fetchall()
    if not rows:
        bot_reply(open_id, f"\u6ca1\u6709\u627e\u5230\u77ed\u4fe1\uff1a{label}")
        return
    suffix = "\uff08\u6700\u65b0 10 \u6761\uff09" if count > 10 else ""
    bot_reply(open_id, format_sms_rows(rows, f"\u67e5\u8be2 {label}\uff1a{count} \u6761{suffix}"))


def category_statistics(open_id: str) -> None:
    with sqlite3.connect(DB_PATH) as database:
        rows = database.execute(
            """
            SELECT category, count(*) FROM sms
            WHERE received_at >= ?
            GROUP BY category ORDER BY count(*) DESC
            """,
            ((datetime.now().astimezone() - timedelta(days=30)).isoformat(),),
        ).fetchall()
    if not rows:
        bot_reply(open_id, "\u8fd1 30 \u5929\u65e0\u77ed\u4fe1\u3002")
        return
    lines = ["\u8fd1 30 \u5929\u77ed\u4fe1\u7edf\u8ba1\uff1a"]
    lines.extend(f"{category}: {count}" for category, count in rows)
    bot_reply(open_id, "\n".join(lines))


def create_outbox_table(database: sqlite3.Connection) -> None:
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS sms_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_at TEXT NOT NULL,
            recipient TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            response TEXT
        )
        """
    )
    database.commit()


def prepare_sms(open_id: str, recipient: str, body: str) -> None:
    if "\n" in body or "\r" in body:
        bot_reply(open_id, "\u77ed\u4fe1\u5185\u5bb9\u6682\u4e0d\u652f\u6301\u6362\u884c\u3002")
        return
    state = load_state()
    code = f"{secrets.randbelow(1_000_000):06d}"
    state["pending_sms"] = {
        "code": code,
        "recipient": recipient,
        "body": body,
        "expires_at": int(time.time()) + 300,
    }
    save_state(state)
    bot_reply(
        open_id,
        f"\u5f85\u53d1\u9001\u77ed\u4fe1\uff1a\n\u6536\u4ef6\u4eba: {recipient}\n\u5185\u5bb9: {body}\n\n"
        f"5 \u5206\u949f\u5185\u56de\u590d\uff1a\u786e\u8ba4 {code}",
    )


def confirm_sms(open_id: str, code: str) -> None:
    state = load_state()
    pending = state.get("pending_sms")
    if not isinstance(pending, dict) or pending.get("code") != code:
        bot_reply(open_id, "\u6ca1\u6709\u5339\u914d\u7684\u5f85\u53d1\u9001\u77ed\u4fe1\u3002")
        return
    if int(pending.get("expires_at", 0)) < int(time.time()):
        state.pop("pending_sms", None)
        save_state(state)
        bot_reply(open_id, "\u8be5\u53d1\u9001\u786e\u8ba4\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u63d0\u4ea4\u3002")
        return
    recipient = str(pending["recipient"])
    body = str(pending["body"])
    command = f"quectel sms {SMS_DEVICE} {recipient} {body}"
    result = subprocess.run(
        ["/usr/sbin/asterisk", "-rx", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=20,
    )
    output = result.stdout.strip()[-300:]
    status = "sent" if result.returncode == 0 and "error" not in output.lower() else "failed"
    with sqlite3.connect(DB_PATH) as database:
        create_outbox_table(database)
        database.execute(
            """
            INSERT INTO sms_outbox (requested_at, recipient, body, status, response)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now().astimezone().isoformat(timespec="seconds"),
                recipient,
                body,
                status,
                output,
            ),
        )
        database.commit()
    state.pop("pending_sms", None)
    save_state(state)
    if status == "sent":
        bot_reply(open_id, f"\u77ed\u4fe1\u5df2\u63d0\u4ea4\u53d1\u9001: {recipient}")
    else:
        bot_reply(open_id, f"\u77ed\u4fe1\u53d1\u9001\u5931\u8d25: {output or 'unknown error'}")


def handle_text(open_id: str, text: str) -> None:
    if bind_if_requested(open_id, text):
        return
    state = load_state()
    if state.get("admin_open_id") != open_id:
        return
    stripped = text.strip()
    if stripped in {"\u5e2e\u52a9", "help"}:
        bot_reply(
            open_id,
            "\u547d\u4ee4\uff1a\n"
            "\u6700\u8fd1 5\n"
            "\u67e5\u77ed\u4fe1 \u4eca\u5929 / 7\u5929 / \u53f7\u7801 10086 / "
            "\u5173\u952e\u8bcd \u6d41\u91cf / \u5206\u7c7b \u8425\u9500\n"
            "\u77ed\u4fe1\u7edf\u8ba1\n"
            "\u53d1\u77ed\u4fe1 <\u53f7\u7801> <\u5185\u5bb9>",
        )
        return
    recent = re.match(r"^\u6700\u8fd1(?:\s+(\d{1,2}))?$", stripped)
    if recent:
        recent_messages(open_id, int(recent.group(1) or "5"))
        return
    query = QUERY_PATTERN.match(stripped)
    if query:
        query_messages(open_id, query.group(1) or "")
        return
    if stripped == "\u77ed\u4fe1\u7edf\u8ba1":
        category_statistics(open_id)
        return
    send = SEND_PATTERN.match(stripped)
    if send:
        prepare_sms(open_id, send.group(1), send.group(2))
        return
    confirm = CONFIRM_PATTERN.match(stripped)
    if confirm:
        confirm_sms(open_id, confirm.group(1))
        return
    bot_reply(open_id, "\u672a\u8bc6\u522b\u547d\u4ee4\u3002\u8f93\u5165\uff1a\u5e2e\u52a9")


def on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    event = data.event
    if event.message.message_type != "text":
        return
    open_id = event.sender.sender_id.open_id
    print(f"feishu text event received from ...{open_id[-6:]}", flush=True)
    content = json.loads(event.message.content)
    handle_text(open_id, str(content.get("text", "")))


def main() -> None:
    config = load_config()
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    client = lark.ws.Client(
        config["FEISHU_APP_ID"],
        config["FEISHU_APP_SECRET"],
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    client.start()


if __name__ == "__main__":
    main()
