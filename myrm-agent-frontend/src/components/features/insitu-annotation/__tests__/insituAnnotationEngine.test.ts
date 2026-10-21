import { describe, it, expect } from 'vitest';
import {
  generateCssFromPatches,
  compileBatchAnnotationsPrompt,
  buildBatchAnnotationPayload,
} from '../insituAnnotationEngine';
import { ElementStylePatch, VisualCommentPin } from '../insituAnnotationTypes';

describe('insituAnnotationEngine 核心函数单测', () => {
  const patches: ElementStylePatch[] = [
    {
      selector: '#submit-btn',
      tagName: 'button',
      color: '#ffffff',
      backgroundColor: '#4f46e5',
      fontSize: '16px',
      padding: '12px',
      textContent: '立即提交',
    },
    {
      selector: '.title',
      tagName: 'h1',
      fontSize: '24px',
    },
  ];

  const comments: VisualCommentPin[] = [
    {
      id: 'pin-1',
      index: 1,
      x: 100,
      y: 150,
      selector: '#submit-btn',
      targetTag: 'button',
      targetPreviewSnippet: '<button>提交</button>',
      commentText: '按钮增加微弱阴影与圆角',
      createdAt: '14:00:00',
    },
    {
      id: 'pin-2',
      index: 2,
      x: 250,
      y: 80,
      selector: '.title',
      targetTag: 'h1',
      targetPreviewSnippet: '<h1>标题</h1>',
      commentText: '文字行高增加并加粗',
      createdAt: '14:01:00',
    },
  ];

  it('generateCssFromPatches 能将样式补丁数组编译为标准 CSS 规则', () => {
    const css = generateCssFromPatches(patches);

    expect(css).toContain('#submit-btn {');
    expect(css).toContain('color: #ffffff !important;');
    expect(css).toContain('background-color: #4f46e5 !important;');
    expect(css).toContain('font-size: 16px !important;');
    expect(css).toContain('.title { font-size: 24px !important; }');

    expect(generateCssFromPatches([])).toBe('');
  });

  it('compileBatchAnnotationsPrompt 应将多点批注与就地补丁编译为结构化 Prompt', () => {
    const prompt = compileBatchAnnotationsPrompt('art-landing-page', comments, patches);

    expect(prompt).toContain('【工件画布多点精准修改需求包】');
    expect(prompt).toContain('工件 ID: art-landing-page');
    expect(prompt).toContain('批注数量: 2 处');
    expect(prompt).toContain('就地样式补丁: 2 处');
    expect(prompt).toContain('批注 [1] 目标元素: <button> (Selector: "#submit-btn")');
    expect(prompt).toContain('修改诉求: 按钮增加微弱阴影与圆角');
    expect(prompt).toContain('补丁 [1] 目标: #submit-btn');
    expect(prompt).toContain('文本内容改为: "立即提交"');
  });

  it('buildBatchAnnotationPayload 组装完整分发对象', () => {
    const payload = buildBatchAnnotationPayload('art-test-1', comments, patches);

    expect(payload.artifactId).toBe('art-test-1');
    expect(payload.totalComments).toBe(2);
    expect(payload.comments.length).toBe(2);
    expect(payload.appliedStylePatches.length).toBe(2);
    expect(payload.dispatchedAt).toBeDefined();
    expect(payload.compiledPromptInstruction).toContain('【工件画布多点精准修改需求包】');
  });
});
