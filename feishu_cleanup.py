#!/usr/bin/env python3
"""Recall EC20 bot messages older than the configured chat retention."""

from __future__ import annotations

import sys

sys.path.insert(0, "/usr/local/lib/ec20")

from feishu_common import recall_expired_messages


def main() -> int:
    recalled, failed = recall_expired_messages(7)
    print(f"feishu-cleanup: recalled={recalled} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
