"""编排器：为单个专家端到端跑完所有流水线阶段。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.panel import Panel

from .avatar import generate_avatar
from .config import Settings, ensure_dirs
from .critique import critique_agents, critique_skill
from .discovery import discover_sources
from .distill import distill_all
from .fetchers import fetch_all
from .identity import resolve_identity
from .llm import LLMClient
from .parallel_client import ParallelClient
from .research import deep_research
from .schemas import Extraction, FetchedContent, Source
from .synthesize import author_agents, author_skill, cluster_corpus
from .verify import verify_quotes
from .writers import write_agents, write_skill

logger = logging.getLogger(__name__)


async def run_pipeline(
    settings: Settings,
    *,
    console: Console | None = None,
    on_stage: Callable[[str, str], None] | None = None,
    parallel: ParallelClient | None = None,
    llm: LLMClient | None = None,
) -> Path:
    """跑完整条流水线，返回生成 skill 的目录路径。

    ``parallel`` 和 ``llm`` 都是可注入的，便于测试传假对象。生产环境下
    默认从环境变量读取凭证。
    """

    console = console or Console()
    ensure_dirs(settings)

    def stage(name: str, detail: str = "") -> None:
        console.rule(f"[bold cyan]{name}")
        if detail:
            console.print(detail)
        if on_stage:
            on_stage(name, detail)

    expert_line = settings.expert_name
    if settings.expert_description:
        expert_line = f"{settings.expert_name}（{settings.expert_description}）"
    console.print(
        Panel(
            (
                f"[bold]专家:[/bold] {expert_line}\n"
                f"[bold]输出格式:[/bold] {settings.format}\n"
                f"[bold]抓取模式:[/bold] {settings.mode}\n"
                f"[bold]最大来源数:[/bold] {settings.max_sources}\n"
                f"[bold]深度检索:[/bold] {'开启' if settings.deep_research else '关闭'}\n"
                f"[bold]引文核验:[/bold] {'开启' if settings.verify_quotes else '关闭'}\n"
                f"[bold]对抗式评审:[/bold] {'开启' if settings.critique else '关闭'}\n"
                f"[bold]头像生成:[/bold] {'开启 (' + settings.avatar_model + ')' if settings.generate_avatar else '关闭'}\n"
                f"[bold]LLM 服务商:[/bold] {settings.provider}\n"
                f"[bold]LLM 模型:[/bold] {settings.model}\n"
                f"[bold]输出目录:[/bold] {settings.skill_dir}"
            ),
            title="mimeo-zh",
            border_style="cyan",
        )
    )

    if parallel is None:
        parallel = ParallelClient()
    if llm is None:
        llm = LLMClient(model=settings.model, provider=settings.provider)

    # 阶段 0：先消歧，再烧搜索费。一次 Search + 一次 LLM 分类，
    # 避免把同名的两个人捏成一个四不像 skill。
    settings = await resolve_identity(
        settings=settings, parallel=parallel, llm=llm, console=console
    )

    write_skill_flag = settings.format in ("skill", "both")
    write_agents_flag = settings.format in ("agents", "both")
    # 基础 4 步 = discover/fetch/distill/cluster；每种输出再各加一次著作，
    # critique 开启时每种输出再额外加一次评审。verify-quotes 与 deep-research
    # 都是旁路步骤，不计入总步数。
    total_stages = (
        4
        + int(write_skill_flag)
        + int(write_agents_flag)
        + (int(write_skill_flag) + int(write_agents_flag)) * int(settings.critique)
    )

    stage(
        f"1/{total_stages} 来源发现",
        "在论文、演讲、访谈、播客、书籍等八个意图桶里搜索……",
    )
    sources: list[Source] = await discover_sources(
        settings=settings, parallel=parallel, llm=llm
    )
    console.print(f"已挑选 [bold]{len(sources)}[/bold] 份来源。")
    if not sources:
        raise RuntimeError(
            "未发现任何来源。请检查 PARALLEL_API_KEY 与专家名。"
        )

    stage(f"2/{total_stages} 内容抓取", "逐条抓取每份来源的全文……")
    fetched: list[FetchedContent] = await fetch_all(
        sources, settings=settings, parallel=parallel
    )
    console.print(
        f"成功抓取 [bold]{len(fetched)}[/bold] / {len(sources)} 份来源，"
        f"共 {sum(f.char_count for f in fetched):,} 字符。"
    )

    if settings.deep_research:
        stage(
            f"2.5/{total_stages} 深度检索",
            "调用 Parallel Task API 做深度研究（可能需要几分钟）……",
        )
        pair = await deep_research(settings=settings, parallel=parallel)
        if pair:
            research_source, research_content = pair
            sources.append(research_source)
            fetched.append(research_content)
            console.print(
                f"深度研究报告已作为 [bold]{research_source.id}[/bold] 入库 "
                f"（{research_content.char_count:,} 字符）。"
            )
        else:
            console.print(
                "[yellow]深度检索失败或返回空，跳过继续。[/yellow]"
            )

    stage(
        f"3/{total_stages} 单源蒸馏",
        "从每份来源中抽取原则、框架、心智模型与金句……",
    )
    extractions: list[Extraction] = await distill_all(
        sources=sources, fetched=fetched, settings=settings, llm=llm
    )
    console.print(
        f"已将 [bold]{len(extractions)}[/bold] 份来源蒸馏为结构化抽取。"
    )

    stage(f"4/{total_stages} 聚类合并", "将所有抽取合并为统一语料……")
    corpus = await cluster_corpus(
        extractions=extractions, settings=settings, llm=llm
    )
    console.print(
        f"聚类结果：{len(corpus.principles)} 条原则 / "
        f"{len(corpus.frameworks)} 套框架 / "
        f"{len(corpus.mental_models)} 个心智模型 / "
        f"{len(corpus.signature_quotes)} 条金句。"
    )

    if settings.verify_quotes:
        console.rule("[bold cyan]引文核验")
        corpus, verify_report = verify_quotes(
            corpus=corpus, fetched=fetched, settings=settings
        )
        if verify_report.total == 0:
            console.print("[dim]无引文需要核验。[/dim]")
        else:
            pass_pct = verify_report.pass_rate * 100
            style = "green" if verify_report.pass_rate >= 0.9 else "yellow"
            console.print(
                f"[{style}]已核验 {verify_report.verified}/{verify_report.total} "
                f"条引文（通过率 {pass_pct:.0f}%）。[/{style}]"
            )
            if verify_report.unverified:
                console.print(
                    f"[yellow]剔除 {len(verify_report.unverified)} 条未核验引文；"
                    "详情见 _workspace/quote_verification.md。[/yellow]"
                )
        # 重写聚类缓存，使后续著作和 --refresh 重跑都看到核验后的状态。
        cluster_cache = (
            settings.workspace_dir / f"clustered_corpus.{settings.model_cache_id}.json"
        )
        cluster_cache.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")

    authoring_index = 5

    written: list[str] = []

    if write_skill_flag:
        stage(
            f"{authoring_index}/{total_stages} 撰写 SKILL.md",
            "生成 SKILL.md 与 references/*.md 等中文报告……",
        )
        authoring_index += 1
        skill_output = await author_skill(corpus=corpus, settings=settings, llm=llm)
        skill_path = write_skill(
            output=skill_output, sources=sources, settings=settings
        )
        written.append(f"SKILL.md + references/ 位于 [bold green]{skill_path}[/bold green]")

        if settings.critique:
            stage(
                f"{authoring_index}/{total_stages} 评审 SKILL.md",
                "对 SKILL.md 进行对抗式编辑评审……",
            )
            authoring_index += 1
            report = await critique_skill(
                output=skill_output, corpus=corpus, settings=settings, llm=llm
            )
            console.print(_critique_summary(report, label="SKILL.md"))

    if write_agents_flag:
        stage(
            f"{authoring_index}/{total_stages} 撰写 AGENTS.md",
            "生成 AGENTS.md……",
        )
        authoring_index += 1
        agents_output = await author_agents(corpus=corpus, settings=settings, llm=llm)
        agents_path = write_agents(
            output=agents_output, sources=sources, settings=settings
        )
        written.append(f"AGENTS.md 位于 [bold green]{agents_path}[/bold green]")

        if settings.critique:
            stage(
                f"{authoring_index}/{total_stages} 评审 AGENTS.md",
                "对 AGENTS.md 进行对抗式编辑评审……",
            )
            authoring_index += 1
            report = await critique_agents(
                output=agents_output, corpus=corpus, settings=settings, llm=llm
            )
            console.print(_critique_summary(report, label="AGENTS.md"))

    if settings.generate_avatar:
        console.rule("[bold cyan]生成头像")
        console.print(
            f"使用 [bold]{settings.avatar_model}[/bold] 生成头像……"
        )
        try:
            avatar_path = await generate_avatar(settings=settings)
        except Exception as exc:  # noqa: BLE001 - 头像属于尽力而为
            logger.warning("头像生成失败：%s", exc)
            console.print(
                f"[yellow]头像生成失败（{exc}），跳过继续。[/yellow]"
            )
        else:
            if avatar_path is not None:
                console.print(f"头像已保存到 [bold green]{avatar_path}[/bold green]")
                written.append(f"头像位于 [bold green]{avatar_path}[/bold green]")
            else:
                console.print(
                    "[yellow]图像模型未返回图片，已跳过。[/yellow]"
                )

    console.print(
        Panel(
            "\n".join(written) if written else "[yellow]未写入任何文件。[/yellow]",
            title="完成",
            border_style="green",
        )
    )
    return settings.skill_dir


def _critique_summary(report, *, label: str) -> str:  # type: ignore[no-untyped-def]
    """单行控制台摘要（评审环节）。"""
    highs = sum(1 for i in report.issues if i.severity == "high")
    mediums = sum(1 for i in report.issues if i.severity == "medium")
    colour = "green" if report.overall_score >= 8 else "yellow" if report.overall_score >= 6 else "red"
    return (
        f"[{colour}]{label} 评分：{report.overall_score}/10[/{colour}] "
        f"— 严重问题 {highs} 个、中等问题 {mediums} 个。"
        "完整报告见 _workspace/。"
    )
