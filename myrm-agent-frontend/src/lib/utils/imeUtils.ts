/**
 * IME (Input Method Editor) 输入法兼容性守卫工具函数
 *
 * 解决 Windows、macOS 以及各类移动端 WebView 在中文/日文/韩文输入法候选词确认（Enter / Space）时，
 * 因浏览器事件时序竞争导致的 isComposing 提前翻转或 keyCode=229 / key='Process' 导致的误触提交问题。
 *
 * 额外覆盖 Safari / WebKit 的事件顺序倒置：Safari 先派发 `compositionend` 再派发确认 keydown，
 * 该 keydown 的 `isComposing` 已是 false、`keyCode` 已是 13，三个常规信号全部落空，
 * 导致「按 Enter 上屏」被误判为「按 Enter 提交」。故额外维护 compositionend 时间戳窗口。
 */

/**
 * Structural subset shared by React synthetic events, native DOM events and test doubles.
 * Declared as a single interface so field access stays type-safe for every caller shape.
 */
export interface KeyboardEventLike {
  isComposing?: boolean;
  key?: string;
  keyCode?: number;
  which?: number;
  nativeEvent?: {
    isComposing?: number | boolean;
    keyCode?: number;
  };
}

/**
 * Safari 在 compositionend 之后派发确认 keydown 的时间窗（毫秒）。
 *
 * 取值参考 opencode 真机验证结论（Safari 26 + macOS 拼音/日文）：该窗口内到达的 Enter
 * 属于 IME 候选上屏，必须吞掉；超出窗口则视为用户的真实提交意图。
 */
export const IME_CONFIRM_ENTER_WINDOW_MS = 100;

let lastCompositionEndAt = 0;
let compositionObserverInstalled = false;

/**
 * 安装 document 级 compositionend 观察器（捕获阶段）。
 *
 * 选择 document 监听而非逐输入框绑定，是因为调用点分散在十余个组件（composer、澄清卡、
 * 审批卡、各类设置弹窗），任何逐点绑定都会让 IME 策略随组件增删而漂移。
 * 监听器只写入一个时间戳，不参与渲染，可安全地全局唯一。
 */
function installCompositionObserver(): void {
  if (compositionObserverInstalled || typeof document === 'undefined') {
    return;
  }
  compositionObserverInstalled = true;
  document.addEventListener(
    'compositionend',
    () => {
      lastCompositionEndAt = Date.now();
    },
    true,
  );
}

if (typeof document !== 'undefined') {
  installCompositionObserver();
}

/**
 * 严格判定当前键盘事件是否处于 IME 输入法组合键阶段（候选词挑选 / 拼音输入中）
 *
 * @param event React 键盘事件或原生 KeyboardEvent
 * @param now 当前时间戳（毫秒），默认 `Date.now()`；测试可注入以避免时间耦合
 * @returns true 表示正在输入法组合中，业务层应 return 阻止提交或快捷指令触发
 */
export function isImeComposing(event: KeyboardEventLike, now: number = Date.now()): boolean {
  if (!event) {
    return false;
  }

  installCompositionObserver();

  // 1. 标准 nativeEvent.isComposing 或 event.isComposing
  if (event.nativeEvent?.isComposing || event.isComposing) {
    return true;
  }

  // 2. W3C UI Events 标准：IME 处理中的按键 key 为 'Process'
  if (event.key === 'Process') {
    return true;
  }

  // 3. Windows IME 标准兼容：keyCode 229 为组合输入事件专属代码
  const keyCode = event.keyCode ?? event.which ?? event.nativeEvent?.keyCode;
  if (keyCode === 229) {
    return true;
  }

  // 4. Safari / WebKit 顺序倒置：compositionend 之后补发的确认 Enter 三个信号全部落空
  if (event.key === 'Enter' && lastCompositionEndAt > 0) {
    const elapsed = now - lastCompositionEndAt;
    if (elapsed >= 0 && elapsed < IME_CONFIRM_ENTER_WINDOW_MS) {
      return true;
    }
  }

  return false;
}
