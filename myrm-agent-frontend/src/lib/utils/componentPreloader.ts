/**
 * Component Preloader Utility
 *
 * 用于在用户hover时预加载重型组件，提升首次渲染体验
 */

let monacoPreloadPromise: Promise<any> | null = null;
let sandpackPreloadPromise: Promise<any> | null = null;

/**
 * 预加载Monaco编辑器
 * 可以在用户hover到相关链接时调用，提前加载Monaco
 */
export function preloadMonacoEditor() {
  if (!monacoPreloadPromise) {
    monacoPreloadPromise = import('@monaco-editor/react')
      .then(() => {
        console.log('[Preload] Monaco editor loaded');
      })
      .catch((error) => {
        console.error('[Preload] Failed to load Monaco editor:', error);
        monacoPreloadPromise = null;
      });
  }
  return monacoPreloadPromise;
}

/**
 * 预加载Sandpack组件
 * 可以在用户hover到相关链接时调用
 */
export function preloadSandpack() {
  if (!sandpackPreloadPromise) {
    sandpackPreloadPromise = import('@codesandbox/sandpack-react')
      .then(() => {
        console.log('[Preload] Sandpack loaded');
      })
      .catch((error) => {
        console.error('[Preload] Failed to load Sandpack:', error);
        sandpackPreloadPromise = null;
      });
  }
  return sandpackPreloadPromise;
}

/**
 * 预加载所有重型编辑器组件
 */
export function preloadAllEditors() {
  preloadMonacoEditor();
  preloadSandpack();
}
