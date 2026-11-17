/**
 * [INPUT]
 * - @shared/config/chat_input_limits.json (POS: 服务端对聊天输入的长度上限，前后端共用，由服务端契约测试逐路由核对)
 *
 * [OUTPUT]
 * - HISTORY_SEARCH_MAX_LENGTH: 聊天历史查询的最大长度，等于服务端对查询的上限。
 *
 * [POS]
 * 聊天历史查询的长度上限：侧栏会话搜索、Cmd+K 消息搜索与共享上下文历史搜索的输入框限长，`@chat:` 选择器截断发出的查询。
 */
import chatInputLimits from '@shared/config/chat_input_limits.json';

/**
 * The server refuses a longer query (HTTP 422): the sidebar keyword, the Cmd+K dialog, the `@chat:` picker and the
 * shared-context history search all share this cap. The search boxes stop typing and pasting here, and the `@chat:`
 * picker, whose query is whatever follows the mention in the composer, cuts the query it sends. The browser counts
 * UTF-16 units and the server counts characters, so a box never lets through more than the server accepts.
 */
export const HISTORY_SEARCH_MAX_LENGTH = chatInputLimits.history_search_query;
