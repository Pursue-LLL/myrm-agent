/**
 * IME (Input Method Editor) 输入法兼容性守卫工具函数
 *
 * 解决 Windows、macOS 以及各类移动端 WebView 在中文/日文/韩文输入法候选词确认（Enter / Space）时，
 * 因浏览器事件时序竞争导致的 isComposing 提前翻转或 keyCode=229 / key='Process' 导致的误触提交问题。
 *
 * 额外覆盖 Safari / WebKit 的事件顺序倒置：Safari 先派发 `compositionend` 再派发确认 keydown，
 * 该 keydown 的 `isComposing` 已是 false，`key` 也不再是 'Process'（keyCode 随 WebKit 版本为 13 或 229，
 * 为 229 时由第 3 条拦下；为 13 时三个常规信号全部落空），导致「按 Enter 上屏」被误判为「按 Enter 提交」。
 * 故额外记录 compositionend 的时间戳，以两个事件的创建时间差判定时间窗：用事件自带的 `timeStamp` 而不是处理器
 * 运行时刻的时钟，主线程繁忙时处理器会迟到，按运行时刻计时会把确认键误判为已超出窗口。
 *
 * 输入法组合期间归输入法所有的两个键是 Enter（确认候选词）与 Escape（取消组合）。按 Enter 提交、按 Escape 关闭
 * 的处理器遍布全站（输入框 onKeyDown、各类弹窗的 window 级监听、Radix 的 document 捕获监听、运行中任务的中止快捷键），
 * 逐点加守卫必然在新增输入面上再漏；`installImeKeyGuard` 因此在 window 捕获阶段统一拦下这两个键，各处理器天然收不到。
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
  /** 浏览器创建事件的时刻；与 `compositionend` 事件同一时钟，两者之差即二者相隔多久。 */
  timeStamp?: number;
  nativeEvent?: {
    isComposing?: number | boolean;
    keyCode?: number;
  };
}

/**
 * Safari 在 compositionend 之后派发确认 / 取消 keydown 的时间窗（毫秒）。
 *
 * 取值参考 opencode 真机验证结论（Safari 26 + macOS 拼音/日文）：该窗口内到达的 Enter / Escape
 * 属于 IME 的候选上屏或取消组合，必须吞掉；超出窗口则视为用户的真实意图。
 */
export const IME_CONFIRM_KEY_WINDOW_MS = 100;

/** 组合期间归输入法所有、不得再被页面当作提交或关闭的按键。 */
const IME_OWNED_KEYS: ReadonlySet<string> = new Set(['Enter', 'Escape']);

let lastCompositionEndStamp: number | null = null;
let compositionObserverInstalled = false;

/**
 * 安装 document 级 compositionend 观察器（捕获阶段）。
 *
 * 选择 document 监听而非逐输入框绑定，是因为调用点分散在十余个组件（composer、澄清卡、
 * 审批卡、各类设置弹窗），任何逐点绑定都会让 IME 策略随组件增删而漂移。
 * 监听器只记录一个事件时间戳，不参与渲染，可安全地全局唯一。
 */
function installCompositionObserver(): void {
  if (compositionObserverInstalled || typeof document === 'undefined') {
    return;
  }
  compositionObserverInstalled = true;
  document.addEventListener(
    'compositionend',
    (event) => {
      lastCompositionEndStamp = event.timeStamp;
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
 * @returns true 表示正在输入法组合中，业务层应 return 阻止提交或快捷指令触发
 */
export function isImeComposing(event: KeyboardEventLike): boolean {
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

  // 4. Safari / WebKit 顺序倒置：compositionend 之后补发的确认 Enter / 取消 Escape 前三个信号全部落空；
  //    无时间戳的事件无法与 compositionend 比较先后，不在此判定范围。
  if (
    event.key !== undefined &&
    IME_OWNED_KEYS.has(event.key) &&
    event.timeStamp !== undefined &&
    lastCompositionEndStamp !== null &&
    Math.abs(event.timeStamp - lastCompositionEndStamp) < IME_CONFIRM_KEY_WINDOW_MS
  ) {
    return true;
  }

  return false;
}

/** 自己处理输入法组合的编辑器：它们的按键事件必须原样送达，守卫不介入。 */
const SELF_MANAGED_EDITOR_SELECTOR = '.monaco-editor, .cm-editor';

let keyGuardInstalled = false;

function swallowImeOwnedKey(event: KeyboardEvent): void {
  if (!IME_OWNED_KEYS.has(event.key) || !isImeComposing(event)) {
    return;
  }
  if (event.target instanceof Element && event.target.closest(SELF_MANAGED_EDITOR_SELECTOR)) {
    return;
  }
  // 只阻断传播、不 preventDefault：浏览器对候选词上屏 / 取消组合的默认行为不变，只是没有任何处理器把它当成「提交」或「关闭」。
  // 必须 stopImmediatePropagation：Radix 的 Escape 监听与本守卫同在捕获链上，stopPropagation 拦不住同节点上后注册的监听。
  event.stopImmediatePropagation();
}

/**
 * 安装 window 级捕获守卫：输入法确认候选词的 Enter、取消组合的 Escape 不会传给页面里的任何处理器（含 React 的
 * onKeyDown、各类 window / document 监听，以及运行中任务的 Escape 中止快捷键）。判定与逐点守卫共用 `isImeComposing`，
 * 二者不会出现分歧。
 *
 * 挂在 window 而不是 document：window 上的捕获监听先于 document 上的，只有挂在最前面才拦得住 window 捕获阶段的快捷键，
 * 所以安装方必须先于功能 hook 的 effect 注册。
 *
 * 只允许一个持有者（应用根的 `ImeKeyGuardInitializer`）；已安装时再次调用是空操作。返回卸载函数。
 */
export function installImeKeyGuard(): () => void {
  if (typeof window === 'undefined' || keyGuardInstalled) {
    return () => undefined;
  }
  keyGuardInstalled = true;
  window.addEventListener('keydown', swallowImeOwnedKey, true);
  return () => {
    window.removeEventListener('keydown', swallowImeOwnedKey, true);
    keyGuardInstalled = false;
  };
}
