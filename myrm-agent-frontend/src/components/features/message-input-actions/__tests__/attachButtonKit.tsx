/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - @/store/useProviderStore (POS: 真实的 Provider store，用来配置模型能力)
 * - ../AttachButton (POS: 被测组件)
 *
 * [OUTPUT]
 * - kit: 提示、文件服务、上传控制器、图片整理、哈希、部署模式的替身句柄
 * - resetAttachKit: 恢复默认行为（浏览器环境、文件原样通过、哈希按文件名、上传全部成功）
 * - renderAttach: 渲染按钮，返回当前文件列表的读写口（模拟别处同时改动列表）
 * - settle / pickFiles: 让已能完成的步骤跑完；在文件输入框里选文件并等待
 * - makeFile / makeSizedFile: 构造原生 File，后者可声明大小
 * - configureModels: 配置默认模型及各模型的视觉 / 视频能力
 *
 * [POS]
 * AttachButton 行为测试的共享底座。必须先于 ../AttachButton 导入：vi.mock 在本模块求值时登记。
 * 文件服务、上传、哈希是边界，换成替身；能力判断、文件分类与转换都是真实的。
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { UploadOptions, UploadProgress } from '@/services/file';
import type { FileReference } from '@/services/file-service';
import type {
  CustomModelInfo,
  DefaultModelConfig,
  ModelSlot,
  SingleModelSelection,
} from '@/store/config/providerTypes';
import type { File as ChatFile } from '@/store/chat/types';
import useProviderStore from '@/store/useProviderStore';
import AttachButton from '../AttachButton';

const kit = vi.hoisted(() => ({
  /** Keys with their values appended, so tests can see what a message was filled with. */
  t: (key: string, values?: Record<string, string>) => (values ? `${key}|${Object.values(values).join(',')}` : key),
  toast: vi.fn<(options: { title: string; description?: string; duration?: number }) => void>(),
  visionToast: vi.fn<(kind: 'image' | 'video') => void>(),
  isTauri: vi.fn<() => boolean>(),
  selectFiles: vi.fn<() => Promise<FileReference[]>>(),
  uploadFiles:
    vi.fn<
      (
        files: File[],
        onProgress?: (progress: UploadProgress) => void,
        signal?: AbortSignal,
        options?: UploadOptions,
      ) => Promise<FileReference[]>
    >(),
  resetUploadController: vi.fn<() => void>(),
  uploadSignal: new AbortController().signal,
  admit: vi.fn<(files: File[]) => Promise<File[]>>(),
  hashOf: vi.fn<(file: File) => Promise<string>>(),
}));
export { kit };

vi.mock('next-intl', () => ({ useTranslations: () => kit.t }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: kit.toast }));
vi.mock('@/store/config/visionConfigGap', () => ({ showVisionNotConfiguredToast: kit.visionToast }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isTauriRuntime: kit.isTauri,
}));
vi.mock('@/services/file-service', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/file-service')>()),
  selectFiles: kit.selectFiles,
  getFileService: () => ({ uploadFiles: kit.uploadFiles }),
}));
vi.mock('@/services/uploadController', () => ({
  resetUploadController: kit.resetUploadController,
  getUploadSignal: () => kit.uploadSignal,
}));
vi.mock('@/lib/utils/imageAdmission', () => ({ admitAndCompressFiles: kit.admit }));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  computeFileHash: kit.hashOf,
}));

const extensionOf = (name: string) => name.split('.').pop() ?? '';

/** Boundaries behave: files pass through untouched, hashes follow the file name, every upload succeeds. */
export function resetAttachKit(): void {
  cleanup();
  vi.clearAllMocks();
  kit.isTauri.mockReturnValue(false);
  kit.admit.mockImplementation(async (files) => files);
  kit.hashOf.mockImplementation(async (file) => `hash:${file.name}`);
  kit.uploadFiles.mockImplementation(async (files) =>
    files.map((file) => ({
      id: `id:${file.name}`,
      fileName: file.name,
      fileExtension: extensionOf(file.name),
      fileType: 'uploaded' as const,
      fileUrl: `/uploads/${file.name}`,
    })),
  );
  useProviderStore.setState({ defaultModelConfig: undefined });
}

/** Lets every already-resolved step of a chain run, which can take several turns. */
export const settle = (): Promise<void> =>
  act(async () => void (await new Promise((resolve) => setTimeout(resolve, 0))));

/** Picks files in the browser's file input and waits for everything that can finish to finish. */
export async function pickFiles(input: HTMLInputElement, ...files: File[]): Promise<void> {
  fireEvent.change(input, { target: { files } });
  await settle();
}

export function makeFile(name: string): File {
  return new File(['content'], name);
}

export function makeSizedFile(name: string, bytes: number): File {
  const file = makeFile(name);
  Object.defineProperty(file, 'size', { value: bytes });
  return file;
}

export function chatFile(fileName: string, extra: Partial<ChatFile> = {}): ChatFile {
  return { fileName, fileExtension: extensionOf(fileName), fileType: 'uploaded', ...extra };
}

type SetFilesArgument = ChatFile[] | ((previous: ChatFile[]) => ChatFile[]);

/**
 * Renders the button. `list` is the attachment list as the rest of the composer sees it: it starts as `initial`,
 * `setFiles` applies plain and functional updates to it, and other code may change it while an upload is running.
 */
export function renderAttach(initial: ChatFile[] = []) {
  const list = { current: initial };
  const setFiles = vi.fn((update: SetFilesArgument) => {
    list.current = typeof update === 'function' ? update(list.current) : update;
  });
  render(
    <TooltipProvider>
      <AttachButton files={initial} setFiles={setFiles} />
    </TooltipProvider>,
  );
  return {
    list,
    setFiles,
    button: () => screen.getByRole('button', { name: 'attach' }),
    input: () => document.querySelector('input[type="file"]') as HTMLInputElement,
  };
}

const slot = (primary: SingleModelSelection | null, fallback: SingleModelSelection | null = null): ModelSlot => ({
  primary,
  fallback,
});

export const BASE_MODEL: SingleModelSelection = { providerId: 'base-provider', model: 'base-model' };
export const VISION_MODEL: SingleModelSelection = { providerId: 'vision-provider', model: 'vision-model' };
export const VIDEO_MODEL: SingleModelSelection = { providerId: 'video-provider', model: 'video-model' };

/** Configures the default models and says which models see images or take video; every other model sees neither. */
export function configureModels(options: {
  base?: SingleModelSelection | null;
  visionFallback?: SingleModelSelection | null;
  videoFallback?: SingleModelSelection | null;
  vision?: SingleModelSelection[];
  video?: SingleModelSelection[];
}): void {
  const { base = BASE_MODEL, visionFallback = null, videoFallback = null, vision = [], video = [] } = options;
  const same = (a: SingleModelSelection, providerId: string, model: string) =>
    a.providerId === providerId && a.model === model;
  const defaultModelConfig: DefaultModelConfig = {
    baseModel: slot(base),
    liteModel: slot(null),
    fastModeModel: null,
    routingConfig: null,
    visionFallbackModel: visionFallback ? slot(visionFallback) : null,
    videoFallbackModel: videoFallback ? slot(videoFallback) : null,
  };
  const getModelInfo = (providerId: string, model: string): CustomModelInfo => ({
    source: 'user',
    lastUpdated: '2026-01-01',
    supports_vision: vision.some((m) => same(m, providerId, model)),
    supports_video_input: video.some((m) => same(m, providerId, model)),
  });
  useProviderStore.setState({ defaultModelConfig, getModelInfo });
}
