"""运行时配置与环境变量加载。

通过 python-dotenv 在导入时读取 ``.env``，对外暴露带类型的
:class:`Settings`。为了让不需要 API 密钥的测试和工具链也能 import，
校验动作被推迟到真正用到 key 的时刻。

本中文版在原版基础上新增了 ``Provider`` 机制，允许在
``openrouter`` 和原生 ``deepseek`` (https://api.deepseek.com) 之间切换，
方便国内用户直连。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

Mode = Literal["text", "captions", "full"]
Format = Literal["skill", "agents", "both"]
Provider = Literal["openrouter", "deepseek"]

# ``MIMEO_PROVIDER`` 默认走 OpenRouter，国内用户设置为 ``deepseek`` 即可
# 直连 DeepSeek 官方 API（api.deepseek.com）。
_raw_provider = os.environ.get("MIMEO_PROVIDER", "openrouter").lower()
DEFAULT_PROVIDER: Provider = (
    "deepseek" if _raw_provider == "deepseek" else "openrouter"
)

# 每个 provider 的默认模型不同：
# - OpenRouter: 继续使用 Google Gemini（和原版保持一致）
# - DeepSeek 官方: 默认使用 deepseek-chat（稳定、便宜、中文体验好）
_DEFAULT_MODEL_OPENROUTER = os.environ.get(
    "MIMEO_MODEL", "google/gemini-3.1-pro-preview"
)
_DEFAULT_MODEL_DEEPSEEK = os.environ.get("MIMEO_MODEL", "deepseek-chat")
DEFAULT_MODEL = (
    _DEFAULT_MODEL_DEEPSEEK
    if DEFAULT_PROVIDER == "deepseek"
    else _DEFAULT_MODEL_OPENROUTER
)
DEFAULT_AVATAR_MODEL = os.environ.get("MIMEO_AVATAR_MODEL", "openai/gpt-5.4-image-2")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)


@dataclass(frozen=True)
class Settings:
    """单次流水线运行的已解析配置。"""

    expert_name: str
    output_dir: Path
    mode: Mode = "captions"
    format: Format = "skill"
    max_sources: int = 25
    deep_research: bool = False
    model: str = DEFAULT_MODEL
    provider: Provider = DEFAULT_PROVIDER
    concurrency: int = 5
    refresh: bool = False
    # 可选的"消歧描述"，用来指明当前 expert 到底指哪一位真实人物。
    # 可由用户通过 ``--disambiguator`` 传入，也可由 identity 阶段自动补齐。
    expert_description: str | None = None
    # 完全跳过 identity 消歧（非交互式场景下，确信名字唯一时使用）。
    assume_unambiguous: bool = False
    # 聚类完成后，校验每条 representative_quote 是否真的出现在某个
    # 已抓取的源文本中；不匹配的会被剔除，并写入审计报告。
    verify_quotes: bool = True
    # 著作完成后，再跑一次"对抗式编辑"批判，把结果写到
    # ``_workspace/critique_*.md``。
    critique: bool = True
    # 为 expert 生成一张画像式头像，保存为 ``avatar.<ext>``。
    # 走 OpenRouter 图像模型；失败会被日志吞掉，不影响主流程。
    generate_avatar: bool = True
    avatar_model: str = DEFAULT_AVATAR_MODEL

    @property
    def slug(self) -> str:
        from slugify import slugify

        return slugify(self.expert_name)

    @property
    def expert_context(self) -> str:
        """供 prompt 插值使用的括号限定语。

        当存在描述时渲染成 ``（段永平，步步高创始人、投资人）``；
        否则为空字符串。模板里直接跟在 ``{expert}`` 后面即可，不会出现
        悬空的空括号。
        """
        if self.expert_description:
            return f"（{self.expert_description}）"
        return ""

    @property
    def skill_dir(self) -> Path:
        return self.output_dir / self.slug

    @property
    def workspace_dir(self) -> Path:
        return self.skill_dir / "_workspace"

    @property
    def references_dir(self) -> Path:
        return self.skill_dir / "references"

    @property
    def model_cache_id(self) -> str:
        """模型 slug 的短哈希，用于隔离缓存。

        换模型 = 让之前所有 LLM 产物（抽取、聚类、著作）作废。
        缓存文件名里加上这段哈希，两次用不同模型的运行就不会相互踩到。
        把 provider 也揉进去，避免同名模型跨 provider 串缓存。
        """
        key = f"{self.provider}|{self.model}".encode("utf-8")
        return hashlib.sha1(key).hexdigest()[:8]


class MissingCredentialError(RuntimeError):
    """环境里缺少必需的 API key 时抛出。"""


def require_openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise MissingCredentialError(
            "未设置 OPENROUTER_API_KEY。请复制 .env.example 为 .env 并填入。"
        )
    return key


def require_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise MissingCredentialError(
            "未设置 DEEPSEEK_API_KEY。去 https://platform.deepseek.com/ "
            "申请后写入 .env。"
        )
    return key


def require_parallel_key() -> str:
    key = os.environ.get("PARALLEL_API_KEY")
    if not key:
        raise MissingCredentialError(
            "未设置 PARALLEL_API_KEY。请复制 .env.example 为 .env 并填入。"
        )
    return key


def openrouter_default_headers() -> dict[str, str]:
    """OpenRouter 推荐携带的可选归因 headers。"""
    headers: dict[str, str] = {}
    if url := os.environ.get("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = url
    if title := os.environ.get("OPENROUTER_APP_NAME"):
        headers["X-Title"] = title
    return headers


def ensure_dirs(settings: Settings) -> None:
    """幂等创建 skill 输出骨架。"""
    settings.skill_dir.mkdir(parents=True, exist_ok=True)
    settings.references_dir.mkdir(parents=True, exist_ok=True)
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("discovery", "raw", "distilled", "research"):
        (settings.workspace_dir / sub).mkdir(parents=True, exist_ok=True)


# Prompts 目录：开发态在 ``<repo>/prompts``，打成 wheel 之后被 force-include
# 到 ``<site-packages>/mimeo/prompts``。两处都兼容。
_HERE = Path(__file__).resolve().parent
_REPO_PROMPTS = _HERE.parents[1] / "prompts"
_PACKAGE_PROMPTS = _HERE / "prompts"
PROMPTS_DIR = _REPO_PROMPTS if _REPO_PROMPTS.exists() else _PACKAGE_PROMPTS
