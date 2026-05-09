# 中国价值投资者示例合集

> 中文版新增内容，不修改原项目的任何示例。

mimeo-zh 可以像处理 Buffett、Munger 一样，把国内的长期主义者提炼成
一份 `SKILL.md` 或 `AGENTS.md`。以下是我们维护的三位代表人物的**默认
命令模板**，直接复制即可运行。

## 1. 段永平（Duan Yongping）

步步高/OPPO/vivo 创始人，网易（NTES）早期重要投资人，国内最知名的
"价值投资布道者"之一，长期在「i 问财」「雪球」留下大量公开答问。

```bash
uv run mimeo "段永平" \
  --provider deepseek \
  --model deepseek-chat \
  --disambiguator "步步高/OPPO/vivo 创始人，网易等公司早期重要投资人" \
  --format both \
  --max-sources 30
```

**建议关注的触发词（会自动进入 description）**：商业模式、本分、
敢为天下后、不为清单、能力圈、长期、企业文化。

## 2. 但斌（Dan Bin）

东方港湾董事长，长期持有贵州茅台、腾讯等核心资产的坚定实践者，
"时间的玫瑰"系列公开演讲/书籍留下大量可被采集的原话与观点。

```bash
uv run mimeo "但斌" \
  --provider deepseek \
  --model deepseek-chat \
  --disambiguator "东方港湾投资管理公司董事长，价值投资与长期持有倡导者" \
  --max-sources 30 \
  --format skill
```

**建议关注的触发词**：长期持有、核心资产、时间的玫瑰、穿越牛熊、
消费龙头、确定性。

## 3. 李录（Li Lu）

Himalaya Capital 创始人，Charlie Munger 最信任的华人投资人，著有
《文明、现代化、价值投资与中国》。其在北大光华、哥伦比亚商学院等的
公开演讲是最核心的一手资料。

```bash
uv run mimeo "李录" \
  --provider deepseek \
  --model deepseek-reasoner \
  --disambiguator "Himalaya Capital 创始人，芒格的长期合作者，《文明、现代化、价值投资与中国》作者" \
  --deep-research \
  --max-sources 40
```

**建议关注的触发词**：现代化、价值投资、能力圈、复利、文明演化、
中国机会、概率思维。

## 一次跑三个人的小脚本（可选）

```bash
for name in "段永平" "但斌" "李录"; do
  uv run mimeo "$name" \
    --provider deepseek \
    --format both \
    --max-sources 30 \
    --assume-unambiguous
done
```

跑完后你会得到三个目录：

```
output/
├── duan-yongping/
├── dan-bin/
└── li-lu/
```

每个目录下都带 `SKILL.md` + `references/` + `AGENTS.md`，可以直接
作为 Claude Code / Cursor 的技能库或常驻提示注入。

## 注意事项

- mimeo-zh **不会抓取付费墙后的内容**，也不会替你下载受版权保护的
  书籍正文。所有来源都来自 Parallel 搜索能到达的公开网页与 YouTube
  字幕。引文逐条做回指核验，不匹配的会被剔除。
- 这三人都属于**活跃在世的投资人/经营者**，公开观点仍在演化，输出
  反映的是"截至本次运行的公开材料"。不构成任何投资建议。
- 输出按原项目 MIT 协议继承分发；但产物里引用的他人原话仍归原作者
  所有，使用时请自行判断合规性。
