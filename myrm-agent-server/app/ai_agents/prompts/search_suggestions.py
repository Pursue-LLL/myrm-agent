"""搜索建议提示模板

提供根据聊天历史生成相关搜索建议的提示模板
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from typing_extensions import Annotated, TypedDict


class SuggestionsResponse(TypedDict):
    """搜索建议响应"""

    suggestions: Annotated[list[str], [], "搜索建议列表"]


def get_search_suggestions_prompt(chat_history: list[BaseMessage]) -> list[BaseMessage]:
    """获取用于生成搜索建议的提示

    Args:
        chat_history: 聊天历史记录

    Returns:
        系统和用户的消息列表
    """

    # 格式化聊天历史
    formatted_history = "\n".join([f"{'User' if isinstance(msg, HumanMessage) else 'AI'}: {msg.content}" for msg in chat_history])

    system_message = f"""
    <role_definition>
    你是一个服务于AI搜索引擎的智能建议生成器。你的唯一任务是根据用户与AI的对话历史，生成一系列高质量的、可用于进一步提问的搜索建议。你被设计为自动化流程中的一个环节，因此必须严格遵守输出格式。
    </role_definition>

    <input_data>
    {formatted_history}
    </input_data>

    <instructions>
    1.  分析下方 `<input_data>` 标签中提供的对话历史。
    2.  基于对话的核心主题和潜在的用户兴趣点，生成 4 到 5 个相关的后续查询建议。
    3.  生成的建议应具有启发性，能够引导用户：
        - 探索核心主题下的相关子概念。
        - 追问事件或观点的深层原因与影响。
        - 寻求具体的实践方法或案例。
        - 对比不同观点或方案的优劣。
    4.  建议的语言应简洁、清晰，模仿一个好奇的人会提出的问题。
    </instructions>

    <output_format>
    你的回复必须且只能是一个JSON字符串，并用Markdown代码块包裹。禁止在JSON代码块前后添加任何解释、问候或其他文字。

    JSON结构必须如下：
    - 根对象包含一个名为 `suggestions` 的键。
    - `suggestions` 的值是一个包含4-5个字符串建议的数组。

    示例格式：
    ```json
    {
        "suggestions": [
        "第一个建议",
        "第二个建议",
        "第三个建议",
        "第四个建议"
      ]
    }
    """

    messages: list[BaseMessage] = [
        SystemMessage(content=system_message),
    ]

    return messages
