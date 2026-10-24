/**
 * Component Preloader Utility
 *
 * 用于在用户 hover 相关入口时预加载重型编辑器组件，提升首次交互体验。
 */

let monacoPreloadPromise: Promise<void> | null = null;

/**
 * 预加载 Monaco 编辑器
 * 在用户 hover 到工作台或代码入口时提前拉取资源。
 */
export function preloadMonacoEditor(): Promise<void> | null {
  if (!monacoPreloadPromise) {
    monacoPreloadPromise = Promise.all([import('@monaco-editor/react'), import('monaco-editor')])
      .then(([reactMod, monacoMod]) => {
        reactMod.loader.config({ monaco: monacoMod });
      })
      .catch((error: unknown) => {
        console.error('[Preload] Failed to load Monaco editor:', error);
        monacoPreloadPromise = null;
      });
  }
  return monacoPreloadPromise;
}
