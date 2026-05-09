"""Typer CLI 入口（中文版）。"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from .config import (
    DEFAULT_AVATAR_MODEL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    Format,
    Mode,
    MissingCredentialError,
    Provider,
    Settings,
)
from .identity import AmbiguousNameError
from .pipeline import run_pipeline

app = typer.Typer(
    add_completion=False,
    help=(
        "mimeo-zh：把一位专家的全部公开作品提炼成"
        "一份可直接使用的 Agent Skill / AGENTS.md（中文版）。"
    ),
    no_args_is_help=True,
)

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=verbose)],
    )
    # 压一下几个吵闹的三方库。
    for name in ("httpx", "httpcore", "openai", "urllib3", "parallel"):
        logging.getLogger(name).setLevel(logging.WARNING)


@app.command()
def build(
    expert: Annotated[
        str,
        typer.Argument(help="专家姓名，例如“段永平”或“Naval Ravikant”。"),
    ],
    mode: Annotated[
        Mode,
        typer.Option(
            "--mode",
            help=(
                "抓取深度。text：仅网页；captions：网页 + YouTube 字幕；"
                "full：再加音频转写（需可选依赖）。"
            ),
            case_sensitive=False,
        ),
    ] = "captions",
    fmt: Annotated[
        Format,
        typer.Option(
            "--format",
            "-f",
            help=(
                "输出形态。skill：SKILL.md + references/（默认）；"
                "agents：单文件 AGENTS.md；both：两者都生成。"
            ),
            case_sensitive=False,
        ),
    ] = "skill",
    max_sources: Annotated[
        int,
        typer.Option(
            "--max-sources",
            min=1,
            max=200,
            help="去重排序后保留的最大来源数。",
        ),
    ] = 25,
    deep_research: Annotated[
        bool,
        typer.Option(
            "--deep-research/--no-deep-research",
            help="额外调用 Parallel 深度研究 API，并把报告作为伪来源合入语料。",
        ),
    ] = False,
    provider: Annotated[
        Provider,
        typer.Option(
            "--provider",
            help=(
                "LLM 服务商。openrouter：走 OpenRouter（全球路由）；"
                "deepseek：直连 DeepSeek 官方 API（国内推荐）。"
            ),
            case_sensitive=False,
        ),
    ] = DEFAULT_PROVIDER,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help=(
                "模型 slug。provider=openrouter 时填 OpenRouter 模型"
                "（如 google/gemini-3.1-pro-preview）；"
                "provider=deepseek 时填 DeepSeek 原生模型"
                "（如 deepseek-chat、deepseek-reasoner）。"
            ),
        ),
    ] = DEFAULT_MODEL,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="生成目录的根路径。"),
    ] = Path("./output"),
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency",
            min=1,
            max=20,
            help="并发蒸馏的 LLM 调用数。",
        ),
    ] = 5,
    disambiguator: Annotated[
        str | None,
        typer.Option(
            "--disambiguator",
            "-d",
            help=(
                "短限定语，用来消歧同名者（例如“步步高创始人、投资人”）。"
                "设置后会跳过自动消歧阶段。"
            ),
        ),
    ] = None,
    assume_unambiguous: Annotated[
        bool,
        typer.Option(
            "--assume-unambiguous/--no-assume-unambiguous",
            help=(
                "彻底跳过身份消歧阶段——在非交互脚本里、你确信名字唯一时使用。"
            ),
        ),
    ] = False,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh/--no-refresh",
            help="忽略 _workspace/ 下的缓存，全部重跑。",
        ),
    ] = False,
    verify_quotes: Annotated[
        bool,
        typer.Option(
            "--verify-quotes/--no-verify-quotes",
            help=(
                "聚类后逐条核验 representative_quote 是否真的出现在"
                "已抓取的来源文本里；不匹配的会被剔除并写入审计报告。"
            ),
        ),
    ] = True,
    critique: Annotated[
        bool,
        typer.Option(
            "--critique/--no-critique",
            help=(
                "著作完成后再跑一轮“对抗式编辑”批判，"
                "输出写到 _workspace/critique_*.md。"
            ),
        ),
    ] = True,
    avatar: Annotated[
        bool,
        typer.Option(
            "--avatar/--no-avatar",
            help=(
                "生成一张油画风头像并保存为 avatar.<ext>。默认开启；"
                "如不需要可加 --no-avatar 省掉一次图像调用。"
            ),
        ),
    ] = True,
    avatar_model: Annotated[
        str,
        typer.Option(
            "--avatar-model",
            help="头像模型 slug（需图像能力，走 OpenRouter 图像通道）。",
        ),
    ] = DEFAULT_AVATAR_MODEL,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="开启详细日志。")
    ] = False,
) -> None:
    """为 ``EXPERT`` 基于其公开作品构建一份中文 Agent Skill。"""
    _setup_logging(verbose)

    settings = Settings(
        expert_name=expert,
        output_dir=output_dir.resolve(),
        mode=mode,
        format=fmt,
        max_sources=max_sources,
        deep_research=deep_research,
        model=model,
        provider=provider,
        concurrency=concurrency,
        refresh=refresh,
        expert_description=disambiguator,
        assume_unambiguous=assume_unambiguous,
        verify_quotes=verify_quotes,
        critique=critique,
        generate_avatar=avatar,
        avatar_model=avatar_model,
    )

    try:
        out_path = asyncio.run(run_pipeline(settings, console=console))
    except MissingCredentialError as exc:
        console.print(f"[bold red]缺少凭证：[/bold red] {exc}")
        raise typer.Exit(code=2)
    except AmbiguousNameError as exc:
        console.print(f"[bold yellow]名字存在歧义。[/bold yellow]\n{exc}")
        raise typer.Exit(code=2)
    except KeyboardInterrupt:
        console.print("[yellow]已取消。[/yellow]")
        raise typer.Exit(code=130)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]流水线执行失败：[/bold red] {exc}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)

    console.print(f"\n[bold green]完成。[/bold green] 输出目录：{out_path}")


def main() -> None:  # main.py 使用
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
