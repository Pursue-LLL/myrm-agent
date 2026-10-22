import React, { useState } from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { StagedAnnotationsDrawer } from '../StagedAnnotationsDrawer';
import { ElementAnnotationPinOverlay } from '../ElementAnnotationPinOverlay';
import { SurgicalPatchCard } from '../SurgicalPatchCard';
import { useElementPatchStore } from '../useElementPatchStore';
import { StagedBatchPayload } from '../elementPatchTypes';

// 模拟工件预览与批注交互工作台
const MockArtifactWorkspace: React.FC = () => {
  const [dispatchedBatch, setDispatchedBatch] = useState<StagedBatchPayload | null>(null);
  const { stageAnnotation, markAnnotationResolved } = useElementPatchStore();

  const handleSimulateAddThreeAnnotations = () => {
    // 连续打点 3 个元素批注
    stageAnnotation({
      artifactId: 'art-nintendo-store',
      selector: '#buy-btn',
      elementTagName: 'button',
      elementTextSnippet: '立即预订',
      boundingBox: { x: 40, y: 120, width: 140, height: 44 },
      instruction: '背景色改深红，加 12px 圆角',
    });
    stageAnnotation({
      artifactId: 'art-nintendo-store',
      selector: 'h1.game-title',
      elementTagName: 'h1',
      elementTextSnippet: '塞尔达传说：王国之泪 限定版套组',
      boundingBox: { x: 40, y: 40, width: 320, height: 48 },
      instruction: '文案精简为 8 个字，防止移动端两行折断',
    });
    stageAnnotation({
      artifactId: 'art-nintendo-store',
      selector: '.box-shadow-layer',
      elementTagName: 'div',
      boundingBox: { x: 20, y: 20, width: 400, height: 300 },
      instruction: '移除重投影，改用 1px 细边框',
    });
  };

  const handleAgentResolveAll = () => {
    if (dispatchedBatch) {
      dispatchedBatch.annotations.forEach((ann) => {
        markAnnotationResolved(ann.id);
      });
      // 同步更新本地 state
      setDispatchedBatch({
        ...dispatchedBatch,
        annotations: dispatchedBatch.annotations.map((ann) => ({
          ...ann,
          status: 'resolved',
          resolvedAt: Date.now(),
        })),
      });
    }
  };

  return (
    <div data-testid="artifact-workspace" className="relative p-6">
      <h2>工件预览: 任天堂游戏商城</h2>

      <button
        type="button"
        onClick={handleSimulateAddThreeAnnotations}
        data-testid="add-annotations-btn"
      >
        连续打点 3 处批注
      </button>

      {dispatchedBatch && (
        <button
          type="button"
          onClick={handleAgentResolveAll}
          data-testid="agent-resolve-all-btn"
        >
          模拟 Agent 完成手术刀修复并验收
        </button>
      )}

      {/* 工件打点覆盖层 */}
      <div className="relative w-[500px] h-[400px] border border-zinc-800 my-4">
        <ElementAnnotationPinOverlay />
      </div>

      {/* 批注暂存箱抽屉 */}
      <StagedAnnotationsDrawer
        artifactId="art-nintendo-store"
        onDispatchBatch={(payload) => {
          setDispatchedBatch(payload);
        }}
      />

      {/* 对话流中呈现的手术刀审查卡片 */}
      {dispatchedBatch && (
        <div data-testid="chat-stream-container" className="mt-4">
          <SurgicalPatchCard batchPayload={dispatchedBatch} />
        </div>
      )}
    </div>
  );
};

describe('ElementPatch Integration Suite', () => {
  beforeEach(() => {
    useElementPatchStore.getState().reset();
  });

  it('orchestrates staging 3 annotations, batch dispatching with surgical scope, and green resolution alignment', () => {
    render(<MockArtifactWorkspace />);

    // 1. 用户在工件预览界面连续拾取并暂存 3 处批注
    const addBtn = screen.getByTestId('add-annotations-btn');
    fireEvent.click(addBtn);

    // 2. 验证暂存箱抽屉展示 3 处修改待处理
    const drawer = screen.getByTestId('staged-annotations-drawer');
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText('3 项')).toBeInTheDocument();
    expect(within(drawer).getByText('#buy-btn')).toBeInTheDocument();
    expect(within(drawer).getByText('h1.game-title')).toBeInTheDocument();
    expect(within(drawer).getByText('.box-shadow-layer')).toBeInTheDocument();

    // 3. 点击「一键打包发送」
    const dispatchBtn = within(drawer).getByRole('button', {
      name: /一键打包发送 \(3 处修改\)/i,
    });
    fireEvent.click(dispatchBtn);

    // 4. 暂存箱抽屉关闭，主对话流中呈现外科手术式审查卡片
    expect(screen.queryByTestId('staged-annotations-drawer')).toBeNull();
    const chatContainer = screen.getByTestId('chat-stream-container');
    expect(chatContainer).toBeInTheDocument();
    expect(within(chatContainer).getByText('工件多元素打包批注')).toBeInTheDocument();
    expect(within(chatContainer).getByText('局部修复中 (0/3)')).toBeInTheDocument();

    // 5. 模拟 Agent 执行局部修改自实验收变绿
    const resolveBtn = screen.getByTestId('agent-resolve-all-btn');
    fireEvent.click(resolveBtn);

    // 6. 审查卡片状态联动更新为「全部自愈修复 (3/3)」
    expect(within(chatContainer).getByText('全部自愈修复 (3/3)')).toBeInTheDocument();
  });
});
