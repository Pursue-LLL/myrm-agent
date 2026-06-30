/**
 * [OUTPUT]
 * ArtifactType, ArtifactVersion, Artifact.
 * 
 * [POS]
 * 聊天工件（代码/文档/媒体）契约。
 */

import type { ArtifactPublication } from '@/services/hosting';

export type { ArtifactPublication } from '@/services/hosting';
export type ArtifactType =
  | 'code'
  | 'document'
  | 'html'
  | 'pdf'
  | 'image'
  | 'video'
  | 'audio'
  | 'svg'
  | 'mermaid'
  | 'spreadsheet'
  | 'binary'
  | 'interactive_ui';

// 工件版本数据
export interface ArtifactVersion {
  versionId: string;
  versionNumber: number;
  content: string;
  createdAt: string;
  description?: string;
  source?: 'assistant' | 'user';
  originalArtifact?: Artifact;
}

// 工件数据
export interface Artifact {
  id: string; // 文件 ID
  filename: string; // 文件名
  type: ArtifactType; // 工件类型
  content_type: string; // MIME 类型
  size: number; // 文件大小（字节）
  preview_url: string; // 预览 URL
  download_url: string; // 下载 URL
  language?: string; // 编程语言（代码类型）
  created_at?: string; // 创建时间
  file_path?: string; // 本地文件路径（仅本地模式）
  // 版本历史
  versions?: ArtifactVersion[]; // 版本历史列表
  currentVersionIndex?: number; // 当前版本索引（默认为最新版本）
  latest_version_id?: string | null;
  publications?: ArtifactPublication[];
}
