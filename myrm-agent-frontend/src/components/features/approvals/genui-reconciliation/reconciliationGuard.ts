import type {
  AnswersState,
  DynamicFormSpec,
  FieldDirtyMap,
  ReconciliationOutcome,
} from './genuiReconciliationTypes';

/**
 * 生成式 UI 状态调和守卫算法
 * 优先级铁律: 用户手动输入的持久化/草稿值 (Dirty AnswersState) > 新到达 Spec 中的默认值 (Spec Defaults)
 */
export function reconcileAnswersWithSpec(
  currentAnswers: AnswersState,
  dirtyFields: FieldDirtyMap,
  newSpec: DynamicFormSpec
): ReconciliationOutcome {
  const mergedAnswers: AnswersState = {};
  let preservedCount = 0;
  let initializedCount = 0;

  for (const field of newSpec.fields) {
    const fieldId = field.fieldId;
    const isUserDirty = dirtyFields[fieldId] === true;
    const existingVal = currentAnswers[fieldId];

    if (isUserDirty && existingVal !== undefined) {
      // 1. 用户已明确输入或修改该字段: 100% 保持用户的值不变，严禁被新 Spec 默认值覆盖！
      mergedAnswers[fieldId] = existingVal;
      preservedCount += 1;
    } else if (existingVal !== undefined && !isUserDirty) {
      // 2. 字段已存在但用户未改动过（原本就是默认值）: 如果新 Spec 调整了默认值，同步跟进为新默认值
      mergedAnswers[fieldId] = field.defaultValue;
      initializedCount += 1;
    } else {
      // 3. 全新字段（用户此前未接触过）: 初始化为新 Spec 的默认值
      mergedAnswers[fieldId] = field.defaultValue;
      initializedCount += 1;
    }
  }

  return {
    mergedAnswers,
    preservedUserFieldsCount: preservedCount,
    initializedNewFieldsCount: initializedCount,
    reconciledAt: new Date().toISOString(),
  };
}

/**
 * 校验表单是否包含未保存的脏字段
 */
export function hasDirtyInputs(dirtyFields: FieldDirtyMap): boolean {
  for (const key of Object.keys(dirtyFields)) {
    if (dirtyFields[key] === true) {
      return true;
    }
  }
  return false;
}
