# rss-to-notion

一条能跑的信息流水线：**RSS → 本地暂存 → Gemini 翻译 → 关键词打股票标签 → 写进 Notion**，用 cron 每天自动跑。

这是「AI 助力投研」系列第 4 期的配套代码。第 3 期讲了资料库该长什么样（湖 + 索引），这一期把「你手动往 `update/` 里放材料」换成一条自己运转的流水线。

代码是给你改的，不是给你直接用的——`config/` 下三个 CSV 就是你要动的地方。

---

## 它做什么

```
config/sources.csv        你订阅的 RSS 源
        │
        ▼  feedparser 拉取，URL 归一化后按 link 去重
   SQLite 暂存表 (processed=0)          ← 相当于第 3 期的 update/ 目录
        │
        ├─ Gemini 翻标题（公司名、ticker 保留英文）
        ├─ 关键词匹配打股票标签（config/stocks.csv）
        └─ 关键词匹配打主题标签（config/topics.csv）
        │
        ▼  写入 Notion，relation 挂到股票池表
   Notion「信息索引」表 ←──relation──→ Notion「股票池」表
        │
        ▼  回写 processed=1 + notion_page_id
```

跑完之后，你在 Notion 里打开任意一只股票，就能看到所有和它相关的新闻——这是 relation 换来的，也是这条流水线最值钱的地方。

---

## 跑起来

需要 Python 3.10+。

**1. 装依赖**

```bash
git clone https://github.com/<your-name>/rss-to-notion.git
cd rss-to-notion
pip install -r requirements.txt
cp .env.example .env
```

**2. 拿两个 key**

- Gemini：https://aistudio.google.com/apikey ，填进 `.env` 的 `GEMINI_API_KEY`
- Notion：https://www.notion.so/my-integrations 建一个 integration，把 secret 填进 `NOTION_TOKEN`

**3. 建 Notion 的两张表**

在 Notion 里随便建一个页面当容器，右上角 `···` → `Connections` → 把你的 integration 加进去（**不做这一步后面一定 404**）。复制这个页面的 id 填进 `NOTION_PARENT_PAGE_ID`，然后：

```bash
python scripts/bootstrap_notion.py
```

它会建好「信息索引」和「股票池」两张表、把 `config/stocks.csv` 里的股票填进去，最后打印两个 id——填回 `.env`。

**4. 先空跑一次**

```bash
python run.py --dry-run
```

只抓取和本地打标，不花钱、不写 Notion。看看抓下来的东西对不对。

**5. 真跑**

```bash
python run.py --limit 5     # 第一次先跑 5 条
python run.py               # 没问题了就全跑
```

**6. 交给 cron**

```
0 8,20 * * * cd /绝对路径/rss-to-notion && /绝对路径/python3 run.py --quiet
```

macOS 上有三个坑，都源于 **cron 的世界不是你终端的世界**：

- **环境变量**：`PATH` 是最小集，`.zshrc` 不加载，虚拟环境不激活。所有路径写绝对路径。第一次跑失败，九成是这个。
- **休眠**：合上盖子就不跑，而且 cron 不补跑。要么换 `launchd`，要么放到一台常开的机器上。
- **权限**：系统设置里给 `cron`（或你的 Python）完全磁盘访问权限。这个报错很不直观，通常表现为"文件明明在那儿，脚本却说找不到"。

有任何一步失败，`run.py` 会返回非零退出码——把告警接在这上面。

---

## 你要改的三个文件

| 文件 | 改什么 |
|---|---|
| `config/sources.csv` | 你订阅哪些源。`enabled` 列是开关——源会退化，留个开关比删掉那一行好 |
| `config/stocks.csv` | 你跟踪哪些股票，以及每只股票的关键词（公司名、别名、旗舰产品、CEO 名字）。**打标的准确率全在这张表上** |
| `config/topics.csv` | 主题标签和它们的关键词 |

改完 `stocks.csv` 之后，记得重新跑一次 `bootstrap_notion.py --no-seed` 之外的方式把新股票补进 Notion 的股票池表，否则 relation 挂不上。

---

## 几个设计上的决定

**为什么先落库再处理。** 抓取和处理分开，中间隔一张暂存表。`processed=0` 就是「还没建索引」，任何一步失败，那条记录还留在表里，下次跑会自动补上。

**为什么幂等这么重要。** `link` 上有唯一约束，`INSERT OR IGNORE` 抓十遍也只有一行；`title_cn` 有值就跳过翻译。做到这两条，失败之后你才敢直接重跑。

**为什么先写 Notion 再回写 processed。** 反过来的话，中途崩一次就会留下「暂存表说处理过、Notion 里却没有」的幽灵记录，排查起来非常难受。

**为什么只翻标题。** 标题是索引字段，要能被扫、被搜；正文躺在原网页里，等你真要读那一篇的时候再说。翻全文的成本是翻标题的几十倍，而你 95% 的标题只会扫一眼。

**为什么用关键词打标，而不是让模型判断。** 便宜、可复现、可解释。模型该留给关键词搞不定的少数情况。

**为什么 relation 要先查 page id。** Notion 的关联字段要的是目标页的 id，不是 ticker 字符串。所以每次入库前先把股票池整张表拉下来，在内存里建 `ticker → page_id` 的映射。成本在这儿，收益也在这儿——存的是 id 而不是字符串，公司那一侧才能把材料全找出来。

---

## 已知的取舍

- **关键词打标会误伤。** 比如 `elon musk` 挂在 TSLA 名下，于是一条 SpaceX 的新闻也会被标成 TSLA。这是关键词法的固有代价，调 `stocks.csv` 能缓解，想彻底解决得让模型来判断——但那要花钱，而且不可复现。
- **打不上标不是失败。** 很多新闻本来就不关任何一只票，留空即可。强行挂一个标签比不挂更糟。
- **只做到标题级索引。** `内容概要` 和 `原文存档` 两个字段留空了——抓正文、清洗、存进「湖」是自然的下一步，但那会让这个仓库大一倍。想做的话，从 `src/fetch.py` 里加一步正文抓取开始。
- **没有实现告警推送。** `run.py` 返回非零退出码，接企业微信、Telegram 还是邮件，看你自己。

---

## 目录

```
config/          你要改的三个 CSV
src/
  db.py          SQLite 暂存层（换 Supabase / Postgres 只需要重写这个文件）
  fetch.py       抓 RSS、URL 归一化、去重入库
  translate.py   Gemini 翻标题
  tag.py         关键词倒排索引，打股票和主题标签
  notion_sink.py 写 Notion，处理 relation 映射
  pipeline.py    串起来 + 日志 + 统计
scripts/
  bootstrap_notion.py   一次性建两张 Notion 表
run.py           入口
data/            SQLite 和日志（已 gitignore）
```

---

## 说明

个人研究用途。抓取请遵守各站点的 robots.txt 和服务条款，不要把抓下来的内容批量转发或再分发。

MIT License。
