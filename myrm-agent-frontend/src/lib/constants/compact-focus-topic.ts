/**
 * [INPUT]
 * - @shared/config/chat_input_limits.json (POS: 服务端对聊天输入的长度上限，前后端共用，由服务端契约测试逐路由核对)
 *
 * [OUTPUT]
 * - COMPACT_FOCUS_TOPIC_MAX_LENGTH: 压缩上下文时「聚焦主题」的最大长度，等于服务端对它的上限。
 *
 * [POS]
 * 聚焦主题的长度上限：压缩面板的输入框限长，`compactChat` 在请求发出前按它截断，所以输入 `/compact <主题>` 的路径也不会被服务端拒收。
 */
import chatInputLimits from '@shared/config/chat_input_limits.json';

/**
 * The server refuses a longer focus topic (HTTP 422), so a topic is cut to this many characters before it is sent. The
 * browser counts UTF-16 units and the server counts characters, so a box stopped at this length never lets through
 * more than the server accepts.
 */
export const COMPACT_FOCUS_TOPIC_MAX_LENGTH = chatInputLimits.compact_focus_topic;
