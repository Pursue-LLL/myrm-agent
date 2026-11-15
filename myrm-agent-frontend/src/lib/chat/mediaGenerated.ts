/**
 * [INPUT]
 * - @/lib/mediaReference::parseMediaReference (POS: `media://<id>` 媒体库引用的读写)
 *
 * [OUTPUT]
 * - MEDIA_GENERATED_METADATA_KEY: 消息 metadata 中登记生成媒体的键
 * - MediaGeneratedEntry / MediaTaskEntry / MediaStoredEntry / isMediaTaskEntry: 登记条目的类型与判别
 * - mediaGeneratedEntriesOf: 一次媒体工具结束事件登记的条目
 * - mergeMediaGeneratedEntries: 把新条目并入消息已有的登记（去重）
 * - readMediaGeneratedEntries: 读取消息 metadata 里已登记的条目（丢弃形状不合法的项）
 *
 * [POS]
 * 生成媒体卡片的唯一数据来源：卡片由工具返回的结构化结果驱动，不解析模型回复文字，所以回复为空、被截断或不是 JSON 时卡片照常出现。
 * 异步生成（图像 / 视频）登记任务，卡片跟随任务进度；同步生成（图像编辑、语音）登记已落库的媒体引用。
 * `status` / `list` 结果不登记。与服务端 `collect_media_generated` 解析同一份结果得到同一份条目，
 * 二者共同受 `shared/config/media_generation_contract.json` 约束。
 */

import { parseMediaReference } from '@/lib/mediaReference';

export const MEDIA_GENERATED_METADATA_KEY = 'media_generated';

export interface MediaTaskEntry {
  kind: 'image' | 'video';
  task_id: string;
}

export interface MediaStoredEntry {
  kind: 'image' | 'tts';
  media: string;
  model?: string;
  duration_seconds?: number;
}

export type MediaGeneratedEntry = MediaTaskEntry | MediaStoredEntry;

export function isMediaTaskEntry(entry: MediaGeneratedEntry): entry is MediaTaskEntry {
  return 'task_id' in entry;
}

type JsonObject = Record<string, unknown>;

const IMAGE_TOOL = 'image_tool';
const VIDEO_TOOL = 'video_tool';
const TTS_TOOL = 'tts_generate';

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function taskEntries(kind: MediaTaskEntry['kind'], result: JsonObject): MediaTaskEntry[] {
  if (!Array.isArray(result.tasks)) {
    return [];
  }
  const entries: MediaTaskEntry[] = [];
  for (const task of result.tasks) {
    const taskId = isObject(task) ? nonEmptyString(task.task_id) : undefined;
    if (taskId) {
      entries.push({ kind, task_id: taskId });
    }
  }
  return entries;
}

function storedEntry(kind: MediaStoredEntry['kind'], media: unknown, result: JsonObject): MediaStoredEntry | null {
  if (typeof media !== 'string' || parseMediaReference(media) === null) {
    return null;
  }
  const model = nonEmptyString(result.model);
  return model ? { kind, media, model } : { kind, media };
}

function imageEditEntries(result: JsonObject): MediaStoredEntry[] {
  if (!Array.isArray(result.images)) {
    return [];
  }
  const entries: MediaStoredEntry[] = [];
  for (const image of result.images) {
    const entry = isObject(image) ? storedEntry('image', image.url, result) : null;
    if (entry) {
      entries.push(entry);
    }
  }
  return entries;
}

function speechEntries(result: JsonObject): MediaStoredEntry[] {
  if (result.status !== 'success') {
    return [];
  }
  const entry = storedEntry('tts', result.audio_url, result);
  if (!entry) {
    return [];
  }
  const duration = finiteNumber(result.duration_seconds);
  return [duration === undefined ? entry : { ...entry, duration_seconds: duration }];
}

/** The entries one finished media tool call registers; any other tool, or a result of another shape, registers none. */
export function mediaGeneratedEntriesOf(toolName: string, result: unknown): MediaGeneratedEntry[] {
  if (!isObject(result)) {
    return [];
  }
  switch (toolName) {
    case TTS_TOOL:
      return speechEntries(result);
    case VIDEO_TOOL:
      return taskEntries('video', result);
    case IMAGE_TOOL: {
      const tasks = taskEntries('image', result);
      return tasks.length > 0 ? tasks : imageEditEntries(result);
    }
    default:
      return [];
  }
}

function parseStoredKind(kind: unknown): MediaStoredEntry['kind'] | undefined {
  return kind === 'image' || kind === 'tts' ? kind : undefined;
}

function parseEntry(raw: unknown): MediaGeneratedEntry | null {
  if (!isObject(raw)) {
    return null;
  }
  const taskId = nonEmptyString(raw.task_id);
  if (taskId) {
    return raw.kind === 'image' || raw.kind === 'video' ? { kind: raw.kind, task_id: taskId } : null;
  }
  const kind = parseStoredKind(raw.kind);
  const media = nonEmptyString(raw.media);
  if (!kind || !media || parseMediaReference(media) === null) {
    return null;
  }
  const model = nonEmptyString(raw.model);
  const duration = finiteNumber(raw.duration_seconds);
  return {
    kind,
    media,
    ...(model ? { model } : {}),
    ...(duration === undefined ? {} : { duration_seconds: duration }),
  };
}

export function readMediaGeneratedEntries(raw: unknown): MediaGeneratedEntry[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const entries: MediaGeneratedEntry[] = [];
  for (const item of raw) {
    const entry = parseEntry(item);
    if (entry) {
      entries.push(entry);
    }
  }
  return entries;
}

function entryIdentity(entry: MediaGeneratedEntry): string {
  return isMediaTaskEntry(entry)
    ? JSON.stringify([entry.kind, entry.task_id])
    : JSON.stringify([entry.kind, entry.media, entry.model ?? null, entry.duration_seconds ?? null]);
}

export function mergeMediaGeneratedEntries(prior: unknown, incoming: MediaGeneratedEntry[]): MediaGeneratedEntry[] {
  const merged = readMediaGeneratedEntries(prior);
  const seen = new Set(merged.map(entryIdentity));
  for (const entry of incoming) {
    const identity = entryIdentity(entry);
    if (!seen.has(identity)) {
      seen.add(identity);
      merged.push(entry);
    }
  }
  return merged;
}
