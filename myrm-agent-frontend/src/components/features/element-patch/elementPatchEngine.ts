import {
  AnnotationResolveSummary,
  AnnotationStatus,
  ElementAnnotationItem,
  StagedBatchPayload,
  SurgicalPatchScope,
} from './elementPatchTypes';

/**
 * 生成语义化且精准唯一的 CSS 选择器
 */
export function generateElementSelector(
  tagName: string,
  elementId?: string,
  classNames: string[] = [],
  nthChild?: number
): string {
  const cleanTag = tagName.toLowerCase();
  if (elementId && elementId.trim()) {
    return `#${elementId.trim()}`;
  }

  const validClasses = classNames
    .filter((c) => c && !c.includes(':') && !c.includes('['))
    .slice(0, 2);

  let selector = cleanTag;
  if (validClasses.length > 0) {
    selector += `.${validClasses.join('.')}`;
  }

  if (typeof nthChild === 'number' && nthChild > 0) {
    selector += `:nth-child(${nthChild})`;
  }

  return selector;
}

/**
 * 构造注入 Agent 上下文的手术刀式局部精准补丁约束指令
 */
export function buildSurgicalPatchPromptDirective(
  annotations: ElementAnnotationItem[],
  artifactId: string
): string {
  if (annotations.length === 0) {
    return '';
  }

  const patchItemsText = annotations
    .map((ann, idx) => {
      const snippet = ann.elementTextSnippet
        ? ` (原节点片段: "${ann.elementTextSnippet}")`
        : '';
      return `${idx + 1}. [目标选择器: ${ann.selector}]${snippet} ➜ 批注修改要求: ${ann.instruction}`;
    })
    .join('\n');

  return `<surgical_patch_scope artifact_id="${artifactId}">
【极重要：手术刀式局部精准打补丁协议 - 绝不全量重生成】
针对右侧工件预览打包下发的 ${annotations.length} 处元素批注，请严格遵守以下约束：
1. 绝对禁止全量重写整个工件或重构未涉及的上下文模块，避免任何回归随机漂移；
2. 仅针对以下明确指定的选择器与 DOM 节点执行手术刀式局部增量替换与样式微调；
3. 保持原有事件绑定、页面架构与其余组件 100% 不变。

待处理精准批注清单:
${patchItemsText}
</surgical_patch_scope>`;
}

/**
 * 构造批量下发数据载荷
 */
export function createStagedBatchPayload(
  artifactId: string,
  annotations: ElementAnnotationItem[]
): StagedBatchPayload {
  const batchId = `batch-${artifactId}-${Date.now().toString(36)}`;
  const promptDirective = buildSurgicalPatchPromptDirective(annotations, artifactId);

  return {
    batchId,
    artifactId,
    annotations: annotations.map((ann) => ({ ...ann, status: 'staged' })),
    promptDirective,
    timestamp: Date.now(),
  };
}

/**
 * 计算批注生命周期状态对齐汇总
 */
export function calculateBatchResolveSummary(
  annotations: ElementAnnotationItem[],
  batchId: string
): AnnotationResolveSummary {
  const totalCount = annotations.length;
  const resolvedCount = annotations.filter((a) => a.status === 'resolved').length;
  const failedCount = annotations.filter((a) => a.status === 'failed').length;

  let status: AnnotationResolveSummary['status'] = 'in_progress';
  if (totalCount > 0 && resolvedCount === totalCount) {
    status = 'all_resolved';
  } else if (resolvedCount > 0 && resolvedCount + failedCount === totalCount) {
    status = 'partially_resolved';
  }

  return {
    batchId,
    totalCount,
    resolvedCount,
    failedCount,
    status,
  };
}

/**
 * 格式化批注状态视觉标签与色彩
 */
export function formatAnnotationStatus(status: AnnotationStatus): {
  label: string;
  bg: string;
  text: string;
  border: string;
  dotColor: string;
} {
  if (status === 'resolved') {
    return {
      label: '已自愈修复',
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-300',
      border: 'border-emerald-500/30',
      dotColor: 'bg-emerald-400',
    };
  }

  if (status === 'resolving') {
    return {
      label: '手术刀补丁中',
      bg: 'bg-indigo-500/10',
      text: 'text-indigo-300',
      border: 'border-indigo-500/30',
      dotColor: 'bg-indigo-400',
    };
  }

  if (status === 'staged') {
    return {
      label: '已打包暂存',
      bg: 'bg-cyan-500/10',
      text: 'text-cyan-300',
      border: 'border-cyan-500/30',
      dotColor: 'bg-cyan-400',
    };
  }

  if (status === 'failed') {
    return {
      label: '补丁应用失败',
      bg: 'bg-rose-500/10',
      text: 'text-rose-300',
      border: 'border-rose-500/30',
      dotColor: 'bg-rose-400',
    };
  }

  return {
    label: '待打包暂存',
    bg: 'bg-amber-500/10',
    text: 'text-amber-300',
    border: 'border-amber-500/30',
    dotColor: 'bg-amber-400',
  };
}
