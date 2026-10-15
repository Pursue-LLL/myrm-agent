/**
 * [INPUT]
 * (none)
 *
 * [OUTPUT]
 * - blockedReasonText: 把服务端写入的任务阻塞原因译成界面语言；不认识的原因原样返回
 *
 * [POS]
 * 看板卡片与任务抽屉显示阻塞原因的唯一入口。服务端的原因是英文句子（频道命令、诊断、活动流等处原样展示），
 * 这里按整句匹配出界面语言的文案；匹配表与服务端 `landing_gate.PARENT_MERGE_FAILED_REASON` 的字面值保持一致。
 */

// A Map, not an object literal: the reason is server text, and `{}['constructor']` is a function.
const BLOCKED_REASON_KEYS: ReadonlyMap<string, string> = new Map([
  ["Merging a dependency's changes failed; resolve it, then continue", 'blockedReason.parentMergeFailed'],
]);

/** `t` is the translator of the `kanban` namespace. */
export function blockedReasonText(reason: string, t: (key: string) => string): string {
  const key = BLOCKED_REASON_KEYS.get(reason);
  return key ? t(key) : reason;
}
