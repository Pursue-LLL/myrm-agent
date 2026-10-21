/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 当前会话的 chatId 与无痕开关)
 * - @/services/file::UploadOptions (POS: 上传选项)
 *
 * [OUTPUT]
 * - incognitoUploadOptions(): 当前会话处于无痕时，返回把上传绑定到该会话的选项；否则返回空对象
 *
 * [POS]
 * 聊天附件上传的无痕绑定入口。无痕会话的上传随会话一起清理、不进入备份；由调用方在发起上传的那一刻
 * 显式传入，而不是让底层上传服务读取全局状态——资源池等与当前会话无关的上传不得被绑定，否则会随无痕会话被清掉。
 */

import type { UploadOptions } from '@/services/file';
import useChatStore from '@/store/useChatStore';

export function incognitoUploadOptions(): UploadOptions {
  const { incognitoMode, chatId } = useChatStore.getState();
  return incognitoMode && chatId ? { incognitoChatId: chatId } : {};
}
