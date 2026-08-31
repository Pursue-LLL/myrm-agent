/**
 * [INPUT]
 * - @/store/useDesktopInspectorStore (POS: Desktop Inspector 面板状态管理，含 per-chat turn engagement 释放)
 * - @/store/useBrowserInspectorStore (POS: Browser Inspector 面板状态管理，含 per-chat turn engagement 释放)
 *
 * [OUTPUT]
 * - releaseTurnInspectorControls: turn 结束/手动停止时归还 desktop + browser Inspector 控制权
 *
 * [POS]
 * Inspector 控制权释放的纯函数 SSOT。所有 turn 终止路径（MESSAGE_END / stopMessage / ERROR / AGENT_CANCELLED / CONTEXT_OVERFLOW_RESET / GOAL_STATUS budget_limited / stream 中断 attach false）共用同一释放编排。
 * 释放按 viewData 归属 chatId 回收（releaseTurnEngagement 同时匹配本 chat 的 engage 与其 viewData 归属），
 * 即使 engage 槽位被其它 pane 覆盖，本 turn 结束仍能回收自己的视图；
 * 手动打开的面板（无 engagedChatId）与 viewData 归其它 chat 的进行中 turn 不会被强制关闭。
 */

/**
 * 归还 desktop + browser inspector 的 turn 控制权。
 *
 * 只释放归属 chatId 的 turn engagement：release 在 chatId 不匹配（含未 engaged）
 * 时是 no-op，因此其它 pane 正在进行的桌面/浏览器 turn 不会被误关；
 * 被其它 pane 覆盖 engage 的 turn 结束时会回收其 viewData，避免「幽灵控制」残留；
 * 动态 import 失败不会以 unhandled rejection 形式出现在 stop/turn 路径上。
 */
export async function releaseTurnInspectorControls(chatId: string): Promise<void> {
  try {
    const [
      { default: useDesktopInspectorStore },
      { default: useBrowserInspectorStore },
      { default: useDeviceInspectorStore },
    ] = await Promise.all([
      import('@/store/useDesktopInspectorStore'),
      import('@/store/useBrowserInspectorStore'),
      import('@/store/useDeviceInspectorStore'),
    ]);
    useDesktopInspectorStore.getState().releaseTurnEngagement(chatId);
    useBrowserInspectorStore.getState().releaseTurnEngagement(chatId);
    useDeviceInspectorStore.getState().releaseTurnEngagement(chatId);
  } catch {
    // Best-effort teardown; chunk load failure should not break the stop path.
  }
}
