/**
 * 交互式 UI 工具函数
 */

// ============ 验证规则类型定义 ============

/**
 * 验证规则类型
 */
export interface ValidationRule {
  type: 'required' | 'minLength' | 'maxLength' | 'pattern' | 'min' | 'max' | 'email' | 'custom';
  value?: unknown; // 规则参数（如 minLength 的长度值）
  message?: string; // 自定义错误消息（覆盖默认 i18n 消息）
}

/**
 * 结构化验证错误（支持 i18n）
 */
export interface ValidationErrorInfo {
  key: string; // i18n key，如 'required'
  params: Record<string, string | number>; // 插值参数
  customMessage?: string; // 自定义消息（如果提供则优先使用）
}

/**
 * 字段验证错误
 */
export interface ValidationError {
  path: string; // 数据路径
  message: string; // 错误消息
}

/**
 * 验证结果
 */
export interface ValidationResult {
  isValid: boolean;
  errors: Map<string, ValidationErrorInfo>; // path -> error info
}

// ============ 验证函数 ============

/**
 * 执行单个验证规则，返回结构化错误信息
 */
function executeValidationRule(value: unknown, rule: ValidationRule, fieldLabel: string): ValidationErrorInfo | null {
  const strValue = typeof value === 'string' ? value : String(value ?? '');
  const numValue = typeof value === 'number' ? value : Number(value);

  switch (rule.type) {
    case 'required':
      if (value === undefined || value === null || strValue.trim() === '') {
        return {
          key: 'required',
          params: { field: fieldLabel },
          customMessage: rule.message,
        };
      }
      break;

    case 'minLength':
      if (strValue.length < (rule.value as number)) {
        return {
          key: 'minLength',
          params: { field: fieldLabel, min: rule.value as number },
          customMessage: rule.message,
        };
      }
      break;

    case 'maxLength':
      if (strValue.length > (rule.value as number)) {
        return {
          key: 'maxLength',
          params: { field: fieldLabel, max: rule.value as number },
          customMessage: rule.message,
        };
      }
      break;

    case 'pattern': {
      const pattern = new RegExp(rule.value as string);
      if (!pattern.test(strValue)) {
        return {
          key: 'pattern',
          params: { field: fieldLabel },
          customMessage: rule.message,
        };
      }
      break;
    }

    case 'min':
      if (!isNaN(numValue) && numValue < (rule.value as number)) {
        return {
          key: 'min',
          params: { field: fieldLabel, min: rule.value as number },
          customMessage: rule.message,
        };
      }
      break;

    case 'max':
      if (!isNaN(numValue) && numValue > (rule.value as number)) {
        return {
          key: 'max',
          params: { field: fieldLabel, max: rule.value as number },
          customMessage: rule.message,
        };
      }
      break;

    case 'email': {
      const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (strValue && !emailPattern.test(strValue)) {
        return {
          key: 'email',
          params: { field: fieldLabel },
          customMessage: rule.message,
        };
      }
      break;
    }
  }

  return null;
}

/**
 * 验证单个字段，返回结构化错误信息
 */
export function validateField(value: unknown, rules: ValidationRule[], fieldLabel: string): ValidationErrorInfo | null {
  for (const rule of rules) {
    const error = executeValidationRule(value, rule, fieldLabel);
    if (error) {
      return error;
    }
  }
  return null;
}

/**
 * 从组件 props 中提取验证规则
 */
export function extractValidationRules(props: Record<string, unknown>): ValidationRule[] {
  const rules: ValidationRule[] = [];

  // 支持直接定义 validation 规则数组
  if (Array.isArray(props.validation)) {
    rules.push(...(props.validation as ValidationRule[]));
  }

  // 支持快捷属性
  if (props.required === true) {
    rules.push({ type: 'required', message: props.requiredMessage as string | undefined });
  }

  if (typeof props.minLength === 'number') {
    rules.push({ type: 'minLength', value: props.minLength });
  }

  if (typeof props.maxLength === 'number') {
    rules.push({ type: 'maxLength', value: props.maxLength });
  }

  if (typeof props.pattern === 'string') {
    rules.push({
      type: 'pattern',
      value: props.pattern,
      message: props.patternMessage as string | undefined,
    });
  }

  if (typeof props.min === 'number') {
    rules.push({ type: 'min', value: props.min });
  }

  if (typeof props.max === 'number') {
    rules.push({ type: 'max', value: props.max });
  }

  if (props.type === 'email') {
    rules.push({ type: 'email' });
  }

  return rules;
}

// ============ 数据工具函数 ============

/**
 * 根据路径从数据对象获取值
 * 支持 JSONPath 风格的路径，如 "$.form.name" 或 "form.name"
 */
export function getValueByPath(data: Record<string, unknown>, path: string): unknown {
  if (!path || !data) return undefined;

  // 移除开头的 "$." 前缀
  const cleanPath = path.startsWith('$.') ? path.slice(2) : path;
  const keys = cleanPath.split('.');

  let current: unknown = data;
  for (const key of keys) {
    if (current === null || current === undefined) return undefined;
    if (typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[key];
  }

  return current;
}

/**
 * 根据路径设置数据对象的值
 * 返回一个新的数据对象（不可变更新）
 */
export function setValueByPath(data: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  if (!path) return data;

  // 移除开头的 "$." 前缀
  const cleanPath = path.startsWith('$.') ? path.slice(2) : path;
  const keys = cleanPath.split('.');

  // 深拷贝数据对象
  const newData = structuredClone(data);

  // 遍历路径并设置值
  let current: Record<string, unknown> = newData;
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (current[key] === undefined || current[key] === null || typeof current[key] !== 'object') {
      current[key] = {};
    }
    current = current[key] as Record<string, unknown>;
  }

  const lastKey = keys[keys.length - 1];
  current[lastKey] = value;

  return newData;
}

/**
 * 构建组件 ID 到组件的映射
 */
export function buildComponentMap<T extends { id: string }>(components: T[]): Map<string, T> {
  const map = new Map<string, T>();
  for (const comp of components) {
    map.set(comp.id, comp);
  }
  return map;
}

export interface UIActionMessageLabels {
  header: string;
  actionLabel: string;
  dataLabel: string;
  emptyField: string;
  actionTypes: Record<string, string>;
}

/**
 * Format a UI action as a user message for the Agent.
 * Machine-readable JSON is appended in `<ui_action_data>` (stripped from chat display).
 */
export function formatUIActionAsMessage(
  event: {
    surface_id: string;
    action_id: string;
    action_type: string;
    data: Record<string, unknown>;
    payload: Record<string, unknown>;
  },
  labels: UIActionMessageLabels,
): string {
  const actionDescription = getActionDescription(event.action_type, event.action_id, labels);
  const formattedData = formatDataForMessage(event.data, labels.emptyField);

  const parts: string[] = [labels.header, `${labels.actionLabel}: ${actionDescription}`];

  if (formattedData) {
    parts.push(`${labels.dataLabel}:`);
    parts.push(formattedData);
  }

  const jsonData = JSON.stringify({
    type: 'ui_action',
    surface_id: event.surface_id,
    action_id: event.action_id,
    action_type: event.action_type,
    data: event.data,
    payload: event.payload,
  });
  parts.push(`\n<ui_action_data>${jsonData}</ui_action_data>`);

  return parts.join('\n');
}

function getActionDescription(actionType: string, actionId: string, labels: UIActionMessageLabels): string {
  const known = labels.actionTypes[actionType];
  if (known) {
    return known;
  }
  return actionId ? `${actionType} (${actionId})` : actionType;
}

function formatDataForMessage(data: Record<string, unknown>, emptyFieldLabel: string): string {
  if (!data || Object.keys(data).length === 0) {
    return '';
  }

  const lines: string[] = [];

  function formatValue(value: unknown, indent: number = 0): string {
    const prefix = '  '.repeat(indent);

    if (value === null || value === undefined) {
      return `${prefix}${emptyFieldLabel}`;
    }

    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return value.map((v) => `${prefix}- ${formatValue(v, 0)}`).join('\n');
      }

      const entries = Object.entries(value as Record<string, unknown>);
      return entries
        .map(([k, v]) => {
          const formattedValue = formatValue(v, indent + 1);
          if (typeof v === 'object' && v !== null) {
            return `${prefix}${k}:\n${formattedValue}`;
          }
          return `${prefix}${k}: ${formattedValue.trim()}`;
        })
        .join('\n');
    }

    return String(value);
  }

  lines.push(formatValue(data, 0));
  return lines.join('\n');
}
