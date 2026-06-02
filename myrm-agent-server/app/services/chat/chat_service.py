"""Chat business facade.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- chat_crud::_ChatCrudMixin (POS: Chat CRUD、session、channel 操作)
- chat_message::_ChatMessageMixin (POS: 消息持久化操作)
- chat_history::_ChatHistoryMixin (POS: 历史加载与搜索)
- chat_turn::_ChatTurnMixin (POS: 重试/撤销/兄弟/标题生成)
- chat_compaction::_ChatCompactionMixin (POS: compaction drain 操作)

[OUTPUT]
ChatService: 聊天业务统一入口，组合各 mixin 的所有方法。

[POS]
聊天业务门面层。为 API、Agent 入口和频道执行器提供统一聊天业务接口。
通过 Mixin 组合模式，各域方法定义在独立文件中，ChatService 作为统一入口。
"""

from __future__ import annotations

from .chat_compaction import _ChatCompactionMixin
from .chat_crud import _ChatCrudMixin
from .chat_history import _ChatHistoryMixin
from .chat_message import _ChatMessageMixin
from .chat_turn import _ChatTurnMixin


class ChatService(
    _ChatCrudMixin,
    _ChatMessageMixin,
    _ChatHistoryMixin,
    _ChatTurnMixin,
    _ChatCompactionMixin,
):
    """聊天服务聚合类，对外提供统一接口。

    各域方法定义在独立文件中：
    - chat_crud.py: CRUD、session、channel 操作
    - chat_message.py: 消息持久化
    - chat_history.py: 历史加载与搜索
    - chat_turn.py: 重试/撤销/兄弟/标题生成
    - chat_compaction.py: compaction drain

    所有方法均为 @staticmethod，消费者无需改动 import 路径。
    """
