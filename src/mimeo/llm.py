"""LLM 客户端：统一封装 OpenRouter 与 DeepSeek 官方 API。

底层仍然复用 ``openai`` 这套 SDK——OpenRouter 与 DeepSeek 都提供
OpenAI 兼容协议，只是 base_url / API key 不同。

结构化输出没有走 ``client.beta.chat.completions.parse``（部分模型
不支持严格模式），而是让模型以 ``response_format=json_object`` 返回，
我们再用 pydantic 做校验。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import (
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    OPENROUTER_BASE_URL,
    PROMPTS_DIR,
    Provider,
    openrouter_default_headers,
    require_deepseek_key,
    require_openrouter_key,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """``AsyncOpenAI`` 的薄封装，支持 OpenRouter / DeepSeek 两种 provider。"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        provider: Provider = DEFAULT_PROVIDER,
    ) -> None:
        self.model = model
        self.provider: Provider = provider

        if provider == "deepseek":
            self._client = AsyncOpenAI(
                api_key=require_deepseek_key(),
                base_url=DEEPSEEK_BASE_URL,
            )
        else:
            self._client = AsyncOpenAI(
                api_key=require_openrouter_key(),
                base_url=OPENROUTER_BASE_URL,
                default_headers=openrouter_default_headers() or None,
            )

    async def complete(
        self,
        *,
        system: str | None,
        user: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """纯文本补全。"""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        async for attempt in _network_retryer():
            with attempt:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return (resp.choices[0].message.content or "").strip()
        raise RuntimeError("unreachable")  # pragma: no cover

    async def structured(
        self,
        *,
        system: str | None,
        user: str,
        schema: type[T],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> T:
        """要求模型返回符合 ``schema`` 的 JSON。

        schema 直接拼进 user prompt，``response_format`` 强制 json_object。
        校验失败会自重试若干次，每次带上上一次的错误让模型自修正。
        """
        schema_hint = _format_schema_hint(schema)
        augmented_user = (
            f"{user}\n\n"
            f"只返回符合下面这份 Pydantic schema 的 JSON 对象：\n"
            f"{schema_hint}\n\n"
            f"不要包裹任何解释、代码块或多余文字——仅返回 JSON 本身。"
        )

        base_messages: list[dict[str, str]] = []
        if system:
            base_messages.append({"role": "system", "content": system})
        base_messages.append({"role": "user", "content": augmented_user})

        last_raw: str | None = None
        last_error: str | None = None

        for repair_attempt in range(_SCHEMA_REPAIR_ATTEMPTS):
            messages = list(base_messages)
            if last_raw is not None and last_error is not None:
                messages.append({"role": "assistant", "content": last_raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "你上一次返回的内容没有通过 schema 校验：\n"
                            f"{last_error}\n"
                            "请再返回一份严格匹配 schema 的 JSON，"
                            "不要带任何注释或代码块。"
                        ),
                    }
                )

            raw = ""
            async for attempt in _network_retryer():
                with attempt:
                    resp = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,  # type: ignore[arg-type]
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                    )
                    raw = (resp.choices[0].message.content or "").strip()

            try:
                data = json.loads(_strip_code_fence(raw))
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_raw = raw
                last_error = str(exc)[:1500]
                remaining = _SCHEMA_REPAIR_ATTEMPTS - repair_attempt - 1
                logger.warning(
                    "Schema 校验失败（还剩 %d 次自修复机会）: %s",
                    remaining,
                    exc,
                )
                if remaining == 0:
                    raise

        raise RuntimeError("unreachable")  # pragma: no cover


# 这些状态码重试通常会有效果；4xx 里的 401/400 重试也只是烧钱，直接抛出。
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# 解析成功但 schema 不匹配时，让模型自修复的次数。
_SCHEMA_REPAIR_ATTEMPTS = 3


def _is_network_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return False


def _network_retryer() -> AsyncRetrying:
    """只对短暂的网络 / 5xx 错误重试，不包 schema 失败。"""
    return AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception(_is_network_retryable),
        reraise=True,
    )


def _strip_code_fence(text: str) -> str:
    """部分模型即便被叮嘱过，也会用 ```json 包 JSON。"""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _format_schema_hint(schema: type[BaseModel]) -> str:
    """给模型看的紧凑 JSON schema。"""
    return json.dumps(schema.model_json_schema(), indent=2, ensure_ascii=False)


def load_prompt(name: str) -> str:
    """从 ``prompts/`` 目录加载模板。

    ``name`` 可带或不带 ``.md`` 后缀。
    """
    filename = name if name.endswith(".md") else f"{name}.md"
    path: Path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"未找到 prompt 模板：{path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **values: str) -> str:
    """把 ``template`` 里的 ``{name}`` 占位符用 ``values`` 替换。

    相比 ``str.format``，这里只动我们传进来的 key，模板里保留的
    形如 ``{2-3 段综述}`` 的说明性花括号不会被踩。
    """
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", val)
    return out
