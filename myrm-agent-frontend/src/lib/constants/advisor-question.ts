/**
 * [INPUT]
 * - @shared/config/chat_input_limits.json (POS: 服务端对聊天输入的长度上限，前后端共用，由服务端契约测试逐路由核对)
 *
 * [OUTPUT]
 * - ADVISOR_QUESTION_MAX_LENGTH: 向会话顾问提问的最大长度，等于服务端对问题的上限。
 *
 * [POS]
 * 顾问提问的长度上限：顾问面板的输入框限长，`askAdvisor` 在请求发出前按它截断，所以 `/ask <问题>` 这类由程序带入问题的路径也不会被服务端拒收。
 */
import chatInputLimits from '@shared/config/chat_input_limits.json';

/**
 * The server refuses a longer question (HTTP 422). The advisor panel's box stops typing and pasting here, and
 * `askAdvisor` cuts a question a command hands the panel, which no box could stop. The browser counts UTF-16 units and
 * the server counts characters, so a box stopped at this length never lets through more than the server accepts.
 */
export const ADVISOR_QUESTION_MAX_LENGTH = chatInputLimits.advisor_question;
