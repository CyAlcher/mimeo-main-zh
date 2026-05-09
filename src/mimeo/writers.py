"""Write a :class:`SkillOutput` to disk as a skill-creator-compliant directory."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .config import Settings
from .schemas import AgentsOutput, SkillOutput, Source

logger = logging.getLogger(__name__)


def write_skill(
    *,
    output: SkillOutput,
    sources: list[Source],
    settings: Settings,
) -> Path:
    """Write SKILL.md + references/*.md; returns the skill directory path."""

    skill_dir = settings.skill_dir
    skill_dir.mkdir(parents=True, exist_ok=True)
    settings.references_dir.mkdir(parents=True, exist_ok=True)

    skill_md_path = skill_dir / "SKILL.md"
    skill_md_path.write_text(
        _assemble_skill_md(output),
        encoding="utf-8",
    )

    (settings.references_dir / "principles.md").write_text(
        output.principles_md.strip() + "\n", encoding="utf-8"
    )
    (settings.references_dir / "frameworks.md").write_text(
        output.frameworks_md.strip() + "\n", encoding="utf-8"
    )
    (settings.references_dir / "mental-models.md").write_text(
        output.mental_models_md.strip() + "\n", encoding="utf-8"
    )
    (settings.references_dir / "quotes.md").write_text(
        output.quotes_md.strip() + "\n", encoding="utf-8"
    )
    # heuristics / anti-patterns are optional: models historically produced
    # empty strings on corpora that didn't surface those categories. We still
    # write the file so the SKILL.md references resolve, but fall back to a
    # short placeholder so the reader isn't staring at a blank page.
    (settings.references_dir / "heuristics.md").write_text(
        _nonempty_markdown(
            output.heuristics_md,
            placeholder=(
                "# 经验法则\n\n"
                f"本次语料中未从 {settings.expert_name} 提炼出足够独特的"
                "经验法则。\n"
            ),
        ),
        encoding="utf-8",
    )
    (settings.references_dir / "anti-patterns.md").write_text(
        _nonempty_markdown(
            output.anti_patterns_md,
            placeholder=(
                "# 反模式\n\n"
                f"本次语料中未从 {settings.expert_name} 提炼出显著的反模式。\n"
            ),
        ),
        encoding="utf-8",
    )
    (settings.references_dir / "sources.md").write_text(
        _render_sources(sources, expert=settings.expert_name),
        encoding="utf-8",
    )
    logger.info("Skill written to %s", skill_dir)
    return skill_dir


def write_agents(
    *,
    output: AgentsOutput,
    sources: list[Source],
    settings: Settings,
) -> Path:
    """Write AGENTS.md to the skill directory.

    The sources bibliography is appended as an inline section (rather than a
    separate file) since AGENTS.md is a single self-contained document.
    Returns the path to AGENTS.md.
    """
    skill_dir = settings.skill_dir
    skill_dir.mkdir(parents=True, exist_ok=True)

    content = output.content.rstrip()
    # 中文 AGENTS.md 由模板引导生成"## 来源文献"节，若模型已自行输出则
    # 不重复追加；英文 "## Sources" 兼容原版在极偶发情况下的回退。
    already_has_sources = any(
        marker in content
        for marker in ("## 来源文献", "# 来源文献", "## Sources", "# Sources")
    )
    if not already_has_sources:
        content = f"{content}\n\n{_render_sources_inline(sources, expert=settings.expert_name)}"
    else:
        content = f"{content}\n"

    agents_path = skill_dir / "AGENTS.md"
    agents_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    logger.info("AGENTS.md written to %s", agents_path)
    return agents_path


def _render_sources_inline(sources: list[Source], *, expert: str) -> str:
    lines = [
        "## 来源文献",
        "",
        f"本文基于以下 {len(sources)} 份关于 {expert} 的来源写成，"
        "正文中的 `(src_XXX)` 标注对应下方 id。",
        "",
    ]
    for s in sources:
        title = s.title or "(无标题)"
        bucket = f" — _{s.bucket}_" if s.bucket else ""
        score = f"（得分 {s.canonicity_score:.2f}）" if s.canonicity_score is not None else ""
        date = f" [{s.publish_date}]" if s.publish_date else ""
        lines.append(f"- **{s.id}**{bucket}{score}：[{title}]({s.url}){date}")
    return "\n".join(lines)


def _nonempty_markdown(text: str, *, placeholder: str) -> str:
    stripped = text.strip()
    if not stripped:
        return placeholder
    return stripped + "\n"


def _assemble_skill_md(output: SkillOutput) -> str:
    frontmatter = yaml.safe_dump(
        {"name": output.skill_name, "description": output.description.strip()},
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    ).strip()
    body = output.skill_body.strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def _render_sources(sources: list[Source], *, expert: str) -> str:
    lines = [
        f"# {expert} 所用来源文献",
        "",
        "按重要性排序的全部来源，其他 reference 文件中的 `(sources: src_XXX)` "
        "标注对应这里的 id。",
        "",
    ]
    for s in sources:
        title = s.title or "(无标题)"
        bucket = f" — _{s.bucket}_" if s.bucket else ""
        score = f"（得分 {s.canonicity_score:.2f}）" if s.canonicity_score is not None else ""
        date = f" [{s.publish_date}]" if s.publish_date else ""
        lines.append(f"- **{s.id}**{bucket}{score}：[{title}]({s.url}){date}")
    lines.append("")
    return "\n".join(lines)
