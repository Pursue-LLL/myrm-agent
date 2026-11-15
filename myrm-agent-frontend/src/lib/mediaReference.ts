/**
 * [INPUT]
 * - 无
 *
 * [OUTPUT]
 * - MEDIA_REFERENCE_PREFIX: `media://`
 * - toMediaReference: 媒体库记录 id → `media://<id>`
 * - parseMediaReference: `media://<id>` → 记录 id（其余字符串返回 null）
 *
 * [POS]
 * 媒体库条目的稳定地址（镜像服务端 `app/core/media/reference.py`）。生成结果、任务载荷与聊天消息只保存这个地址，
 * 不保存存储 URL；渲染时由 `getStorageUrl` 解析成后端文件端点，附件作为对话句柄时也用同一个地址。
 */

export const MEDIA_REFERENCE_PREFIX = 'media://';

export function toMediaReference(mediaId: string): string {
  return `${MEDIA_REFERENCE_PREFIX}${mediaId}`;
}

export function parseMediaReference(value: string): string | null {
  if (!value.startsWith(MEDIA_REFERENCE_PREFIX)) {
    return null;
  }
  return value.slice(MEDIA_REFERENCE_PREFIX.length) || null;
}
