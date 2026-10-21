import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClarificationQuestionnaireCard } from '../ClarificationQuestionnaireCard';
import { useClarificationQuestionnaireStore } from '../useClarificationQuestionnaireStore';

describe('ClarificationQuestionnaireCard', () => {
  beforeEach(() => {
    useClarificationQuestionnaireStore.getState().reset();
  });

  it('正常渲染卡片头部、答题进度与第一道题目选项', () => {
    render(<ClarificationQuestionnaireCard />);

    expect(screen.getByTestId('clarification-questionnaire-card')).toBeInTheDocument();
    expect(screen.getByText('需求前置澄清与 V1 目标对齐问卷')).toBeInTheDocument();
    expect(screen.getByText(/4\/4 已答/)).toBeInTheDocument();
    expect(screen.getByText('1. 您期望的目标运行形态是怎样的？')).toBeInTheDocument();
    expect(screen.getByText('单页本地 Web 应用 (开箱即用)')).toBeInTheDocument();
    expect(screen.getByText('推荐')).toBeInTheDocument();
  });

  it('点击选项切换选择状态', () => {
    render(<ClarificationQuestionnaireCard />);

    const cliOption = screen.getByText('轻量命令行 CLI 工具');
    fireEvent.click(cliOption);

    const qShape = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape');
    expect(qShape?.selectedOptionIds).toEqual(['opt-cli']);
  });

  it('点击“一键按推荐确认全部”按钮触发批量应用', () => {
    render(<ClarificationQuestionnaireCard />);

    const recBtn = screen.getByText('一键按推荐确认全部');
    fireEvent.click(recBtn);

    const questions = useClarificationQuestionnaireStore.getState().questions;
    for (const q of questions) {
      expect(q.selectedOptionIds.length).toBeGreaterThan(0);
    }
  });

  it('支持上一题与下一题翻页', () => {
    render(<ClarificationQuestionnaireCard />);

    expect(screen.getByText('1. 您期望的目标运行形态是怎样的？')).toBeInTheDocument();

    const nextBtn = screen.getByText('下一题');
    fireEvent.click(nextBtn);

    expect(screen.getByText('2. 系统的核心业务复杂度与功能范围？')).toBeInTheDocument();

    const prevBtn = screen.getByText('上一题');
    fireEvent.click(prevBtn);

    expect(screen.getByText('1. 您期望的目标运行形态是怎样的？')).toBeInTheDocument();
  });

  it('支持展开补充说明并键入内容以及添加附件', () => {
    render(<ClarificationQuestionnaireCard />);

    const toggleTextBtn = screen.getByText('+ 填写该题目的补充说明或特殊需求');
    fireEvent.click(toggleTextBtn);

    const textarea = screen.getByPlaceholderText('如需补充特定逻辑、参数公式或限制条件，请在此键入...');
    fireEvent.change(textarea, { target: { value: '必须兼容离线模式' } });

    expect(
      useClarificationQuestionnaireStore.getState().questions[0]?.customTextAnswer
    ).toBe('必须兼容离线模式');

    const addAttBtn = screen.getByText('上传/粘贴附件材料');
    fireEvent.click(addAttBtn);

    const attList = useClarificationQuestionnaireStore.getState().questions[0]?.attachments;
    expect(attList?.length).toBe(1);
    expect(screen.getByText(/需求参考截图_/)).toBeInTheDocument();
  });

  it('点击“锁定规范并启动”触发 onSubmitSpec 回调', () => {
    const handleSubmit = vi.fn();
    render(<ClarificationQuestionnaireCard onSubmitSpec={handleSubmit} />);

    const submitBtn = screen.getByText('锁定规范并启动 (Enter)');
    fireEvent.click(submitBtn);

    expect(handleSubmit).toHaveBeenCalled();
    expect(useClarificationQuestionnaireStore.getState().status).toBe('submitted');
  });
});
