import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MultimodalTraceViewerModal } from '../MultimodalTraceViewerModal';
import { MultimodalTraceRecordItem } from '../multimodalTraceTypes';

describe('MultimodalTraceViewerModal Component', () => {
  const mockTraces: MultimodalTraceRecordItem[] = [
    {
      trace_id: 'tr_mm_101',
      session_id: 'sess_login_flow',
      prompt_summary: '修复登录弹窗响应式溢出 bug',
      media_references: [
        {
          media_id: 'med_shot_01',
          uri: 'storage://workspace/screenshots/overflow.png',
          modality: 'image',
          mime_type: 'image/png',
          file_size_bytes: 409600,
          sha256_hash: 'sha256_1234567890abcdef',
          visibility_state: 'ready',
          presigned_preview_url: 'https://cdn.local/preview/overflow.png',
          created_at_ms: 1718000000000,
        },
      ],
      steps: [
        {
          step_index: 1,
          step_type: 'input',
          description: '用户上传登录对话框截屏',
          media_ids: ['med_shot_01'],
          status: 'success',
          timestamp_ms: 1718000001000,
        },
        {
          step_index: 2,
          step_type: 'execution',
          description: '添加 CSS max-w-md 与 overflow-y-auto 规则',
          media_ids: [],
          status: 'success',
          timestamp_ms: 1718000002000,
        },
        {
          step_index: 3,
          step_type: 'feedback',
          description: '视觉回归验收测试通过',
          media_ids: [],
          status: 'success',
          timestamp_ms: 1718000003000,
        },
      ],
      pinned_for_golden_eval: false,
      golden_eval_category: '',
      created_at_ms: 1718000000000,
    },
  ];

  it('renders modal header, trace list and media badges', () => {
    render(
      <MultimodalTraceViewerModal
        isOpen={true}
        onClose={vi.fn()}
        traces={mockTraces}
      />
    );

    expect(screen.getByText('多模态 Trace 原位三步排查与媒体引用解耦大盘')).toBeInTheDocument();
    expect(screen.getByText('OTel GenAI 规范对齐')).toBeInTheDocument();
    expect(screen.getAllByText('修复登录弹窗响应式溢出 bug').length).toBeGreaterThanOrEqual(1);

    const imgBadges = screen.getAllByText('📷 图片');
    expect(imgBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders decoupled media reference cards and ready visibility badge', () => {
    render(
      <MultimodalTraceViewerModal
        isOpen={true}
        onClose={vi.fn()}
        traces={mockTraces}
      />
    );

    expect(screen.getByText('storage://workspace/screenshots/overflow.png')).toBeInTheDocument();
    expect(screen.getByText('● 可预览 (Ready)')).toBeInTheDocument();

    const imgPreview = screen.getByRole('img', { name: 'med_shot_01' });
    expect(imgPreview).toBeInTheDocument();
    expect(imgPreview).toHaveAttribute('src', 'https://cdn.local/preview/overflow.png');
  });

  it('renders input-execution-feedback 3-step inspector timeline', () => {
    render(
      <MultimodalTraceViewerModal
        isOpen={true}
        onClose={vi.fn()}
        traces={mockTraces}
      />
    );

    expect(screen.getByText('① 输入 (Input)')).toBeInTheDocument();
    expect(screen.getByText('② 执行 (Execution)')).toBeInTheDocument();
    expect(screen.getByText('③ 反馈 (Feedback)')).toBeInTheDocument();
    expect(screen.getByText('用户上传登录对话框截屏')).toBeInTheDocument();
    expect(screen.getByText('视觉回归验收测试通过')).toBeInTheDocument();
  });

  it('handles Golden Eval pinning and modal close interactions', async () => {
    const handleClose = vi.fn();
    const handlePin = vi.fn();

    render(
      <MultimodalTraceViewerModal
        isOpen={true}
        onClose={handleClose}
        onPinGoldenEval={handlePin}
        traces={mockTraces}
      />
    );

    const pinBtn = screen.getByRole('button', { name: '☆ 沉淀为黄金评测样本 (Pin to Golden Eval)' });
    await React.act(async () => {
      fireEvent.click(pinBtn);
    });
    expect(handlePin).toHaveBeenCalledWith('tr_mm_101', 'visual_regression');

    const closeBtn = screen.getByRole('button', { name: '关闭窗口' });
    await React.act(async () => {
      fireEvent.click(closeBtn);
    });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
