import { describe, it, expect } from 'vitest';
import {
  DEFAULT_CLARIFICATION_QUESTIONS,
  parseQuestionOption,
  autoApplyAllRecommendations,
  synthesizeV1Spec,
  isQuestionnaireReadyToSubmit,
} from '../clarificationQuestionnaireEngine';
import { QuestionnaireQuestion } from '../clarificationQuestionnaireTypes';

describe('clarificationQuestionnaireEngine', () => {
  it('提供 4 道核心分水岭澄清问题且结构合规', () => {
    expect(DEFAULT_CLARIFICATION_QUESTIONS.length).toBe(4);
    const titles = DEFAULT_CLARIFICATION_QUESTIONS.map((q) => q.title);
    expect(titles.some((t) => t.includes('运行形态'))).toBe(true);
    expect(titles.some((t) => t.includes('核心业务复杂度'))).toBe(true);
    expect(titles.some((t) => t.includes('存储'))).toBe(true);
    expect(titles.some((t) => t.includes('Non-goals'))).toBe(true);
  });

  it('支持智能解析包含(推荐)标签的选项文本', () => {
    const parsedRec = parseQuestionOption('单页本地 Web 应用 (推荐)', 0);
    expect(parsedRec.label).toBe('单页本地 Web 应用');
    expect(parsedRec.isRecommended).toBe(true);

    const parsedNormal = parseQuestionOption('微服务前后端分离系统', 1);
    expect(parsedNormal.label).toBe('微服务前后端分离系统');
    expect(parsedNormal.isRecommended).toBe(false);
  });

  it('一键应用全部推荐项', () => {
    const rawQuestions: QuestionnaireQuestion[] = [
      {
        id: 'q1',
        title: '测试问题1',
        isMultiSelect: false,
        options: [
          { id: 'opt1', label: '普通选项', isRecommended: false },
          { id: 'opt2', label: '推荐选项', isRecommended: true },
        ],
        selectedOptionIds: [],
        attachments: [],
      },
      {
        id: 'q2',
        title: '测试多选',
        isMultiSelect: true,
        options: [
          { id: 'optA', label: '推荐A', isRecommended: true },
          { id: 'optB', label: '普通B', isRecommended: false },
          { id: 'optC', label: '推荐C', isRecommended: true },
        ],
        selectedOptionIds: [],
        attachments: [],
      },
    ];

    const result = autoApplyAllRecommendations(rawQuestions);
    expect(result[0]?.selectedOptionIds).toEqual(['opt2']);
    expect(result[1]?.selectedOptionIds).toEqual(['optA', 'optC']);
  });

  it('正确聚合 V1 Spec 契约并提取 Non-goals', () => {
    const spec = synthesizeV1Spec(DEFAULT_CLARIFICATION_QUESTIONS);

    expect(spec.productShape).toContain('单页');
    expect(spec.coreCapabilities.length).toBeGreaterThan(0);
    expect(spec.nonGoals.length).toBeGreaterThan(0);
    expect(spec.generatedPromptText).toContain('【克制 V1 需求规范与目标对齐协议 (Spec Lock-in)】');
    expect(spec.generatedPromptText).toContain('明确排除不做项 (Non-goals)');
  });

  it('校验问卷就绪状态与附件上传拦截', () => {
    const emptyQ: QuestionnaireQuestion[] = [
      {
        id: 'q-empty',
        title: '未作答题目',
        isMultiSelect: false,
        options: [{ id: 'opt1', label: 'A', isRecommended: false }],
        selectedOptionIds: [],
        attachments: [],
      },
    ];

    const unreadyCheck = isQuestionnaireReadyToSubmit(emptyQ);
    expect(unreadyCheck.isReady).toBe(false);
    expect(unreadyCheck.unfulfilledIndex).toBe(0);

    const uploadingQ: QuestionnaireQuestion[] = [
      {
        id: 'q-uploading',
        title: '带附件题目',
        isMultiSelect: false,
        options: [{ id: 'opt1', label: 'A', isRecommended: false }],
        selectedOptionIds: ['opt1'],
        attachments: [
          {
            id: 'att-1',
            name: 'uploading.png',
            size: 100,
            type: 'image/png',
            uploadStatus: 'uploading',
          },
        ],
      },
    ];

    const uploadingCheck = isQuestionnaireReadyToSubmit(uploadingQ);
    expect(uploadingCheck.isReady).toBe(false);
    expect(uploadingCheck.reason).toContain('正在上传');
  });
});
