"""把三步串起来：抓 → 翻 → 标，最后追加进索引。

定时任务的难点从来不是"怎么定时"，是"它失败了你不知道"。
所以这里做三件事：留日志、统计每步数字、有失败就让 run.py 返回非零退出码。
"""

import logging
from pathlib import Path

from . import fetch, index_store, tag, translate

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "run.log"


def setup_logging(verbose: bool = True) -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pipeline")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s")
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    if verbose:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    return logger


def run(limit: int | None = None, dry_run: bool = False, verbose: bool = True) -> dict:
    log = setup_logging(verbose)
    log.info("=" * 60)

    # 1. 抓
    items, fetch_failures = fetch.fetch_all()
    for failure in fetch_failures:
        log.error("源失败 %s: %s", failure["source"], failure["error"])

    # 去重：已经在 index.csv 里的 URL 直接跳过
    seen = index_store.existing_urls()
    fresh = [i for i in items if i["link"] not in seen]
    if limit:
        fresh = fresh[:limit]
    log.info("抓取：拿到 %d 条，其中新条目 %d 条", len(items), len(fresh))

    if not fresh:
        log.info("没有新东西，收工")
        return {"fetched": len(items), "new": 0, "translated": 0,
                "written": 0, "failures": fetch_failures}

    # 2. 翻 + 3. 标
    tagger = tag.Tagger()
    translator = None if dry_run else translate.Translator()
    rows, translated, with_ticker = [], 0, 0
    failures = list(fetch_failures)

    for item in fresh:
        title_cn = ""
        if translator:
            try:
                title_cn = translator.translate(item["title_en"])
                translated += 1
            except Exception as exc:                  # noqa: BLE001
                failures.append({"source": item["link"], "error": f"翻译失败: {exc}"})
        tickers, tags = tagger.tag(item["title_en"], title_cn)
        if tickers:
            with_ticker += 1
        rows.append(index_store.build_row(item, title_cn, tickers, tags))

    if dry_run:
        log.info("翻译：dry-run 跳过")
    else:
        log.info("翻译：%d 条", translated)
    log.info("打标：%d 条挂上了股票", with_ticker)

    # 4. 追加进索引
    written = index_store.append(rows)
    log.info("写入索引：%d 条，index.csv 现在共 %d 条", written, index_store.count())

    return {"fetched": len(items), "new": len(fresh), "translated": translated,
            "with_ticker": with_ticker, "written": written, "failures": failures}
