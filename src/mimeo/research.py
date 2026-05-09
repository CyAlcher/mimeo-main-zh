"""Optional Parallel Task API deep-research pseudo-source.

Kicks off a ``pro-fast`` (by default) task run asking Parallel to produce a
comprehensive synthesis of the expert's thought process. The returned report
is injected into the pipeline as an extra :class:`Source` with a synthetic
``src_research_XXX`` id, so the rest of the pipeline can treat it uniformly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import Settings
from .parallel_client import ParallelClient
from .schemas import FetchedContent, Source

logger = logging.getLogger(__name__)


def _task_input(expert: str) -> str:
    return (
        f"请就 {expert} 的思考方式、原则、框架与心智模型，结合其全部"
        "公开的文字与音视频作品，产出一份综合、可溯源的中文综述。"
        "凡有原话处请原样引用，并为每个论点注明原始出处（文章标题、"
        "书名、演讲或访谈）。需覆盖：(1) 他反复回到的大主题；"
        "(2) 核心原则及其理由；(3) 他使用的命名框架或决策流程；"
        "(4) 标志性金句；(5) 他常年反对的立场。请用清晰的中文小节组织。"
        "人名、公司、英文书名保留原文即可。"
    )


async def deep_research(
    *,
    settings: Settings,
    parallel: ParallelClient,
) -> tuple[Source, FetchedContent] | None:
    """Run deep research; return (pseudo_source, fetched_content) or None on failure."""
    cache_dir = settings.workspace_dir / "research"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "report.json"

    if cache_path.exists() and not settings.refresh:
        logger.info("Using cached deep-research report from %s", cache_path)
        return _load_from_cache(cache_path)

    try:
        result = await parallel.deep_research(
            input_text=_task_input(settings.expert_name),
            processor="pro-fast",
            metadata={"expert": settings.expert_name},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep research failed: %s", exc)
        return None

    output = result.output
    text = _stringify_output(output)
    if not text:
        logger.warning("Deep research returned empty output")
        return None

    src = Source(
        id="src_research",
        url="parallel://deep-research",
        title=f"Parallel 深度研究报告：{settings.expert_name}",
        kind="other",
        medium="research-report",
        bucket="deep-research",
        excerpts=[],
    )
    content = FetchedContent(
        source_id=src.id,
        url=src.url,
        title=src.title,
        text=text,
        char_count=len(text),
        fetch_method="parallel-deep-research",
    )

    cache_path.write_text(
        json.dumps(
            {"source": src.model_dump(), "content": content.model_dump()},
            indent=2,
        ),
        encoding="utf-8",
    )
    return src, content


def _load_from_cache(path: Path) -> tuple[Source, FetchedContent]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return (
        Source.model_validate(data["source"]),
        FetchedContent.model_validate(data["content"]),
    )


def _stringify_output(output) -> str:
    """Task API output is a union type (text, basis, structured). Coerce to string."""
    if output is None:
        return ""
    # Pydantic model - prefer known fields.
    for attr in ("content", "text", "output"):
        val = getattr(output, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    # Dict-like
    if isinstance(output, dict):
        for key in ("content", "text", "output"):
            val = output.get(key)
            if isinstance(val, str) and val.strip():
                return val
    # Fallback: dump the entire model as JSON so we at least have content.
    try:
        return output.model_dump_json(indent=2)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return str(output)
