"""Stage 0: resolve which real person the expert name refers to.

Common names ("John Smith", "Mike Johnson", even single first names) match
many notable people. Without a disambiguation step, downstream discovery
would silently blend their bodies of work into a single incoherent skill.

This module runs one Parallel Search + one LLM classification call to
either:

* confirm the name is unambiguous and attach a short qualifier (used by
  later prompts so the model stays anchored to the right person), or
* list candidates and either prompt the user to pick (TTY) or fail loudly
  with a useful error message (non-interactive).

Results are cached under ``_workspace/identity.<model>.json`` so repeat runs
skip the classification call.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace

from rich.console import Console

from .config import Settings
from .llm import LLMClient
from .parallel_client import ParallelClient
from .schemas import ExpertCandidate, IdentityResolution

logger = logging.getLogger(__name__)


class AmbiguousNameError(RuntimeError):
    """名字存在歧义、又无法在非交互环境下让用户选择时抛出。"""

    def __init__(self, *, expert_name: str, candidates: list[ExpertCandidate]) -> None:
        self.expert_name = expert_name
        self.candidates = candidates
        lines = [
            f"“{expert_name}” 可能指向多位公众人物，"
            "请用 --disambiguator \"<简短限定语>\" 指定，例如：",
        ]
        for cand in candidates:
            lines.append(f"  - {cand.name}：{cand.description}")
        lines.append(
            "或加上 --assume-unambiguous 跳过此检查（不推荐）。"
        )
        super().__init__("\n".join(lines))


async def resolve_identity(
    *,
    settings: Settings,
    parallel: ParallelClient,
    llm: LLMClient,
    console: Console | None = None,
) -> Settings:
    """Ensure ``settings.expert_description`` is set.

    Returns a (possibly new) Settings with ``expert_description`` filled in.
    Raises :class:`AmbiguousNameError` when the name is ambiguous and we
    can't prompt the user (no TTY, no console, etc.).
    """

    if settings.expert_description:
        logger.info(
            "使用用户提供的消歧限定语：%s（%s）",
            settings.expert_name,
            settings.expert_description,
        )
        return settings

    if settings.assume_unambiguous:
        logger.info(
            "跳过身份消歧（--assume-unambiguous）：%s",
            settings.expert_name,
        )
        return settings

    cache_path = settings.workspace_dir / f"identity.{settings.model_cache_id}.json"
    resolution: IdentityResolution | None = None
    if cache_path.exists() and not settings.refresh:
        try:
            resolution = IdentityResolution.model_validate_json(
                cache_path.read_text(encoding="utf-8")
            )
            logger.info("命中身份消歧缓存：%s", cache_path)
        except Exception:  # noqa: BLE001
            logger.warning("身份消歧缓存损坏，重新解析")
            resolution = None

    if resolution is None:
        if console is not None:
            console.print(
                f"[dim]正在为 “{settings.expert_name}” 做身份消歧……[/dim]"
            )
        resolution = await _classify(
            settings=settings, parallel=parallel, llm=llm
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            resolution.model_dump_json(indent=2), encoding="utf-8"
        )

    return _apply_resolution(settings, resolution, console=console)


def _apply_resolution(
    settings: Settings,
    resolution: IdentityResolution,
    *,
    console: Console | None,
) -> Settings:
    if not resolution.is_ambiguous:
        description = resolution.resolved_description
        if description:
            logger.info(
                "身份确定：%s（%s）", settings.expert_name, description
            )
            if console is not None:
                console.print(
                    f"[green]已确定[/green] “{settings.expert_name}” → "
                    f"{description}"
                )
            return replace(settings, expert_description=description)
        # 名字无歧义但没拿到描述（比如搜索证据极少），继续跑即可。
        if console is not None:
            console.print(
                f"[yellow]未找到关于 “{settings.expert_name}” 的传记证据，"
                "但将按无歧义继续执行。[/yellow]"
            )
        return settings

    # 以下都是有歧义的分支。
    if console is not None and sys.stdin.isatty():
        picked = _prompt_choice(console, settings.expert_name, resolution.candidates)
        if picked is not None:
            if console is not None:
                console.print(
                    f"[green]已选[/green] {picked.name} —— {picked.description}"
                )
            return replace(settings, expert_description=picked.description)

    raise AmbiguousNameError(
        expert_name=settings.expert_name, candidates=resolution.candidates
    )


def _prompt_choice(
    console: Console,
    expert_name: str,
    candidates: list[ExpertCandidate],
) -> ExpertCandidate | None:
    if not candidates:
        return None

    from rich.prompt import IntPrompt

    console.print()
    console.rule(f"[bold yellow]姓名存在歧义：{expert_name}[/bold yellow]")
    console.print(
        f"[bold]{expert_name}[/bold] 对应多位公众人物，"
        "请选一位继续，或按 Ctrl-C 终止。"
    )
    for i, cand in enumerate(candidates, start=1):
        console.print(f"  [bold]{i}.[/bold] {cand.name} —— {cand.description}")
        if cand.evidence:
            console.print(f"     [dim]{cand.evidence}[/dim]")
    choice = IntPrompt.ask(
        "你的选择",
        choices=[str(i) for i in range(1, len(candidates) + 1)],
        default=1,
    )
    return candidates[choice - 1]


async def _classify(
    *,
    settings: Settings,
    parallel: ParallelClient,
    llm: LLMClient,
) -> IdentityResolution:
    """检索传记证据并让 LLM 判断是否存在歧义。"""

    search = await parallel.search(
        objective=(
            f"识别名为 “{settings.expert_name}” 的知名人物，"
            "给出短传记片段：职业、机构、所在领域。"
            "如果世界上只有一位公众人物以此名著称，请明说。"
        ),
        search_queries=[
            f"{settings.expert_name} 是谁",
            f'"{settings.expert_name}" 简介',
            f'"{settings.expert_name}" 维基百科',
            f"who is {settings.expert_name}",
            f'"{settings.expert_name}" biography',
        ],
        max_chars_total=10_000,
    )

    rows: list[dict[str, object]] = []
    for r in (getattr(search, "results", None) or [])[:20]:
        url = str(getattr(r, "url", "") or "")
        if not url:
            continue
        rows.append(
            {
                "url": url,
                "title": getattr(r, "title", None),
                "excerpts": list(getattr(r, "excerpts", []) or [])[:3],
            }
        )

    if not rows:
        logger.warning(
            "未找到关于 “%s” 的搜索证据，视为无歧义",
            settings.expert_name,
        )
        return IdentityResolution(
            is_ambiguous=False,
            resolved_description=None,
            notes="身份消歧阶段未找到任何传记证据。",
        )

    system = (
        "你是人名消歧专家。只有当两位及以上的**知名**人物共享同一个名字、"
        "而且仅凭姓名都可能被指代时，该名字才算“有歧义”。无名小辈或极度"
        "冷门的同名者不算。不确定时一律按无歧义处理。不要凭空编造候选。"
        "resolved_description 必须使用简体中文；人名、机构名英文原文保留。"
    )
    user = (
        f"用户给出的专家名：“{settings.expert_name}”\n\n"
        "搜索证据（JSON）：\n"
        f"{json.dumps(rows, indent=2, ensure_ascii=False)}\n\n"
        "请判断该名是否存在歧义：\n"
        "- 无歧义：is_ambiguous=false，resolved_description 写一句简短中文"
        "限定语（例如“步步高/OPPO/vivo 创始人，早期投资人”）。"
        "不超过 40 字，不要重复名字、不要以逗号开头。\n"
        "- 有歧义：is_ambiguous=true，列出 2-5 位不同的候选，"
        "description 与 evidence 都用中文、基于证据、不要臆造。"
    )

    return await llm.structured(
        system=system,
        user=user,
        schema=IdentityResolution,
        temperature=0.1,
    )
