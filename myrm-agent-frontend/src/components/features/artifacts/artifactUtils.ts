import {
  File01Icon,
  File02Icon,
  Globe02Icon,
  Image01Icon,
  FileAttachmentIcon,
  GitBranchIcon,
  CodeCircleIcon,
  CodeSquareIcon,
  ComputerTerminal01Icon,
  Database01Icon,
  PaintBoardIcon,
  Video01Icon,
  HeadphonesIcon,
  Table02Icon,
} from 'hugeicons-react';
import { getApiUrl } from '@/lib/api';
import { Artifact, ArtifactPublication, ArtifactType } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { formatFileSize as formatFileSizeUtil, isPreviewable, needsContentLoad, inferLanguage } from '@/types/artifact';

/** Artifact 类型到图标的映射（基础类型） */
const ARTIFACT_ICON_MAP: Record<ArtifactType, React.ElementType> = {
  code: CodeCircleIcon,
  document: File01Icon,
  html: Globe02Icon,
  pdf: FileAttachmentIcon,
  image: Image01Icon,
  video: Video01Icon,
  audio: HeadphonesIcon,
  svg: Image01Icon,
  mermaid: GitBranchIcon,
  spreadsheet: Table02Icon,
  binary: File02Icon,
  interactive_ui: File01Icon,
};

/** 文件扩展名到图标的精确映射 */
const EXTENSION_ICON_MAP: Record<string, React.ElementType> = {
  // JavaScript/TypeScript 系列
  js: CodeSquareIcon,
  jsx: CodeSquareIcon,
  ts: CodeCircleIcon,
  tsx: CodeCircleIcon,
  mjs: CodeSquareIcon,
  cjs: CodeSquareIcon,

  // Python
  py: CodeSquareIcon,
  pyw: CodeSquareIcon,
  pyi: CodeSquareIcon,

  // Web 相关
  html: Globe02Icon,
  htm: Globe02Icon,
  css: PaintBoardIcon,
  scss: PaintBoardIcon,
  sass: PaintBoardIcon,
  less: PaintBoardIcon,

  // 数据格式
  json: CodeSquareIcon,
  yaml: CodeSquareIcon,
  yml: CodeSquareIcon,
  xml: CodeCircleIcon,
  toml: CodeSquareIcon,

  // Shell/Terminal
  sh: ComputerTerminal01Icon,
  bash: ComputerTerminal01Icon,
  zsh: ComputerTerminal01Icon,
  fish: ComputerTerminal01Icon,
  ps1: ComputerTerminal01Icon,
  bat: ComputerTerminal01Icon,
  cmd: ComputerTerminal01Icon,

  // 数据库
  sql: Database01Icon,

  // 文档
  md: File01Icon,
  mdx: File01Icon,
  txt: File01Icon,
  rst: File01Icon,

  // 图片
  svg: Image01Icon,
  png: Image01Icon,
  jpg: Image01Icon,
  jpeg: Image01Icon,
  gif: Image01Icon,
  webp: Image01Icon,
  ico: Image01Icon,

  // 音频
  mp3: HeadphonesIcon,
  wav: HeadphonesIcon,
  ogg: HeadphonesIcon,
  flac: HeadphonesIcon,
  m4a: HeadphonesIcon,
  aac: HeadphonesIcon,

  // 图表
  mermaid: GitBranchIcon,
  mmd: GitBranchIcon,

  // 配置文件
  env: CodeSquareIcon,
  ini: CodeSquareIcon,
  conf: CodeSquareIcon,

  // 其他代码
  go: CodeCircleIcon,
  rs: CodeCircleIcon,
  rb: CodeCircleIcon,
  java: CodeCircleIcon,
  kt: CodeCircleIcon,
  swift: CodeCircleIcon,
  c: CodeCircleIcon,
  cpp: CodeCircleIcon,
  h: CodeCircleIcon,
  hpp: CodeCircleIcon,
  cs: CodeCircleIcon,
  php: CodeCircleIcon,
  r: CodeCircleIcon,
  scala: CodeCircleIcon,
  lua: CodeCircleIcon,
  dart: CodeCircleIcon,
  vue: CodeCircleIcon,
  svelte: CodeCircleIcon,
};

/** 根据文件名获取扩展名 */
function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  if (lastDot === -1 || lastDot === filename.length - 1) return '';
  return filename.slice(lastDot + 1).toLowerCase();
}

/** 根据工件类型和文件名获取图标（优先使用扩展名精确匹配） */
export function getArtifactIcon(type: ArtifactType, filename?: string): React.ElementType {
  // 优先根据文件扩展名获取精确图标
  if (filename) {
    const ext = getFileExtension(filename);
    if (ext && EXTENSION_ICON_MAP[ext]) {
      return EXTENSION_ICON_MAP[ext];
    }
  }
  // 回退到类型映射
  return ARTIFACT_ICON_MAP[type] || File02Icon;
}

/** 格式化文件大小 */
export function formatBytes(bytes: number): string {
  return formatFileSizeUtil(bytes);
}

/** 检查 Artifact 是否可预览 */
export { isPreviewable, needsContentLoad, inferLanguage };

/** 获取语言显示名称 */
export function getLanguageDisplayName(language: string | undefined): string {
  if (!language) return 'Plain Text';

  const languageMap: Record<string, string> = {
    js: 'JavaScript',
    ts: 'TypeScript',
    jsx: 'React JSX',
    tsx: 'React TSX',
    py: 'Python',
    rb: 'Ruby',
    go: 'Go',
    rs: 'Rust',
    java: 'Java',
    cpp: 'C++',
    c: 'C',
    cs: 'C#',
    php: 'PHP',
    swift: 'Swift',
    kt: 'Kotlin',
    scala: 'Scala',
    sql: 'SQL',
    html: 'HTML',
    css: 'CSS',
    scss: 'SCSS',
    less: 'Less',
    json: 'JSON',
    yaml: 'YAML',
    xml: 'XML',
    md: 'Markdown',
    sh: 'Shell',
    bash: 'Bash',
    zsh: 'Zsh',
    dockerfile: 'Dockerfile',
  };

  return languageMap[language.toLowerCase()] || language.toUpperCase();
}

/** 判断是否为可渲染的 HTML 类型 */
export function isRenderableHtml(contentType: string): boolean {
  return contentType.includes('text/html') || contentType.includes('application/xhtml');
}

/** 判断是否为 SVG 类型 */
export function isSvgType(contentType: string, filename: string): boolean {
  return contentType.includes('image/svg+xml') || filename.endsWith('.svg');
}

/** 判断是否为 Mermaid 图表类型 */
export function isMermaidType(contentType: string, filename: string): boolean {
  return contentType.includes('text/mermaid') || filename.endsWith('.mermaid') || filename.endsWith('.mmd');
}

/**
 * 获取下载文件名
 * 对于 .skill 文件，自动添加 .zip 后缀以帮助用户理解文件格式
 *
 * @param filename - 原始文件名
 * @returns 处理后的下载文件名
 *
 * @example
 * getDownloadFilename('hello-world.skill') // 'hello-world.skill.zip'
 * getDownloadFilename('document.pdf') // 'document.pdf'
 */
export function getDownloadFilename(filename: string): string {
  // 如果文件名以 .skill 结尾，添加 .zip 后缀
  // 这样用户一眼就能看出这是一个 ZIP 压缩文件
  if (filename.endsWith('.skill')) {
    return `${filename}.zip`;
  }
  return filename;
}

/** Sync deployment fields on matching chat message artifacts. */
export function isPublicationStale(
  publication: { publication_status?: string | null; publication_version_id?: string | null },
  latestVersionId?: string | null,
): boolean {
  return Boolean(
    publication.publication_status === 'READY' &&
      publication.publication_version_id &&
      latestVersionId &&
      publication.publication_version_id !== latestVersionId,
  );
}

export function patchArtifactPublicationsInChat(artifactId: string, publications: ArtifactPublication[]): void {
  useChatStore.getState().updateMessages((state) => {
    for (const message of state.messages) {
      if (!message.artifacts?.length) {
        continue;
      }
      const index = message.artifacts.findIndex((item) => item.id === artifactId);
      if (index >= 0) {
        message.artifacts[index] = { ...message.artifacts[index], publications };
      }
    }
  });
}

export function patchArtifactDeploymentInChat(artifactId: string, update: Partial<Artifact>): void {
  useChatStore.getState().updateMessages((state) => {
    for (const message of state.messages) {
      if (!message.artifacts?.length) {
        continue;
      }
      const index = message.artifacts.findIndex((item) => item.id === artifactId);
      if (index >= 0) {
        message.artifacts[index] = { ...message.artifacts[index], ...update };
      }
    }
  });
}

export function isDeploymentStale(artifact: Artifact): boolean {
  const pubs = artifact.publications ?? [];
  if (!artifact.latest_version_id) {
    return false;
  }
  return pubs.some((pub) => isPublicationStale(pub, artifact.latest_version_id));
}

const DEPLOY_CANDIDATE_TYPES: ReadonlySet<ArtifactType> = new Set(['html', 'code']);

export function isDeployCandidateArtifactType(type: ArtifactType): boolean {
  return DEPLOY_CANDIDATE_TYPES.has(type);
}

export interface ArtifactDeployPreflight {
  deployable: boolean;
  reason: string;
  message: string;
  hint: string | null;
}

export async function fetchArtifactDeployPreflight(
  artifactId: string,
): Promise<ArtifactDeployPreflight | null> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifactId}/publish/preflight`));
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as ArtifactDeployPreflight;
}

const SHARE_PREVIEW_SUFFIXES = ['.html', '.htm', '.pdf', '.md', '.markdown', '.txt'] as const;

export function isSharePreviewableArtifact(artifact: Artifact): boolean {
  const lower = artifact.filename.toLowerCase();
  if (SHARE_PREVIEW_SUFFIXES.some((suffix) => lower.endsWith(suffix))) {
    return true;
  }
  return artifact.type === 'html' || artifact.type === 'pdf' || artifact.type === 'document';
}

export interface ArtifactSharePreviewResult {
  token: string;
  share_path: string;
  expires_at: number;
}

export function buildPublicArtifactShareUrl(sharePath: string): string {
  const apiBase = getApiUrl('');
  const backendOrigin = apiBase.replace(/\/api\/v1\/?$/, '');
  return `${backendOrigin}${sharePath}`;
}

export async function createArtifactSharePreview(
  artifactId: string,
  artifactType?: string,
): Promise<ArtifactSharePreviewResult> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifactId}/share-preview`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ttl_days: 7,
      ...(artifactType ? { artifact_type: artifactType } : {}),
    }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Failed to create share link');
  }
  return (await response.json()) as ArtifactSharePreviewResult;
}

/** Safe hostname extraction for deployment URL labels. */
export function deploymentHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
