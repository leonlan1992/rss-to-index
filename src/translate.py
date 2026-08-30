"""第二步：翻。

只翻标题，不翻正文。标题是索引字段，要能被扫、被搜；
正文躺在湖里，等你真要读那一篇的时候再翻不迟。
"""

import os

from google import genai

from . import db

PROMPT = """把下面这条科技新闻标题翻成中文。

要求：
- 公司名、产品名、人名、ticker 一律保留英文原文（Meta 不要翻成"元"，Palantir 不要音译）
- 保持新闻标题的语气，简短、不加主观评价
- 不要加任何解释、引号或前后缀，只输出译文本身

标题：{title}"""


class Translator:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def translate(self, title: str) -> str:
        resp = self.client.models.generate_content(
            model=self.model, contents=PROMPT.format(title=title)
        )
        return (resp.text or "").strip()


def translate_pending(conn, translator: Translator, limit: int | None = None) -> dict:
    """给还没有中文标题的条目补翻译。

    title_cn 有值就跳过——这条让失败重跑变得安全，也省钱。
    """
    rows = [r for r in db.unprocessed(conn, limit) if not r["title_cn"]]
    done, failed = 0, []
    for row in rows:
        try:
            title_cn = translator.translate(row["title_en"])
            if not title_cn:
                raise RuntimeError("模型返回空")
            db.update_item(conn, row["id"], title_cn=title_cn)
            done += 1
        except Exception as exc:                      # noqa: BLE001
            failed.append({"id": row["id"], "error": str(exc)})
    return {"translated": done, "failures": failed}
