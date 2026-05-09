"""DeepSeek 联通性最小验证脚本。

用途：快速验证 DeepSeek 是否可调用，避免完整跑流水线时才发现凭证问题。

两种路径（按顺序自动尝试）：

1. **原生直连**：读取 ``DEEPSEEK_API_KEY``，打 ``https://api.deepseek.com``。
   默认模型 ``deepseek-chat``。国内推荐。
2. **OpenRouter 回退**：若没有 ``DEEPSEEK_API_KEY`` 但有 ``OPENROUTER_API_KEY``，
   则用 OpenRouter 走 DeepSeek 模型（默认 ``deepseek/deepseek-chat``），
   证明 DeepSeek 模型能在本项目里跑通。

用法：
    uv run python scripts/test_deepseek.py
    uv run python scripts/test_deepseek.py --model deepseek-reasoner
    uv run python scripts/test_deepseek.py --via openrouter --model deepseek/deepseek-chat
    uv run python scripts/test_deepseek.py --via auto   # 默认
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mimeo.config import DEEPSEEK_BASE_URL  # noqa: E402
from mimeo.llm import LLMClient  # noqa: E402


def _pick_route(via: str) -> tuple[str, str]:
    """返回 (provider, 默认模型)。provider ∈ {'deepseek','openrouter'}。"""
    has_ds = bool(os.environ.get("DEEPSEEK_API_KEY"))
    has_or = bool(os.environ.get("OPENROUTER_API_KEY"))

    if via == "deepseek":
        if not has_ds:
            print("❌ 没有 DEEPSEEK_API_KEY，无法走 deepseek 原生直连。")
            raise SystemExit(2)
        return "deepseek", "deepseek-chat"
    if via == "openrouter":
        if not has_or:
            print("❌ 没有 OPENROUTER_API_KEY，无法走 openrouter 路径。")
            raise SystemExit(2)
        return "openrouter", "deepseek/deepseek-chat"

    # auto
    if has_ds:
        return "deepseek", "deepseek-chat"
    if has_or:
        print(
            "ℹ️  未检测到 DEEPSEEK_API_KEY，回退到 OpenRouter 的 DeepSeek 模型。\n"
            "    国内推荐直接申请 DEEPSEEK_API_KEY，见 https://platform.deepseek.com/"
        )
        return "openrouter", "deepseek/deepseek-chat"
    print("❌ .env 里既没有 DEEPSEEK_API_KEY 也没有 OPENROUTER_API_KEY。")
    raise SystemExit(2)


async def run(provider: str, model: str) -> int:
    if provider == "deepseek":
        print(f"🛰  路径       : DeepSeek 官方（{DEEPSEEK_BASE_URL}）")
        print(f"🔑  Key tail   : ...{os.environ['DEEPSEEK_API_KEY'][-4:]}")
    else:
        print("🛰  路径       : OpenRouter → DeepSeek 模型")
        print(f"🔑  Key tail   : ...{os.environ['OPENROUTER_API_KEY'][-4:]}")
    print(f"🧠  Model      : {model}")
    print("⏳  正在调用……")

    client = LLMClient(model=model, provider=provider)  # type: ignore[arg-type]
    try:
        reply = await client.complete(
            system="你是一个简短、直接的中文助手。",
            user=(
                "请用一句中文自我介绍，告诉我：1) 你现在使用的模型名；"
                "2) 今天是否可以正常工作。"
            ),
            temperature=0.2,
            max_tokens=200,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 调用失败：{type(exc).__name__}: {exc}")
        return 1

    print("--- DeepSeek 回复 ---")
    print(reply.strip() or "(空回复)")
    print("---------------------")
    if not reply.strip():
        print("⚠️  返回为空，凭证/模型可能有问题。")
        return 1
    print("✅ DeepSeek 正常")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepSeek 联通性测试")
    parser.add_argument(
        "--via",
        choices=("auto", "deepseek", "openrouter"),
        default="auto",
        help="测试路径：auto 自动选择；deepseek 原生直连；openrouter 走 OpenRouter。",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="要测试的模型名（不填则按路径使用默认值）。",
    )
    args = parser.parse_args()

    provider, default_model = _pick_route(args.via)
    model = args.model or default_model
    return asyncio.run(run(provider, model))


if __name__ == "__main__":
    sys.exit(main())
