/**
 * Artifact 相关类型定义
 * 提供更严格的类型安全
 *
 * ⚠️ 类型映射的 Single Source of Truth 在后端：
 *    app/core/constants/artifact_mappings.py
 *
 * 可通过 `bun run generate:artifact-types` 从后端 API 自动生成映射文件：
 *    src/types/artifact-mappings.generated.ts
 */

import { Artifact, ArtifactType } from '@/store/chat/types';

// ==================== 流式事件类型 ====================

/** Artifact 流式事件基础接口 */
interface ArtifactStreamEventBase {
  type: string;
  messageId: string;
}

/** Artifacts 完成事件 */
export interface ArtifactsEvent extends ArtifactStreamEventBase {
  type: 'artifacts';
  data: Artifact[];
}

/** Artifact 内容实时更新事件 */
export interface ArtifactContentEvent extends ArtifactStreamEventBase {
  type: 'artifact_content';
  artifactId: string;
  subtype: 'start' | 'chunk' | 'end';
  artifact?: Artifact; // subtype === 'start' 时存在
  content?: string; // subtype === 'chunk' 时存在
}

/** 所有 Artifact 相关流式事件 */
export type ArtifactStreamEvent = ArtifactsEvent | ArtifactContentEvent;

// ==================== 渲染相关类型 ====================

/** 可预览的 Artifact 类型 */
export type PreviewableArtifactType = 'code' | 'document' | 'html' | 'image' | 'video' | 'audio' | 'svg' | 'mermaid';

/** 不可预览的 Artifact 类型 */
export type NonPreviewableArtifactType = 'pdf' | 'binary';

/** 检查 Artifact 是否可预览 */
export function isPreviewable(type: ArtifactType): type is PreviewableArtifactType {
  return ['code', 'document', 'html', 'image', 'video', 'audio', 'svg', 'mermaid'].includes(type);
}

/** 需要加载内容的 Artifact 类型 */
export type ContentLoadableType = 'code' | 'document' | 'svg' | 'mermaid';

/** 检查 Artifact 是否需要加载内容 */
export function needsContentLoad(type: ArtifactType): type is ContentLoadableType {
  return ['code', 'document', 'svg', 'mermaid'].includes(type);
}

// ==================== MIME 类型映射 ====================
// 与后端 app/core/constants/artifact_mappings.py 保持同步

/** 常见 MIME 类型到 ArtifactType 的映射 */
export const MIME_TO_ARTIFACT_TYPE: Record<string, ArtifactType> = {
  // 代码类型
  'text/javascript': 'code',
  'application/javascript': 'code',
  'text/typescript': 'code',
  'text/x-python': 'code',
  'text/x-java': 'code',
  'text/x-c': 'code',
  'text/x-cpp': 'code',
  'text/x-go': 'code',
  'text/x-rust': 'code',
  'application/json': 'code',
  'text/yaml': 'code',
  'text/x-yaml': 'code',
  'application/xml': 'code',
  'text/xml': 'code',
  'text/css': 'code',

  // 文档类型
  'text/plain': 'document',
  'text/markdown': 'document',
  'text/x-markdown': 'document',

  // HTML 类型
  'text/html': 'html',

  // 图片类型
  'image/png': 'image',
  'image/jpeg': 'image',
  'image/gif': 'image',
  'image/webp': 'image',
  'image/bmp': 'image',
  'image/x-icon': 'image',

  // 音频类型
  'audio/mpeg': 'audio',
  'audio/wav': 'audio',
  'audio/ogg': 'audio',
  'audio/flac': 'audio',
  'audio/mp4': 'audio',
  'audio/aac': 'audio',

  // SVG 类型
  'image/svg+xml': 'svg',

  // PDF 类型
  'application/pdf': 'pdf',

  // 二进制类型
  'application/octet-stream': 'binary',
};

/** 根据 MIME 类型推断 ArtifactType */
export function inferArtifactType(mimeType: string): ArtifactType {
  return MIME_TO_ARTIFACT_TYPE[mimeType] || 'binary';
}

// ==================== 文件扩展名映射 ====================
// 与后端 app/core/constants/artifact_mappings.py 保持同步
// 使用 'tsx'/'jsx' 而非 'typescript'/'javascript' 以获得更好的语法高亮

/** 文件扩展名到编程语言的映射（用于语法高亮） */
export const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  // JavaScript / TypeScript
  '.js': 'javascript',
  '.jsx': 'jsx',
  '.ts': 'typescript',
  '.tsx': 'tsx',
  // Python
  '.py': 'python',
  '.pyw': 'python',
  '.pyi': 'python',
  // Java / JVM
  '.java': 'java',
  '.kt': 'kotlin',
  '.kts': 'kotlin',
  '.scala': 'scala',
  '.groovy': 'groovy',
  // C / C++
  '.c': 'c',
  '.h': 'c',
  '.cpp': 'cpp',
  '.hpp': 'cpp',
  '.cc': 'cpp',
  '.cxx': 'cpp',
  // C#
  '.cs': 'csharp',
  // Go
  '.go': 'go',
  // Rust
  '.rs': 'rust',
  // Ruby
  '.rb': 'ruby',
  '.erb': 'erb',
  // PHP
  '.php': 'php',
  // Swift / Objective-C
  '.swift': 'swift',
  '.m': 'objectivec',
  '.mm': 'objectivec',
  // Shell
  '.sh': 'bash',
  '.bash': 'bash',
  '.zsh': 'bash',
  '.fish': 'fish',
  '.ps1': 'powershell',
  // SQL
  '.sql': 'sql',
  // Web
  '.html': 'html',
  '.htm': 'html',
  '.css': 'css',
  '.scss': 'scss',
  '.sass': 'sass',
  '.less': 'less',
  // Data formats
  '.json': 'json',
  '.jsonc': 'jsonc',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.xml': 'xml',
  '.toml': 'toml',
  '.ini': 'ini',
  '.conf': 'ini',
  // Markup
  '.md': 'markdown',
  '.mdx': 'mdx',
  '.rst': 'restructuredtext',
  '.tex': 'latex',
  // SVG / Diagrams
  '.svg': 'xml',
  '.mermaid': 'mermaid',
  '.mmd': 'mermaid',
  // Frontend frameworks
  '.vue': 'vue',
  '.svelte': 'svelte',
  // Other languages
  '.r': 'r',
  '.R': 'r',
  '.lua': 'lua',
  '.dart': 'dart',
  '.ex': 'elixir',
  '.exs': 'elixir',
  '.erl': 'erlang',
  '.hrl': 'erlang',
  '.hs': 'haskell',
  '.clj': 'clojure',
  '.cljs': 'clojure',
  '.fs': 'fsharp',
  '.fsx': 'fsharp',
  '.pl': 'perl',
  '.pm': 'perl',
  // Config files
  '.dockerfile': 'dockerfile',
  '.dockerignore': 'ignore',
  '.gitignore': 'ignore',
  '.env': 'dotenv',
  // GraphQL
  '.graphql': 'graphql',
  '.gql': 'graphql',
  // Protocol Buffers
  '.proto': 'protobuf',
};

/** 根据文件名推断编程语言 */
export function inferLanguage(filename: string): string | undefined {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase();
  return EXTENSION_TO_LANGUAGE[ext];
}

// ==================== 工具函数 ====================

/** 格式化文件大小 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/** 检查是否为文本类型（可以显示内容） */
export function isTextType(artifact: Artifact): boolean {
  const textTypes: ArtifactType[] = ['code', 'document', 'svg', 'mermaid'];
  return textTypes.includes(artifact.type);
}

/** 检查是否为媒体类型（图片/视频/音频等） */
export function isMediaType(artifact: Artifact): boolean {
  return (
    artifact.type === 'image' ||
    artifact.type === 'video' ||
    artifact.type === 'audio' ||
    artifact.content_type.startsWith('image/') ||
    artifact.content_type.startsWith('video/') ||
    artifact.content_type.startsWith('audio/')
  );
}
