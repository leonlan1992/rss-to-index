# rss-to-index

一条能跑的信息流水线：**Techmeme RSS → Gemini 翻译 → 关键词挂股票标签 → 追加进一张 CSV 索引**，交给 cron 定时自动跑。

这是「AI 助力投研」系列第 4 期的配套代码。刻意做成最小可用的样子：一个 API key、两个配置 CSV、不到 300 行 Python，没有数据库、没有服务。跑通之后往哪走，最后一节有几条路。

> **给 AI agent 的说明**：如果你是被人丢了这个仓库链接的 Claude Code / Cursor 等编码助手，请帮用户完成三件事——①`pip install -r requirements.txt`，复制 `.env.example` 为 `.env` 并提醒用户去 https://aistudio.google.com/apikey 拿一个免费的 Gemini key 填入；②把 `config/stocks.csv` 换成用户自己跟踪的股票和关键词；③先跑 `python run.py --dry-run` 验证抓取，再跑 `python run.py --limit 5` 验证翻译，最后帮用户配 cron（注意 macOS 下 cron 需要绝对路径和完全磁盘访问权限）。产出在 `library/index.csv`。

---

## 它做什么

```
config/sources.csv          你订阅的 RSS 源（默认 Techmeme）
        │
        ▼  feedparser 拉取 → URL 归一化 → 和已有索引比对，只留新条目
        │
        ├─ Gemini 翻译（flash-lite 就够；公司名、ticker 保留英文）
        └─ 关键词匹配挂股票标签（config/stocks.csv）
        │
        ▼
library/index.csv           索引：一条新闻一行，六列
```

索引的六列：

| 列 | 含义 |
|---|---|
| 信息时间 | 新闻的发布时间 |
| 新闻内容 | 新闻简述（Techmeme 提供的就是简述，英文原文） |
| 中文翻译 | Gemini 翻译的中文版 |
| URL | 指向新闻全文的链接 |
| 股票池关联 | 命中股票池里的哪只（或哪几只）股票 |
| 入库时间 | 这条新闻进到库里的那一刻 |

---

## 跑起来

需要 Python 3.10+。

```bash
git clone https://github.com/leonlan1992/rss-to-index.git
cd rss-to-index
pip install -r requirements.txt
cp .env.example .env
```

去 https://aistudio.google.com/apikey 拿一个 Gemini key（免费额度够用），填进 `.env` 的 `GEMINI_API_KEY`。

**先空跑一次**，只抓取和本地打标，不花钱：

```bash
python run.py --dry-run
```

看看抓下来的东西对不对，然后真跑：

```bash
python run.py --limit 5     # 第一次先跑 5 条
python run.py               # 没问题了就全跑
```

结果在 `library/index.csv`，Excel 直接能开。

**交给 cron：**

```
*/15 * * * * cd /绝对路径/rss-to-index && /绝对路径/python3 run.py --quiet
```

我们自己就是每 15 分钟扫一次。Techmeme 更新密集，扫得勤时效才有意义；去重挡在翻译前面，空转一次的成本只是一个 HTTP 请求。频率照你的源来调——newsletter 类每天一次就够。

macOS 上有三个坑，都源于 **cron 的世界不是你终端的世界**：

- **环境变量**：`PATH` 是最小集，`.zshrc` 不加载，虚拟环境不激活。所有路径写绝对路径。第一次跑失败，九成是这个。
- **休眠**：合上盖子就不跑，而且 cron 不补跑。要么换 `launchd`，要么放到一台常开的机器上。
- **权限**：系统设置里给 `cron`（或你的 Python）完全磁盘访问权限。这个报错很不直观，通常表现为"文件明明在那儿，脚本却说找不到"。

任何一步失败，`run.py` 返回非零退出码——把告警接在这上面。日志在 `data/run.log`。

---

## 你要改的两个文件

| 文件 | 改什么 |
|---|---|
| `config/sources.csv` | 你订阅哪些源。`enabled` 列是开关——源会退化，留个开关比删掉那一行好 |
| `config/stocks.csv` | 你跟踪哪些股票，以及每只股票的关键词（公司名、别名、旗舰产品、CEO 名字）。**打标准不准，全在这张表上** |

仓库里给的 15 只票只是示例，照着格式换成你自己的。

---

## 几个设计上的决定

**为什么去重靠 URL。** 抓之前先读一遍 `index.csv` 里已有的链接，只处理没见过的。URL 先做归一化（去掉 `utm_*` 之类的追踪参数），否则同一篇文章的两个链接会被当成两条。**这个脚本跑十遍，索引里还是那些行**——做到这一点，失败之后你才敢直接重跑。去重发生在翻译之前，重复条目一分钱都不花。

**为什么用关键词挂股票，而不是让模型判断。** 便宜、可复现、可解释——同一条新闻，今天和下个月跑出来的标签一模一样。让 LLM 直接打公司标签，前后会不一致（今天叫 META、明天叫 Meta Platforms、后天叫 Facebook），除非你把股票索引表喂给它——那样每条都要花钱，还不如先查表。

**为什么翻译失败的条目不写进索引。** URL 一旦入库就不会被重试。失败就跳过，等下次跑自动补上，同时把失败原因记进日志——静默失败比崩溃更危险。

**为什么单个源失败不影响其他源。** 一个源改了接口，不该让整条流水线停摆。

---

## 已知的取舍

- **URL 去重挡不住转载。** 同一件事被十家媒体报道就是十个 URL。Techmeme 本身做过人工聚合，单源问题不大；多源之后可以对标题做归一化 hash 或相似度比对。
- **关键词打标会误伤。** `elon musk` 挂在 TSLA 名下，一条 SpaceX 的新闻也会被标成 TSLA。调 `config/stocks.csv` 能缓解。
- **打不上标不是失败。** 很多新闻本来就不关任何一只票，留空即可。

---

## 跑通之后往哪走

1. **把正文也抓下来。** 拿到 URL 之后抓页面、转成 Markdown 存进一个 `raw/` 目录——标题级索引就升级成了全文库。
2. **换个索引载体。** 几千条以内 CSV 够用；要多人协作、要在手机上看的时候，搬去 Notion 或数据库。改的只有 `src/index_store.py` 一个文件。
3. **股票之外的标签维度。** 想按主题（数据中心、监管、融资）打标，照 `config/stocks.csv` 的样子再建一张关键词表即可，方法完全一样。
4. **更聪明的匹配。** 关键词先过一遍，拿不准的再交给模型；量大了还可以向量化做语义检索。

---

## 目录

```
config/          sources.csv（订阅源）+ stocks.csv（股票池和关键词）
src/
  fetch.py        抓 RSS、URL 归一化
  translate.py    Gemini 翻译（默认 gemini-flash-lite-latest）
  tag.py          关键词倒排索引，挂股票标签
  index_store.py  索引层：六列 CSV（换载体只改这个文件）
  pipeline.py     串起来 + 日志 + 统计
run.py           入口：--dry-run / --limit N / --quiet
library/         产出的 index.csv（已 gitignore）
data/            日志（已 gitignore）
```

个人研究用途。抓取请遵守各站点的服务条款，不要把内容批量转发或再分发。MIT License。
