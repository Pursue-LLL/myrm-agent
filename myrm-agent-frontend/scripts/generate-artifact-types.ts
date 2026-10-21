#!/usr/bin/env bun
/**
 * 工件类型映射生成脚本
 *
 * 从后端 API 获取类型映射，生成 TypeScript 文件。
 * 确保前后端类型映射保持一致。
 *
 * 使用方法：
 *   bun run generate:artifact-types
 *
 * 或手动执行：
 *   bun scripts/generate-artifact-types.ts
 */

import { writeFileSync } from 'fs';
import { join } from 'path';

// 后端 API 地址（开发环境）
const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000/api';

interface ArtifactMappingsResponse {
  artifact_types: string[];
  extension_to_language: Record<string, string>;
  extension_to_artifact_type: Record<string, string>;
  mime_to_artifact_type: Record<string, string>;
}

async function fetchMappings(): Promise<ArtifactMappingsResponse> {
  const response = await fetch(`${API_BASE_URL}/config/artifact-mappings`);

  if (!response.ok) {
    throw new Error(`Failed to fetch mappings: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

function generateTypeFile(mappings: ArtifactMappingsResponse): string {
  const timestamp = new Date().toISOString();

  return `/**
 * 工件类型映射 - 由后端自动生成
 *
 * ⚠️ 此文件由脚本自动生成，请勿手动修改！
 * 运行 \`bun run generate:artifact-types\` 重新生成。
 *
 * 生成时间: ${timestamp}
 * 数据来源: ${API_BASE_URL}/config/artifact-mappings
 */

// ==================== 工件类型 ====================

/** 工件类型枚举值 */
export type ArtifactType = ${mappings.artifact_types.map((t) => `'${t}'`).join(' | ')};

/** 所有支持的工件类型 */
export const ARTIFACT_TYPES: readonly ArtifactType[] = [${mappings.artifact_types.map((t) => `'${t}'`).join(', ')}] as const;

// ==================== 文件扩展名 → 编程语言映射 ====================

/** 文件扩展名到编程语言的映射（用于语法高亮） */
export const EXTENSION_TO_LANGUAGE: Readonly<Record<string, string>> = ${JSON.stringify(mappings.extension_to_language, null, 2)} as const;

// ==================== 文件扩展名 → 工件类型映射 ====================

/** 文件扩展名到工件类型的映射 */
export const EXTENSION_TO_ARTIFACT_TYPE: Readonly<Record<string, ArtifactType>> = ${JSON.stringify(mappings.extension_to_artifact_type, null, 2)} as const;

// ==================== MIME 类型 → 工件类型映射 ====================

/** MIME 类型到工件类型的映射 */
export const MIME_TO_ARTIFACT_TYPE: Readonly<Record<string, ArtifactType>> = ${JSON.stringify(mappings.mime_to_artifact_type, null, 2)} as const;

// ==================== 工具函数 ====================

/** 根据文件名推断编程语言 */
export function inferLanguage(filename: string): string | undefined {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase();
  return EXTENSION_TO_LANGUAGE[ext];
}

/** 根据文件名推断工件类型 */
export function inferArtifactTypeFromExtension(filename: string): ArtifactType {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase();
  return EXTENSION_TO_ARTIFACT_TYPE[ext] || 'binary';
}

/** 根据 MIME 类型推断工件类型 */
export function inferArtifactTypeFromMime(mimeType: string): ArtifactType {
  return MIME_TO_ARTIFACT_TYPE[mimeType] || 'binary';
}
`;
}

async function main() {
  console.log('🔄 正在从后端获取工件类型映射...');

  try {
    const mappings = await fetchMappings();

    console.log(`✅ 获取成功:`);
    console.log(`   - 工件类型: ${mappings.artifact_types.length} 个`);
    console.log(`   - 扩展名→语言映射: ${Object.keys(mappings.extension_to_language).length} 个`);
    console.log(`   - 扩展名→类型映射: ${Object.keys(mappings.extension_to_artifact_type).length} 个`);
    console.log(`   - MIME→类型映射: ${Object.keys(mappings.mime_to_artifact_type).length} 个`);

    const typeFile = generateTypeFile(mappings);
    const outputPath = join(__dirname, '../src/types/artifact-mappings.generated.ts');

    writeFileSync(outputPath, typeFile, 'utf-8');

    console.log(`📝 已生成: ${outputPath}`);
    console.log('✨ 完成！');
  } catch (error) {
    console.error('❌ 生成失败:', error);
    console.log('\n💡 提示: 确保后端服务正在运行 (http://localhost:8000)');
    console.log('   或设置 API_BASE_URL 环境变量指向正确的后端地址');
    process.exit(1);
  }
}

main();



















