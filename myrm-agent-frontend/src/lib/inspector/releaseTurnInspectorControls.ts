/**
 * [INPUT]
 * - @/store/useDesktopInspectorStore (POS: Desktop Inspector 面板状态)
 * - @/store/useBrowserInspectorStore (POS: Browser Inspector 面板状态)
 *
 * [OUTPUT]
 * - releaseTurnInspectorControls: turn 结束/手动停止时归还 desktop + browser Inspector 控制权
 *
 * [POS]
 * Inspector 控制权释放的纯函数 SSOT。所有 turn 终止路径（MESSAGE_END / stopMessage / ERROR / AGENT_CANCELLED / CONTEXT_OVERFLOW_RESET / GOAL_STATUS budget_limited / stream 中断 attach false）共用同一释放编排。
 *
 * 每个 store 的 releaseTurnEngagement 在未 engagedInTurn 时是 no-op，
 * 因此用户手动打开的面板不会被无关 turn 强制关闭。
 */

/**
 * 归还 desktop + browser inspector 的 turn 控制权。
 *
 * 任何 turn 结束路径都可安全调用：底层 release 在未 engaged 时是 no-op；
 * 动态 import 失败不会以 unhandled rejection 形式出现在 stop/turn 路径上。
 */
export async function releaseTurnInspectorControls(): Promise<void> {
  try {
    const [{ default: useDesktopInspectorStore }, { default: useBrowserInspectorStore }] = await Promise.all([
      import('@/store/useDesktopInspectorStore'),
      import('@/store/useBrowserInspectorStore'),
    ]);
    useDesktopInspectorStore.getState().releaseTurnEngagement();
    useBrowserInspectorStore.getState().releaseTurnEngagement();
  } catch {
    // Best-effort teardown; chunk load failure should not break the stop path.
  }
}
