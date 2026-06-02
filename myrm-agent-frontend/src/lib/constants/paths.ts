/**
 * 存储路径常量和工具函数
 *
 * 用于统一前后端路径处理逻辑
 */

/**
 * 用户工作空间文件目录前缀
 * 后端返回的工件路径包含此前缀，但API请求时需要去除
 *
 * 例如：
 * - 后端返回: "files/skills/prebuilt/calculator/SKILL.md"
 * - API请求: "skills/prebuilt/calculator/SKILL.md"
 */
export const WORKSPACE_FILES_PREFIX = 'files/';

/**
 * 从工件文件名中提取相对于工作空间的路径
 *
 * @param filename - 工件的完整文件名（可能包含 files/ 前缀）
 * @returns 相对于工作空间 files 目录的路径
 *
 * @example
 * stripWorkspacePrefix("files/skills/prebuilt/calc/SKILL.md")
 * // => "skills/prebuilt/calc/SKILL.md"
 *
 * stripWorkspacePrefix("my-skill/SKILL.md")
 * // => "my-skill/SKILL.md"
 */
export function stripWorkspaceFilesPrefix(filename: string): string {
  if (filename.startsWith(WORKSPACE_FILES_PREFIX)) {
    return filename.slice(WORKSPACE_FILES_PREFIX.length);
  }
  return filename;
}

/**
 * 从文件路径中提取目录部分
 *
 * @param filepath - 完整文件路径
 * @returns 目录路径（不包含文件名）
 *
 * @example
 * extractDirectory("skills/prebuilt/calc/SKILL.md")
 * // => "skills/prebuilt/calc"
 *
 * extractDirectory("SKILL.md")
 * // => ""
 */
export function extractDirectory(filepath: string): string {
  const lastSlashIndex = filepath.lastIndexOf('/');
  if (lastSlashIndex === -1) {
    return '';
  }
  return filepath.substring(0, lastSlashIndex);
}

/**
 * 从工件文件名中提取技能目录（去除 files/ 前缀和文件名）
 *
 * @param artifactFilename - 工件的完整文件名
 * @returns 技能目录路径，可直接用于API请求
 *
 * @example
 * extractSkillDirectory("files/skills/prebuilt/calc/SKILL.md")
 * // => "skills/prebuilt/calc"
 */
export function extractSkillDirectory(artifactFilename: string): string {
  const withoutPrefix = stripWorkspaceFilesPrefix(artifactFilename);
  return extractDirectory(withoutPrefix);
}
