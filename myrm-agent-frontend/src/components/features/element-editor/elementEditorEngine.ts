import {
  ArtifactVersionSnapshot,
  BoundingRect,
  InPlacePromptPayload,
  InspectorElementInfo,
  SnapshotDiffStats,
} from './elementEditorTypes';

/**
 * 从实际 DOM 元素提取点选拾取元数据
 */
export function extractElementInfo(
  element: HTMLElement,
  containerRect?: BoundingRect
): InspectorElementInfo {
  const rect = element.getBoundingClientRect();
  const cTop = containerRect ? containerRect.top : 0;
  const cLeft = containerRect ? containerRect.left : 0;

  const tag = element.tagName.toLowerCase();
  const idAttr = element.id ? `#${element.id}` : '';
  const firstClass = element.classList.length > 0 ? `.${element.classList[0]}` : '';
  const selector = `${tag}${idAttr}${firstClass}`;

  const adjustedRect: BoundingRect = {
    top: rect.top - cTop,
    left: rect.left - cLeft,
    width: rect.width,
    height: rect.height,
  };

  return {
    id: element.id || `el-${Math.random().toString(36).substring(2, 8)}`,
    tag,
    selector,
    xpath: `//${tag}[@class='${element.className}']`,
    rect: adjustedRect,
    innerText: element.innerText ? element.innerText.substring(0, 60) : '',
    classes: element.className || '',
    sourceFilePath: 'src/components/preview/HeroSection.tsx',
    sourceLine: 42,
  };
}

/**
 * 组装局部定向微补丁 Prompt
 */
export function buildTargetedMicroPatchPrompt(
  payload: InPlacePromptPayload
): string {
  const { element, instruction, category } = payload;
  return `[外科手术式微补丁请求]
目标标签: <${element.tag}>
定位选择器: ${element.selector}
源文件映射: ${element.sourceFilePath || 'unknown'}:${element.sourceLine || 1}
原文本/类名: "${element.innerText}" / "${element.classes}"
修改分类: ${category}
修改指令: ${instruction}
约束规则: 仅修改该具体 DOM/AST 节点，严禁变动任何未选中的周围标签与父级结构！`;
}

/**
 * 计算快照差异并生成新版本快照
 */
export function createSnapshot(
  previousHtml: string,
  newHtml: string,
  description: string,
  versionNumber: number,
  targetTag = 'element'
): ArtifactVersionSnapshot {
  const prevLines = previousHtml.split('\n').length;
  const newLines = newHtml.split('\n').length;
  const lineDelta = newLines - prevLines;

  const diffStats: SnapshotDiffStats = {
    addedLines: Math.max(1, lineDelta > 0 ? lineDelta : 1),
    removedLines: Math.max(0, lineDelta < 0 ? Math.abs(lineDelta) : 0),
    changedTarget: targetTag,
  };

  return {
    id: `snap-${versionNumber}-${Date.now().toString(36)}`,
    versionNumber,
    timestamp: new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
    description,
    contentHtml: newHtml,
    diffStats,
  };
}

/**
 * 判断是否按下 Undo 悔棋快捷键 (Cmd+Z / Ctrl+Z)
 */
export function isUndoShortcut(e: KeyboardEvent): boolean {
  const hasModifier = Boolean(e.metaKey || e.ctrlKey);
  if (!hasModifier || e.shiftKey) {
    return false;
  }
  return e.key === 'z' || e.key === 'Z' || e.code === 'KeyZ';
}

/**
 * 判断是否按下 Redo 重做快捷键 (Cmd+Shift+Z / Ctrl+Y / Ctrl+Shift+Z)
 */
export function isRedoShortcut(e: KeyboardEvent): boolean {
  const hasModifier = Boolean(e.metaKey || e.ctrlKey);
  if (!hasModifier) {
    return false;
  }
  if (e.shiftKey && (e.key === 'z' || e.key === 'Z' || e.code === 'KeyZ')) {
    return true;
  }
  if (!e.shiftKey && (e.key === 'y' || e.key === 'Y' || e.code === 'KeyY')) {
    return true;
  }
  return false;
}

/**
 * 默认演示 HTML 初始工件
 */
export function getDefaultHtmlContent(): string {
  return `<div class="p-6 bg-slate-900 rounded-2xl border border-slate-800 text-slate-100 font-sans">
  <div class="flex items-center justify-between pb-3 border-b border-slate-800">
    <h3 id="hero-title" class="text-base font-bold text-white">AI 智能设计与代码工件画布</h3>
    <span id="version-badge" class="px-2 py-0.5 text-xs bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">v1.0.0</span>
  </div>
  <p id="hero-desc" class="mt-3 text-xs text-slate-400 leading-relaxed">
    支持鼠标悬停点选任意 DOM 元素，就地呼出微调提示词输入框。无论如何修改，均支持一键悔棋回滚上一版本。
  </p>
  <div class="mt-4 flex items-center gap-3">
    <button id="primary-action-btn" class="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-500 transition-colors">
      立即采纳方案
    </button>
    <button id="secondary-action-btn" class="px-3 py-2 bg-slate-800 text-slate-300 rounded-xl text-xs hover:bg-slate-700 transition-colors">
      查看原型源码
    </button>
  </div>
</div>`;
}

/**
 * 默认示范版本历史
 */
export function getDefaultSnapshots(): ArtifactVersionSnapshot[] {
  const baseHtml = getDefaultHtmlContent();
  return [
    {
      id: 'snap-1',
      versionNumber: 1,
      timestamp: '14:20:05',
      description: '初始工件生成',
      contentHtml: baseHtml,
      diffStats: {
        addedLines: 18,
        removedLines: 0,
        changedTarget: 'Initial Canvas',
      },
    },
  ];
}
