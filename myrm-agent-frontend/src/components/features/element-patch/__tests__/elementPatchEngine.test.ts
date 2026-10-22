import { describe, it, expect } from 'vitest';
import {
  generateElementSelector,
  buildSurgicalPatchPromptDirective,
  createStagedBatchPayload,
  calculateBatchResolveSummary,
  formatAnnotationStatus,
} from '../elementPatchEngine';
import { ElementAnnotationItem } from '../elementPatchTypes';

describe('elementPatchEngine', () => {
  it('generates precise css selectors with id, class, or tag', () => {
    expect(generateElementSelector('button', 'submit-order')).toBe('#submit-order');
    expect(
      generateElementSelector('div', undefined, ['hero-banner', 'bg-dark', 'extra'])
    ).toBe('div.hero-banner.bg-dark');
    expect(generateElementSelector('li', undefined, [], 3)).toBe('li:nth-child(3)');
    expect(generateElementSelector('span')).toBe('span');
  });

  it('builds surgical patch prompt directive with scope and prohibitions', () => {
    const annotations: ElementAnnotationItem[] = [
      {
        id: 'ann-1',
        artifactId: 'art-preview-123',
        selector: '#cta-btn',
        elementTagName: 'button',
        elementTextSnippet: '立即购买',
        boundingBox: { x: 10, y: 20, width: 120, height: 40 },
        instruction: '背景色改为浅灰，增加 8px 圆角',
        status: 'pending',
        createdAt: Date.now(),
      },
      {
        id: 'ann-2',
        artifactId: 'art-preview-123',
        selector: 'h2.sub-title',
        elementTagName: 'h2',
        boundingBox: { x: 10, y: 80, width: 300, height: 30 },
        instruction: '文案精简为 6 个字，防止移动端截断',
        status: 'pending',
        createdAt: Date.now(),
      },
    ];

    const directive = buildSurgicalPatchPromptDirective(annotations, 'art-preview-123');
    expect(directive).toContain('<surgical_patch_scope artifact_id="art-preview-123">');
    expect(directive).toContain('绝对禁止全量重写整个工件');
    expect(directive).toContain('1. [目标选择器: #cta-btn] (原节点片段: "立即购买") ➜ 批注修改要求: 背景色改为浅灰，增加 8px 圆角');
    expect(directive).toContain('2. [目标选择器: h2.sub-title] ➜ 批注修改要求: 文案精简为 6 个字，防止移动端截断');
    expect(directive).toContain('</surgical_patch_scope>');
  });

  it('returns empty string when building directive with empty annotations', () => {
    expect(buildSurgicalPatchPromptDirective([], 'art-empty')).toBe('');
  });

  it('creates staged batch payload with unique batchId and annotations marked staged', () => {
    const annotations: ElementAnnotationItem[] = [
      {
        id: 'ann-1',
        artifactId: 'art-99',
        selector: '.card',
        elementTagName: 'div',
        boundingBox: { x: 0, y: 0, width: 100, height: 100 },
        instruction: '边框改细',
        status: 'pending',
        createdAt: Date.now(),
      },
    ];

    const payload = createStagedBatchPayload('art-99', annotations);
    expect(payload.batchId).toContain('batch-art-99');
    expect(payload.annotations[0].status).toBe('staged');
    expect(payload.promptDirective).toContain('边框改细');
  });

  it('calculates batch resolve summaries accurately', () => {
    const list: ElementAnnotationItem[] = [
      {
        id: 'a1',
        artifactId: 'art-1',
        selector: '#btn1',
        elementTagName: 'button',
        boundingBox: { x: 0, y: 0, width: 50, height: 20 },
        instruction: 'fix 1',
        status: 'resolved',
        createdAt: Date.now(),
      },
      {
        id: 'a2',
        artifactId: 'art-1',
        selector: '#btn2',
        elementTagName: 'button',
        boundingBox: { x: 0, y: 30, width: 50, height: 20 },
        instruction: 'fix 2',
        status: 'staged',
        createdAt: Date.now(),
      },
    ];

    const summaryInProgress = calculateBatchResolveSummary(list, 'b1');
    expect(summaryInProgress.status).toBe('in_progress');
    expect(summaryInProgress.resolvedCount).toBe(1);
    expect(summaryInProgress.totalCount).toBe(2);

    const allResolvedList = list.map((a) => ({ ...a, status: 'resolved' as const }));
    const summaryAll = calculateBatchResolveSummary(allResolvedList, 'b1');
    expect(summaryAll.status).toBe('all_resolved');
  });

  it('formats annotation status visual styles and labels', () => {
    expect(formatAnnotationStatus('resolved').label).toBe('已自愈修复');
    expect(formatAnnotationStatus('resolving').label).toBe('手术刀补丁中');
    expect(formatAnnotationStatus('staged').label).toBe('已打包暂存');
    expect(formatAnnotationStatus('failed').label).toBe('补丁应用失败');
    expect(formatAnnotationStatus('pending').label).toBe('待打包暂存');
  });
});
