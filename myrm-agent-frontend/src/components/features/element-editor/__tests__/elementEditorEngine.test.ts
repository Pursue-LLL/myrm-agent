import { describe, it, expect } from 'vitest';
import {
  extractElementInfo,
  buildTargetedMicroPatchPrompt,
  createSnapshot,
  isUndoShortcut,
  isRedoShortcut,
  getDefaultHtmlContent,
  getDefaultSnapshots,
} from '../elementEditorEngine';
import { InspectorElementInfo } from '../elementEditorTypes';

describe('elementEditorEngine', () => {
  it('extractElementInfo 应正确提取 DOM 元素的标签、选择器与相对坐标', () => {
    const dummyDiv = document.createElement('div');
    dummyDiv.id = 'test-card';
    dummyDiv.className = 'p-4 rounded bg-slate-900';
    dummyDiv.innerText = 'Card Content';
    document.body.appendChild(dummyDiv);

    const info = extractElementInfo(dummyDiv, {
      top: 10,
      left: 10,
      width: 500,
      height: 400,
    });

    expect(info.tag).toBe('div');
    expect(info.id).toBe('test-card');
    expect(info.selector).toContain('div#test-card');
    expect(info.innerText).toBe('Card Content');

    document.body.removeChild(dummyDiv);
  });

  it('buildTargetedMicroPatchPrompt 应组装防改偏的外科手术式微补丁 Prompt', () => {
    const elInfo: InspectorElementInfo = {
      id: 'btn-1',
      tag: 'button',
      selector: 'button#btn-1.primary-btn',
      xpath: '//button',
      rect: { top: 0, left: 0, width: 100, height: 36 },
      innerText: '提交',
      classes: 'primary-btn',
      sourceFilePath: 'src/components/Header.tsx',
      sourceLine: 28,
    };

    const prompt = buildTargetedMicroPatchPrompt({
      element: elInfo,
      instruction: '改成深紫渐变，加圆角',
      category: 'style',
    });

    expect(prompt).toContain('[外科手术式微补丁请求]');
    expect(prompt).toContain('目标标签: <button>');
    expect(prompt).toContain('src/components/Header.tsx:28');
    expect(prompt).toContain('改成深紫渐变，加圆角');
    expect(prompt).toContain('严禁变动任何未选中的周围标签');
  });

  it('createSnapshot 应生成携带正确版本号与行差异的快照', () => {
    const prev = 'line1\nline2';
    const next = 'line1\nline2\nline3\nline4';
    const snapshot = createSnapshot(prev, next, '增加2行代码', 2, 'button');

    expect(snapshot.versionNumber).toBe(2);
    expect(snapshot.description).toBe('增加2行代码');
    expect(snapshot.diffStats.addedLines).toBe(2);
    expect(snapshot.diffStats.changedTarget).toBe('button');
  });

  it('isUndoShortcut 与 isRedoShortcut 应准确识别跨平台快捷键', () => {
    // Cmd+Z
    const undoEvt = {
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      key: 'z',
      code: 'KeyZ',
    } as unknown as KeyboardEvent;
    expect(isUndoShortcut(undoEvt)).toBe(true);
    expect(isRedoShortcut(undoEvt)).toBe(false);

    // Cmd+Shift+Z (Redo)
    const redoEvt = {
      metaKey: true,
      ctrlKey: false,
      shiftKey: true,
      key: 'z',
      code: 'KeyZ',
    } as unknown as KeyboardEvent;
    expect(isUndoShortcut(redoEvt)).toBe(false);
    expect(isRedoShortcut(redoEvt)).toBe(true);

    // Ctrl+Y (Redo)
    const ctrlYEvt = {
      metaKey: false,
      ctrlKey: true,
      shiftKey: false,
      key: 'y',
      code: 'KeyY',
    } as unknown as KeyboardEvent;
    expect(isRedoShortcut(ctrlYEvt)).toBe(true);
  });

  it('getDefaultHtmlContent 与 getDefaultSnapshots 应提供初始工件与快照历史', () => {
    const html = getDefaultHtmlContent();
    expect(html).toContain('hero-title');
    expect(html).toContain('primary-action-btn');

    const snapshots = getDefaultSnapshots();
    expect(snapshots.length).toBe(1);
    expect(snapshots[0].versionNumber).toBe(1);
  });
});
