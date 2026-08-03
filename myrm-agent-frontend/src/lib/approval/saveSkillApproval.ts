/**
 * [INPUT]
 * - 无外部模块依赖（纯函数）
 *
 * [OUTPUT]
 * - isSaveSkillApproval: 识别 save_skill / skill_manage save 审批
 * - normalizeSaveSkillPreviewArgs: 归一化预览字段
 * - basenamePath: 文件路径 basename
 *
 * [POS]
 * save_skill 审批 args 识别与归一化。供 SaveSkillApprovalPreview 与审批卡 wire 使用。
 */

export interface SaveSkillPreviewData {
  description?: string;
  instructions?: string;
  files?: string[];
}

function readTrimmedString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** Whether this approval is a skill save proposal (OW save_skill or harness skill_manage save). */
export function isSaveSkillApproval(toolName: string, toolInput: Record<string, unknown>): boolean {
  if (toolName === 'save_skill' || toolName === 'save_skill_tool') {
    return true;
  }
  if (toolName === 'skill_manage_tool') {
    const action = readTrimmedString(toolInput.action);
    return action === 'save';
  }
  return false;
}

/** Normalize OW save_skill and harness skill_manage_tool save args into one preview shape. */
export function normalizeSaveSkillPreviewArgs(toolInput: Record<string, unknown>): SaveSkillPreviewData {
  const description = readTrimmedString(toolInput.description);
  const instructions =
    readTrimmedString(toolInput.instructions) ?? readTrimmedString(toolInput.content);

  let files: string[] | undefined;
  if (Array.isArray(toolInput.files)) {
    const names = toolInput.files
      .map((entry) => String(entry).trim())
      .filter((entry) => entry.length > 0);
    if (names.length > 0) {
      files = names;
    }
  }

  return { description, instructions, files };
}

export function basenamePath(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
