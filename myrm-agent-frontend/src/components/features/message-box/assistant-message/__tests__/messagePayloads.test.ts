import { describe, expect, it } from 'vitest';

import type { McpAppView, Message, ProgressItem, ToolImageOutput } from '@/store/chat/types';
import {
  closeUnbalancedReasoningTags,
  parseAsyncTaskResponse,
  parseTtsAudioResponse,
  readCronJobResult,
  readKanbanTasksCreated,
  readMcpApps,
  readSessionRecording,
  readToolImages,
  resolveProgressSteps,
} from '../messagePayloads';

function message(extra: Partial<Message> = {}): Message {
  return {
    messageId: 'a1',
    chatId: 'chat-1',
    role: 'assistant',
    content: '',
    createdAt: new Date('2026-11-09T00:00:00.000Z'),
    ...extra,
  };
}

const malformed = <T>(value: unknown): T => value as T;

describe('closeUnbalancedReasoningTags', () => {
  it.each(['think', 'thinking', 'thought', 'antthinking', 'reasoning', 'REASONING_SCRATCHPAD'])(
    'closes an open <%s> block',
    (tag) => {
      expect(closeUnbalancedReasoningTags(`before <${tag}>still thinking`)).toBe(
        `before <${tag}>still thinking</${tag}> <a> </a>`,
      );
    },
  );

  it.each(['', 'plain answer', 'a < b and c > d', '<think>done</think> answer', '</think>x</think>'])(
    'leaves %j as it is',
    (content) => {
      expect(closeUnbalancedReasoningTags(content)).toBe(content);
    },
  );

  it('counts tags regardless of case and closes with the canonical name', () => {
    expect(closeUnbalancedReasoningTags('<THINK>x')).toBe('<THINK>x</think> <a> </a>');
  });

  it('closes a block opened more often than it was closed exactly once', () => {
    expect(closeUnbalancedReasoningTags('<think>a<think>b</think>')).toBe('<think>a<think>b</think></think> <a> </a>');
  });

  it('closes every open kind, in a fixed order', () => {
    expect(closeUnbalancedReasoningTags('<reasoning>a<think>b')).toBe(
      '<reasoning>a<think>b</think> <a> </a></reasoning> <a> </a>',
    );
  });
});

describe('parseAsyncTaskResponse', () => {
  it.each([
    [
      'an image task',
      '{"task_id":"t-1","task_type":"image_generate"}',
      { task_id: 't-1', task_type: 'image_generate' },
    ],
    ['a task without a type', '{"task_id":"t-2"}', { task_id: 't-2' }],
  ])('reads %s', (_name, content, expected) => {
    expect(parseAsyncTaskResponse(content)).toEqual(expected);
  });

  it.each(['{"task_id":""}', '{"task_id":5}', '{}', 'null', '[1]', '"task_id"', '42', '{oops', '', 'plain answer'])(
    'is not a task reply: %j',
    (content) => {
      expect(parseAsyncTaskResponse(content)).toBeNull();
    },
  );
});

describe('parseTtsAudioResponse', () => {
  it('reads a successful reply with its optional fields', () => {
    const content = '{"status":"success","audio_url":"/a.mp3","model":"tts-1","duration_seconds":3}';

    expect(parseTtsAudioResponse(content)).toEqual({
      status: 'success',
      audio_url: '/a.mp3',
      model: 'tts-1',
      duration_seconds: 3,
    });
  });

  it('accepts an empty audio url', () => {
    expect(parseTtsAudioResponse('{"status":"success","audio_url":""}')).toEqual({ status: 'success', audio_url: '' });
  });

  it.each([
    '{"status":"error","audio_url":"/a.mp3"}',
    '{"status":"success"}',
    '{"status":"success","audio_url":5}',
    'null',
    '[1]',
    '{oops',
    '',
  ])('is not a successful reply: %j', (content) => {
    expect(parseTtsAudioResponse(content)).toBeNull();
  });
});

describe('readSessionRecording', () => {
  const recording = { filename: 'r.webm', preview_url: '/r.webm', content_type: 'video/webm' };

  it('returns a complete recording as it is', () => {
    expect(readSessionRecording(message({ sessionRecording: recording }))).toBe(recording);
  });

  it.each([
    ['absent', undefined],
    ['a non-object', 'r.webm'],
    ['a file name that is not text', { filename: 5, preview_url: '/r' }],
    ['no preview url', { filename: 'r' }],
  ])('ignores a recording that is %s', (_name, value) => {
    expect(
      readSessionRecording(message({ sessionRecording: malformed<Message['sessionRecording']>(value) })),
    ).toBeNull();
  });
});

describe('readToolImages / readMcpApps', () => {
  it('pass an array through untouched', () => {
    const images = [malformed<ToolImageOutput>({ url: '/i.png' })];
    const apps = [malformed<McpAppView>({ id: 'app' })];

    expect(readToolImages(message({ toolImages: images }))).toBe(images);
    expect(readMcpApps(message({ mcpApps: apps }))).toBe(apps);
  });

  it.each([undefined, 'oops', {}, null])('fall back to nothing for %j', (value) => {
    expect(readToolImages(message({ toolImages: malformed<Message['toolImages']>(value) }))).toEqual([]);
    expect(readMcpApps(message({ mcpApps: malformed<Message['mcpApps']>(value) }))).toEqual([]);
  });
});

describe('readCronJobResult', () => {
  it('returns the job result kept in the metadata', () => {
    const result = { job_id: 'j1' };

    expect(readCronJobResult(message({ metadata: { cron_job_result: result } }))).toBe(result);
  });

  it.each([
    ['no metadata', undefined],
    ['no result', { other: 1 }],
    ['a null result', { cron_job_result: null }],
  ])('has nothing for %s', (_name, metadata) => {
    expect(readCronJobResult(message({ metadata }))).toBeNull();
  });
});

describe('readKanbanTasksCreated', () => {
  const task = { task_id: 'k1', title: 'Task', board_id: 'b1' };

  it('keeps only complete task records', () => {
    const metadata = { kanban_tasks_created: [task, { task_id: 'x' }, null, 'text', { ...task, task_id: 'k2' }] };

    expect(readKanbanTasksCreated(message({ metadata }))).toEqual([task, { ...task, task_id: 'k2' }]);
  });

  it.each([
    ['no metadata', undefined],
    ['no tasks', { other: 1 }],
    ['tasks that are not a list', { kanban_tasks_created: 'k1' }],
  ])('has nothing for %s', (_name, metadata) => {
    expect(readKanbanTasksCreated(message({ metadata }))).toEqual([]);
  });
});

describe('resolveProgressSteps', () => {
  const own: ProgressItem[] = [{ step_key: 'searching' }];
  const persisted: ProgressItem[] = [{ step_key: 'persisted' }];

  it('prefers the steps of the message', () => {
    expect(resolveProgressSteps(message({ progressSteps: own, metadata: { progressSteps: persisted } }))).toBe(own);
  });

  it('falls back to the copy in the metadata when the message has no steps', () => {
    expect(resolveProgressSteps(message({ progressSteps: [], metadata: { progressSteps: persisted } }))).toBe(
      persisted,
    );
  });

  it.each([
    ['no steps anywhere', undefined],
    ['metadata steps that are not a list', { progressSteps: 'nope' }],
  ])('is empty for %s', (_name, metadata) => {
    expect(resolveProgressSteps(message({ metadata }))).toEqual([]);
  });
});
