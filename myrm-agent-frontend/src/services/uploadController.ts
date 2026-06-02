/**
 * [OUTPUT]
 * - getUploadSignal(): AbortSignal
 * - abortCurrentUpload(): void
 * - resetUploadController(): void
 *
 * [POS]
 * 模块级 AbortController 管理，用于在会话切换时取消进行中的文件上传。
 * 不放入 Zustand store（AbortController 不可序列化且不需要触发 re-render）。
 */

let controller: AbortController | null = null;

export function getUploadSignal(): AbortSignal {
  if (!controller) controller = new AbortController();
  return controller.signal;
}

export function abortCurrentUpload(): void {
  controller?.abort();
  controller = null;
}

export function resetUploadController(): void {
  controller = new AbortController();
}
