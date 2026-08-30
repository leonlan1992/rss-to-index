"""第二步：翻。

只翻标题，不翻正文。标题是索引字段，要能被扫、被搜；
正文躺在原网页里，等你真要读那一篇的时候再说。
"""

import os

from google import genai

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
        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError("模型返回空")
        return text
