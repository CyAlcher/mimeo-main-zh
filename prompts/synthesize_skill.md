# 撰写 Agent Skill

你手里已经有一份关于 **{expert}** 的聚类语料，来自他们的文章、演讲、
访谈、播客等原始材料。你的任务是把它变成一份**可直接投产**的
Agent Skill——一个编程/咨询 Agent 读完之后就能**按 {expert} 的思路推理**。

这份 skill 的作用，是让 AI 助手在用户遇到相关场景时，能够像 {expert}
那样给出**建议、判断与批评**——不是模仿他的语气说话，而是引用他的
原则、框架与心智模型去处理用户当下的问题。

## 输出结构

返回符合 ``SkillOutput`` schema 的 JSON，字段如下：

- ``skill_name``：短 id，如 ``duan-yongping``（小写、连字符、ASCII）。
  通常就是专家姓名的 slug。
- ``description``：frontmatter 中的 description，**最重要的字段**，
  决定这个 skill 什么时候被触发。写法模仿 skill-creator：先说 skill
  做什么，再列出一串会触发它的具体情境或关键词。可以稍微"主动"一点——
  告诉 Claude 只要用户谈到该专家的领域话题就应该打开这个 skill，即使
  用户并没有点名。目标长度约 60-120 字。**必须用中文撰写。**
- ``skill_body``：frontmatter 之后的 markdown 正文，结构见下。
- ``principles_md``：写入 ``references/principles.md`` 的中文 markdown。
- ``frameworks_md``：写入 ``references/frameworks.md``。
- ``mental_models_md``：写入 ``references/mental-models.md``。
- ``quotes_md``：写入 ``references/quotes.md``。
- ``heuristics_md``：写入 ``references/heuristics.md``，列出该专家的
  经验法则/口头禅，每条一两句释义 + 引文 + source_ids。
- ``anti_patterns_md``：写入 ``references/anti-patterns.md``，列出他
  明确反对的做法，每条给出反模式描述、拒斥理由、可选原话、source_ids。

## ``skill_body`` 结构

目标行数不超过 400 行。骨架模板（内部花括号是占位说明，不要保留）：

```
# 像 {expert} 一样思考

{2-3 段综述：这个人是谁，他的思考有什么独特"形状"。收尾用一句
"当你遇到以下情形时，应当调用本技能……"}

## 核心原则

{3-5 条要点，每条一句话。每条既是信念，也是可执行的决策规则。}

更完整的推理与原话请见 ``references/principles.md``。

## {expert} 如何推理

{1-2 段说明他的推理路径：他会先问什么、强调什么、不屑于什么。
行内点名 2-3 个最重要的心智模型，其余请见 ``references/mental-models.md``。}

## 框架应用

{针对最重要的 2-3 个框架，各用一小段命名小节，给出"什么时候用"与
"步骤"。完整目录请见 ``references/frameworks.md``。}

## 他反复反对的做法

{3-6 条，用他的语气给出直接而有力的警示。完整清单与理由请见
``references/anti-patterns.md``。}

## 经验法则

{4-8 条一句话规则，反映他的日常判断习惯。完整清单请见
``references/heuristics.md``。}

## 在对话中如何使用本技能

{对 AI 的具体行为指引：当用户陷入上述情境时，按名字引用相关原则或
框架，结合用户上下文给建议，并说明这个想法来自哪里
（如"{expert} 把这个称作 X"）。不要扮演成他本人——借用他的思考，
不用他的口吻说话。}
```

## 文风规则

- 每条规则要讲清**为什么**，不要靠全大写 MUST 堆叠气势。
- 正文引用 reference 文件时用 ``references/<file>.md`` 路径。正文不超
  过 400 行；深入的细节塞到 reference 文件里。
- 正文引用的原话必须是**原文、不改写**，并标注出处标题。完整金句列表
  放在 ``quotes.md``。
- frontmatter 里的 description 必须触发在**具体场景**上（例如："投资
  决策、公司基本面、估值与安全边际、能力圈"），不要泛泛而谈。从
  themes 里派生关键词。
- **所有输出字段与 markdown 文件必须使用简体中文。人名、机构、英文
  书名、公司 ticker 保留英文原文即可。**

## ``references/*.md`` 结构

每份 reference 文件都要能单独阅读：先一小段引言，再按 H2 分小节，
每节写：

- 该概念的规范性陈述
- 简短的理由
- 代表性原话（有的话），用 blockquote 呈现
- 来源 id，格式形如 ``(sources: src_001, src_014)``

``quotes.md`` 只是一份最有代表性的原话清单，每条 blockquote 后跟
source id。

``heuristics.md`` 同样简洁：引言 + 一串 H2 小节或 bullet 列表，每条
简短，末尾标注 ``(sources: src_XXX)``。

``anti-patterns.md`` 形制与 ``principles.md`` 一致：引言 + H2 小节，
每节含 1-2 句拒斥理由、可选原话、source ids。

## 来源 bibliography

``references/sources.md`` 由程序根据真实 URL 列表自动生成，**不需要**
你产出。你只需关心上述四份 reference 文件。

## 输入数据

专家姓名：{expert}{expert_context}

如果上方带了消歧限定语，请把它自然融进 frontmatter 的 description，
确保 skill 被触发时对应的是正确的那个人（例如："段永平，步步高创始人、
投资人"）。正文里不需要再重复这个限定语，description 一次就够。

聚类语料（JSON）：

```json
{corpus_json}
```
