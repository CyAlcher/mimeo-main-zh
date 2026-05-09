# mimeo-zh — 中文版"专家思维克隆"

> *mim·e·o* — 拷贝、复制、临摹。

**把一位专家的思考方式克隆进你的编程 Agent / 投资副驾。**

> 🇨🇳 本项目为 [K-Dense-AI/mimeo](https://github.com/K-Dense-AI/mimeo)
> 的中文改造版（以下简称 **mimeo-zh**）。原项目 MIT 协议，本项目亦以
> MIT 协议继续开源，版权归原作者所有，见 [LICENSE](./LICENSE)。本中文
> 版的改造范围仅限于：**汉化文档/提示词/日志输出、增加国产 DeepSeek
> 直连入口、补充中国价值投资者示例**；原有代码结构与核心算法保持不动。

![mimeo pipeline](docs/mimeo-explainer.png)

## 它在干什么

每个领域都有人用一辈子公开思考："费曼"之于物理和第一性原理，"达尔文"
之于观察与慢假设，"图灵"之于计算与形式证明；投资领域则有巴菲特、
芒格，以及**段永平、但斌、李录**这三位被称为"中国价值投资代表"的
华人长期主义者。他们的演讲、访谈、股东信与财报解读里藏着真正有用的
心智模型，问题是没人有时间把它们读完、消化、再稳定地用到自己的决策
里。

与此同时，Agent 对这种级别的指导非常饥渴。一份写得好的 `SKILL.md` 或
`AGENTS.md` 就是一根杠杆——它重塑 Agent 的推理方式、默认权衡和常用
套路。但**手写**这样一份资料本身就是多周的工程：读一切、做综述、
把不显而易见的思路摘出来。

**mimeo-zh 自动化的就是这件事。** 你给它一个人名，它会：
自动上网读相关公开材料 → 用前沿大模型分条蒸馏 → 跨来源聚类合并 →
校验每条原话 → 产出可直接加载的中文 SKILL.md 或 AGENTS.md。

输出有两种形态：

- **Agent Skill**：一份 `SKILL.md` 加上 `references/` 子目录，符合
  [skill-creator](https://github.com/anthropics/skills) 规范。适合做
  按需触发的技能库。
- **AGENTS.md**：一份常驻文件，Agent 每次在该目录下启动都会读。适合把
  某位专家的默认立场直接装进 Agent 的日常行为。

用 `--format skill`（默认）、`--format agents` 或 `--format both` 选择。

## 中文版在原版基础上做了什么

1. **所有文档、提示词、日志输出、评审报告全部中文化**，并强制模型
   以简体中文生成 `SKILL.md`、`AGENTS.md` 以及全部 `references/*.md`；
   人名、公司、英文书名保留原文。
2. **原生支持 DeepSeek**：新增 `--provider deepseek` 入口，直连
   `https://api.deepseek.com`，国内网络友好、价格友好。默认模型
   `deepseek-chat`，也可切 `deepseek-reasoner`。OpenRouter 路由仍然
   保留，二选一即可。
3. **补充 3 位"中国巴菲特"示例**（不删减原项目任何内容，仅作添加）：
   - **段永平**（步步高/OPPO/vivo 创始人，网易等公司早期重要投资人，
     国内"价值投资布道者"之一）
   - **但斌**（东方港湾董事长，"长期主义"实践者，以长期持有优质龙头
     著称）
   - **李录**（Himalaya Capital 创始人，芒格最信任的华人投资人之一，
     其《文明、现代化、价值投资与中国》被视为国内价投教材）

   示例命令见下文「开箱即用的中国投资家示例」。
4. 其它：
   - 缓存按 provider 隔离，切换 `openrouter ↔ deepseek` 不会串缓存。
   - `.env.example` 与 README 的环境变量全部双语对照、可直接复制。
   - 保留原版的 Parallel 搜索/抓取、引文核验、对抗式评审、头像生成
     等所有能力。

## 流水线

0. **身份消歧**：用 Parallel Search + 一次 LLM 分类，防止"张三"在
   经济学家、篮球教练和作家之间被拼成一个四不像。
1. **来源发现**：通过 [Parallel](https://parallel.ai) Search API 在
   八个意图桶（文章、演讲、访谈、播客、框架、书籍、论文、信件）里
   广撒网，让现代操盘手和历史科学家都能覆盖到。
2. **内容抓取**：网页走 Parallel 摘要/正文提取；YouTube 走
   `youtube-transcript-api`；可选的本地 Whisper 能转写播客音频。
3. **单源蒸馏**：走 OpenRouter 或 DeepSeek 官方 API（由
   `--provider` 决定）做结构化抽取——原则、框架、心智模型、金句、
   经验法则、反模式。超长材料会按段落切块并行蒸馏后再合并，避免
   "默默被截断"。
4. **聚类合并**：跨来源合并同义概念、按频次排序。语料太大时按预算
   分批聚类再内存合并。
5. **引文核验**：把每条 representative_quote 与已抓取的源文本做模糊
   匹配，对不上的删掉并写进 `_workspace/quote_verification.md` 审计
   日志。可用 `--no-verify-quotes` 关闭。
6. **著作**：写 SKILL 及可选的 AGENTS.md，并产出
   `heuristics.md`、`anti-patterns.md` 等 reference 文件，全部中文。
7. **对抗式评审**：再跑一轮"对抗式编辑"LLM，把 0-10 打分和分类问题
   清单写入 `_workspace/critique_skill.md`（以及相关的
   `critique_agents.md`）。只诊断、不自动改写。`--no-critique` 关闭。
8. **画像头像**：用 OpenRouter 的图像模型产一张油画风头像，保存为
   `avatar.png`。该步是尽力而为，失败会被日志吞掉。`--no-avatar` 关闭。

## 安装

```bash
# uv（推荐）
uv sync

# 或 pip
pip install -e .

# 如需转写播客音频（可选、更慢更重）
uv sync --extra full
```

把 `.env.example` 复制成 `.env` 并填上对应字段：

```env
# 使用 DeepSeek（国内推荐）
MIMEO_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
PARALLEL_API_KEY=...

# 或使用 OpenRouter
# MIMEO_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-...
# PARALLEL_API_KEY=...
```

## 基本用法

```bash
# 走 DeepSeek 官方 API
uv run mimeo "段永平" --provider deepseek --model deepseek-chat

# 走 OpenRouter
uv run mimeo "Naval Ravikant" --provider openrouter
```

## 开箱即用的中国投资家示例

> 这 3 条是**中文版新增**，不替换原项目的任何示例。

```bash
# 段永平 —— 步步高/OPPO/vivo 创始人；国内"价值投资布道者"
uv run mimeo "段永平" \
  --provider deepseek \
  --model deepseek-chat \
  --disambiguator "步步高/OPPO/vivo 创始人，网易等公司早期重要投资人" \
  --format both

# 但斌 —— 东方港湾董事长，长期主义实践者
uv run mimeo "但斌" \
  --provider deepseek \
  --model deepseek-chat \
  --disambiguator "东方港湾投资管理公司董事长，价值投资与长期持有倡导者" \
  --max-sources 30

# 李录 —— Himalaya Capital 创始人，芒格最看重的华人投资人
uv run mimeo "李录" \
  --provider deepseek \
  --model deepseek-reasoner \
  --disambiguator "Himalaya Capital 创始人，芒格的长期合作者，《文明、现代化、价值投资与中国》作者" \
  --deep-research
```

> 如果你的网络能直连 openrouter.ai，把 `--provider deepseek` 换成
> `--provider openrouter` 并改模型 slug 即可（推荐
> `deepseek/deepseek-chat` 或 `google/gemini-3.1-pro-preview`）。

更细的三人对照版提示词与说明见 [`examples/china-value-investors.md`](./examples/china-value-investors.md)。

## 所有 CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--provider {openrouter,deepseek}` | `openrouter` | LLM 服务商；`deepseek` 直连官方 API，国内推荐 |
| `--model SLUG` | 取决于 provider | provider=deepseek 时默认 `deepseek-chat`；provider=openrouter 时默认 `google/gemini-3.1-pro-preview` |
| `--format {skill,agents,both}` / `-f` | `skill` | 输出形态 |
| `--mode {text,captions,full}` | `captions` | 抓取深度 |
| `--max-sources N` | `25` | 保留的最大来源数 |
| `--deep-research` | 关 | 额外跑一次 Parallel 深度研究并合入 |
| `--disambiguator TEXT` / `-d` | 自动 | 同名人消歧短描述；设置后跳过自动消歧 |
| `--assume-unambiguous` | 关 | 完全跳过身份消歧（非交互脚本用） |
| `--output-dir PATH` | `./output` | 输出根目录 |
| `--refresh` | 关 | 忽略 `_workspace/` 下缓存，全量重跑 |
| `--concurrency N` | `5` | 单源蒸馏并发数 |
| `--verify-quotes / --no-verify-quotes` | 开 | 著作前逐条核验 representative_quote |
| `--critique / --no-critique` | 开 | 著作后做对抗式评审 |
| `--avatar / --no-avatar` | 开 | 生成油画风头像 |
| `--avatar-model SLUG` | `openai/gpt-5.4-image-2` | 头像模型 slug |

## 同名歧义

当名字可能对应多位公众人物时，mimeo-zh 会先做消歧：

```bash
# 交互式：列出候选让你选
uv run mimeo "张三"

# 脚本式：一上来就钉死是哪位
uv run mimeo "段永平" -d "步步高/OPPO/vivo 创始人，网易投资人"

# 非交互且确信唯一：直接跳过
uv run mimeo "Charlie Munger" --assume-unambiguous
```

非 TTY 环境下如果没给 `--disambiguator`，mimeo-zh 会报错并列出候选。
结果缓存在 `_workspace/identity.<model>.json`，下次直接命中；
`--refresh` 可以让缓存失效。

## 输出目录结构

`--format skill`（默认）：

```
output/duan-yongping/
├── SKILL.md
├── references/
│   ├── principles.md
│   ├── frameworks.md
│   ├── mental-models.md
│   ├── heuristics.md
│   ├── anti-patterns.md
│   ├── quotes.md
│   └── sources.md
├── avatar.png
└── _workspace/
```

`--format agents`：

```
output/duan-yongping/
├── AGENTS.md
├── avatar.png
└── _workspace/
```

`--format both`：两类产物共存；discovery/fetch/distill/cluster 缓存共享
（头像也只生成一次），第二类产物几乎是"白送"。

## 架构

```
cli -> pipeline -> identity   （Parallel 搜索 + LLM：是否歧义、选哪一位）
                -> discovery  （Parallel 搜索，8 意图桶）
                -> fetch      （网页 / YouTube / 可选音频）
                -> distill    （逐源抽取，超长材料切块合并）
                -> research?  （Parallel 深度研究伪来源）
                -> cluster    （跨源合并 + 排名，过大语料分批）
                -> verify?    （逐条引文模糊匹配）
                -> author     （skill / agents / both）-> writers
                -> critique?  （对抗式评审 -> _workspace/critique_*.md）
                -> avatar?    （OpenRouter 图像模型 -> avatar.png）
```

## 本地联通性测试

`scripts/test_deepseek.py` 是一个极简的联通性脚本，用你 `.env` 里
配置的 `DEEPSEEK_API_KEY` 走一次最短调用：

```bash
uv run python scripts/test_deepseek.py
```

返回 `✅ DeepSeek 正常` 表示凭证、网络、默认模型都能跑通。

## 许可证

本项目沿用原作者 MIT 协议，不做任何修改。见 [LICENSE](./LICENSE)。
原项目主页：<https://github.com/K-Dense-AI/mimeo>。
中文版所做的修改全部在本仓库（`mimeo-main-zh`）内完成，不牵扯对原
仓库的任何侵权主张，特此声明。

## 致谢

- 原项目 [K-Dense-AI/mimeo](https://github.com/K-Dense-AI/mimeo) 的
  架构与流水线设计是本项目的基石；中文版仅做本地化与国产 LLM 适配。
- 段永平、但斌、李录三位长期写作/访谈公开记录的坚持，让国内价值投资
  社区受益良多。
