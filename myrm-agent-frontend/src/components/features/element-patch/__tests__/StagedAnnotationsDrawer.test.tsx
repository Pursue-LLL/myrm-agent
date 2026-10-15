import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StagedAnnotationsDrawer } from '../StagedAnnotationsDrawer';
import { useElementPatchStore } from '../useElementPatchStore';

describe('StagedAnnotationsDrawer', () => {
  beforeEach(() => {
    useElementPatchStore.getState().reset();
  });

  it('renders nothing when closed or no staged annotations', () => {
    const { container } = render(<StagedAnnotationsDrawer artifactId="art-test-01" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, surgical patch assurance, and annotation list when open', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-test-01',
      selector: '#login-btn',
      elementTagName: 'button',
      elementTextSnippet: '登录系统',
      boundingBox: { x: 50, y: 50, width: 100, height: 40 },
      instruction: '圆角改为 12px，去掉黑色阴影',
    });

    render(<StagedAnnotationsDrawer artifactId="art-test-01" />);

    expect(screen.getByTestId('staged-annotations-drawer')).toBeInTheDocument();
    expect(screen.getByText('批注暂存箱')).toBeInTheDocument();
    expect(screen.getByText('1 项')).toBeInTheDocument();
    expect(
      screen.getByText('外科手术式精准局部替换 · 全页其余组件 100% 保持不变')
    ).toBeInTheDocument();
    expect(screen.getByText('#login-btn')).toBeInTheDocument();
    expect(screen.getByText('圆角改为 12px，去掉黑色阴影')).toBeInTheDocument();
  });

  it('clears all annotations when clicking trash icon in header', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-test-01',
      selector: '#login-btn',
      elementTagName: 'button',
      boundingBox: { x: 0, y: 0, width: 10, height: 10 },
      instruction: '测试',
    });

    render(<StagedAnnotationsDrawer artifactId="art-test-01" />);

    const clearBtn = screen.getByRole('button', { name: '清空暂存箱' });
    fireEvent.click(clearBtn);

    expect(useElementPatchStore.getState().stagedAnnotations).toHaveLength(0);
    expect(useElementPatchStore.getState().isDrawerOpen).toBe(false);
  });

  it('removes single annotation via item remove button', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-test-01',
      selector: '#item-1',
      elementTagName: 'div',
      boundingBox: { x: 0, y: 0, width: 10, height: 10 },
      instruction: '待删除项',
    });

    render(<StagedAnnotationsDrawer artifactId="art-test-01" />);

    const removeBtn = screen.getByRole('button', { name: '移除第 1 项批注' });
    fireEvent.click(removeBtn);

    expect(useElementPatchStore.getState().stagedAnnotations).toHaveLength(0);
  });

  it('allows inline editing of annotation instruction', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-test-01',
      selector: '#item-edit',
      elementTagName: 'div',
      boundingBox: { x: 0, y: 0, width: 10, height: 10 },
      instruction: '原始诉求内容',
    });

    render(<StagedAnnotationsDrawer artifactId="art-test-01" />);

    const editBtn = screen.getByTitle('修改批注');
    fireEvent.click(editBtn);

    const input = screen.getByDisplayValue('原始诉求内容');
    fireEvent.change(input, { target: { value: '修改后的精准诉求' } });

    const saveBtn = screen.getByTitle('保存修改');
    fireEvent.click(saveBtn);

    expect(screen.getByText('修改后的精准诉求')).toBeInTheDocument();
  });

  it('packages and dispatches batch payload and triggers callback', () => {
    const onDispatchMock = vi.fn();

    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-test-01',
      selector: '#item-pack',
      elementTagName: 'span',
      boundingBox: { x: 0, y: 0, width: 10, height: 10 },
      instruction: '文案精简',
    });

    render(
      <StagedAnnotationsDrawer
        artifactId="art-test-01"
        onDispatchBatch={onDispatchMock}
      />
    );

    const dispatchBtn = screen.getByRole('button', { name: /一键打包发送/i });
    fireEvent.click(dispatchBtn);

    expect(onDispatchMock).toHaveBeenCalledTimes(1);
    expect(onDispatchMock.mock.calls[0][0].artifactId).toBe('art-test-01');
    expect(onDispatchMock.mock.calls[0][0].promptDirective).toContain('<surgical_patch_scope');
  });
});
