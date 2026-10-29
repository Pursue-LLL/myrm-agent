/**
 * [INPUT]
 * - 审批卡的输入条目（工具入参的 [key, value] 列表）与用户在编辑视图里改过的文本
 *
 * [OUTPUT]
 * - initialEditedArgs: 把入参条目转成编辑视图的初始文本
 * - parseEditedArgs: 把编辑后的文本还原成入参，并指出写成了破损 JSON 的字段
 * - hasEditedChanges: 判断编辑后的文本相对原入参是否有改动
 *
 * [POS]
 * 审批卡「编辑后批准」的纯函数部分：文本与入参之间的互转与比较，不依赖 React。
 */

export type InputEntry = [string, unknown];

function stringifyEntryValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value === undefined || value === null) {
    return '';
  }
  return JSON.stringify(value, null, 2);
}

export function initialEditedArgs(entries: InputEntry[]): Record<string, string> {
  const initial: Record<string, string> = {};
  for (const [key, value] of entries) {
    initial[key] = stringifyEntryValue(value);
  }
  return initial;
}

/**
 * 能解析成 JSON 的按 JSON 还原（数字、布尔、对象保持原类型），否则原样当字符串；
 * 看起来想写对象或数组却解析失败的字段记入 `invalidFields`，由调用方拒绝提交。
 */
export function parseEditedArgs(editedArgs: Record<string, string>): {
  parsed: Record<string, unknown>;
  invalidFields: string[];
} {
  const parsed: Record<string, unknown> = {};
  const invalidFields: string[] = [];

  for (const [key, text] of Object.entries(editedArgs)) {
    try {
      parsed[key] = JSON.parse(text);
    } catch {
      const trimmed = text.trim();
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        invalidFields.push(key);
      }
      parsed[key] = text;
    }
  }
  return { parsed, invalidFields };
}

/** 与编辑视图的初始文本同一口径比较：入参里的 null / 缺省值没被改过就不算改动。 */
export function hasEditedChanges(entries: InputEntry[], editedArgs: Record<string, string>): boolean {
  return entries.some(([key, original]) => editedArgs[key] !== stringifyEntryValue(original));
}
