import { describe, expect, it } from 'vitest';
import { reconcileAnswersWithSpec, hasDirtyInputs } from '../reconciliationGuard';
import type { DynamicFormSpec } from '../genuiReconciliationTypes';

describe('reconciliationGuard', () => {
  const baseSpec: DynamicFormSpec = {
    specId: 'spec-test-v1',
    version: 1,
    title: '测试动态表单',
    description: '用于测试状态调和算法',
    pushedAt: new Date().toISOString(),
    fields: [
      {
        fieldId: 'field_a',
        label: '字段 A',
        type: 'text',
        defaultValue: 'default_a',
      },
      {
        fieldId: 'field_b',
        label: '字段 B',
        type: 'number',
        defaultValue: 10,
      },
    ],
  };

  it('应该严格保护用户已修改的字段，免受新 Spec 默认值覆盖', () => {
    const currentAnswers = {
      field_a: 'user_custom_input',
      field_b: 10,
    };
    const dirtyFields = {
      field_a: true,
      field_b: false,
    };

    const newSpec: DynamicFormSpec = {
      ...baseSpec,
      version: 2,
      fields: [
        {
          fieldId: 'field_a',
          label: '字段 A 更新',
          type: 'text',
          defaultValue: 'new_default_a', // 后端尝试下发新默认值
        },
        {
          fieldId: 'field_b',
          label: '字段 B 更新',
          type: 'number',
          defaultValue: 20, // 未修改字段应该同步为新默认值
        },
        {
          fieldId: 'field_c',
          label: '全新字段 C',
          type: 'boolean',
          defaultValue: true,
        },
      ],
    };

    const outcome = reconcileAnswersWithSpec(currentAnswers, dirtyFields, newSpec);

    // 核心断言: 用户修改过的 field_a 必须 100% 保持用户的值
    expect(outcome.mergedAnswers.field_a).toBe('user_custom_input');
    // 用户未改过的 field_b 应该同步新 Spec 的默认值
    expect(outcome.mergedAnswers.field_b).toBe(20);
    // 新字段 field_c 应该被正确初始化
    expect(outcome.mergedAnswers.field_c).toBe(true);

    expect(outcome.preservedUserFieldsCount).toBe(1);
    expect(outcome.initializedNewFieldsCount).toBe(2);
  });

  it('hasDirtyInputs 应该准确识别表单是否包含脏字段', () => {
    expect(hasDirtyInputs({})).toBe(false);
    expect(hasDirtyInputs({ field_a: false })).toBe(false);
    expect(hasDirtyInputs({ field_a: true })).toBe(true);
    expect(hasDirtyInputs({ field_a: false, field_b: true })).toBe(true);
  });
});
