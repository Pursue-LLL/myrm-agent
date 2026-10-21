"""Test real LLM inference using configured credentials from .env.test."""

import asyncio
import os
from pathlib import Path

# Load .env.test
env_test = Path(__file__).resolve().parents[2] / ".env.test"
if env_test.is_file():
    with open(env_test, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from langchain_core.messages import HumanMessage
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import ChatLiteLLM


async def main() -> None:
    api_key = os.environ.get("BASIC_API_KEY")
    base_url = os.environ.get("BASIC_BASE_URL")
    model = os.environ.get("BASIC_MODEL")

    print(f"MODEL_PROVIDER: {model}")
    print(f"BASE_URL: {base_url}")
    print(f"API_KEY_MASKED: {api_key[:6]}...{api_key[-4:] if api_key else ''}")

    llm = ChatLiteLLM(
        model=model,
        api_key=api_key,
        api_base=base_url,
        temperature=0.1,
        max_tokens=1024,
    )

    prompt = "请计算 12345 + 54321，并用一句话总结企业密码管理器（如 1Password）无明文凭据网关对防凭据泄露的核心价值。"
    print(f"\n[PROMPT_INPUT]: {prompt}\n")

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    print(f"[RAW_RESPONSE_REPR]:\n{repr(response)}")
    print(f"[MODEL_CONTENT]:\n{response.content}")
    print(f"[ADDITIONAL_KWARGS]:\n{response.additional_kwargs}")
    print("\n[INFERENCE_STATUS]: SUCCESS")

if __name__ == "__main__":
    asyncio.run(main())
