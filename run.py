#!/usr/bin/env python3
"""入口。

    python run.py                # 完整跑一遍
    python run.py --dry-run      # 只抓取 + 本地打标，不调 Gemini（不花钱）
    python run.py --limit 5      # 只处理 5 条，第一次试跑用这个
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from src import pipeline  # noqa: E402  必须在 load_dotenv 之后


def main() -> int:
    parser = argparse.ArgumentParser(description="RSS → 翻译 → 打标 → index.csv")
    parser.add_argument("--limit", type=int, default=None, help="本次最多处理多少条")
    parser.add_argument("--dry-run", action="store_true", help="不调 Gemini，只抓取和本地打标")
    parser.add_argument("--quiet", action="store_true", help="只写日志文件，不打屏")
    args = parser.parse_args()

    stats = pipeline.run(limit=args.limit, dry_run=args.dry_run, verbose=not args.quiet)
    # 有失败就返回非零，cron 那一侧才好判断要不要告警
    return 1 if stats["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
