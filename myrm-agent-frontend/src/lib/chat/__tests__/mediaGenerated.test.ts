import { describe, expect, it } from 'vitest';
import {
  isMediaTaskEntry,
  mediaGeneratedEntriesOf,
  mergeMediaGeneratedEntries,
  readMediaGeneratedEntries,
} from '../mediaGenerated';

const startedTasks = (...ids: string[]) => ({
  tasks: ids.map((task_id) => ({ task_id, task_type: 'image_generate', status: 'pending' })),
  message: 'Generation started',
});

describe('mediaGeneratedEntriesOf', () => {
  it('registers one image entry per started image task', () => {
    expect(mediaGeneratedEntriesOf('image_tool', startedTasks('img-1', 'img-2'))).toEqual([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'image', task_id: 'img-2' },
    ]);
  });

  it('registers the video task', () => {
    expect(mediaGeneratedEntriesOf('video_tool', startedTasks('vid-1'))).toEqual([{ kind: 'video', task_id: 'vid-1' }]);
  });

  it('registers the stored image of a synchronous edit with the model that made it', () => {
    const result = { images: [{ url: 'media://media_edit', mime_type: 'image/png' }], model: 'gpt-image-2.6-sunburst' };

    expect(mediaGeneratedEntriesOf('image_tool', result)).toEqual([
      { kind: 'image', media: 'media://media_edit', model: 'gpt-image-2.6-sunburst' },
    ]);
  });

  it('prefers started tasks over images when a result carries both', () => {
    const result = { ...startedTasks('img-1'), images: [{ url: 'media://media_x' }] };

    expect(mediaGeneratedEntriesOf('image_tool', result)).toEqual([{ kind: 'image', task_id: 'img-1' }]);
  });

  it('registers speech only for a successful result with a stored reference', () => {
    const success = {
      status: 'success',
      audio_url: 'media://media_speech',
      model: 'gpt-4o-mini-tts',
      duration_seconds: 3.2,
    };

    expect(mediaGeneratedEntriesOf('tts_generate', success)).toEqual([
      { kind: 'tts', media: 'media://media_speech', model: 'gpt-4o-mini-tts', duration_seconds: 3.2 },
    ]);
    expect(mediaGeneratedEntriesOf('tts_generate', { ...success, status: 'error' })).toEqual([]);
    expect(mediaGeneratedEntriesOf('tts_generate', { ...success, audio_url: 'https://cdn.example/a.mp3' })).toEqual([]);
    expect(mediaGeneratedEntriesOf('tts_generate', { status: 'success' })).toEqual([]);
  });

  it('leaves out optional fields it was not given', () => {
    expect(mediaGeneratedEntriesOf('tts_generate', { status: 'success', audio_url: 'media://m' })).toEqual([
      { kind: 'tts', media: 'media://m' },
    ]);
  });

  it('registers nothing for status, list, errors and other tools', () => {
    const status = { task_id: 'img-1', task_type: 'image_generate', status: 'succeeded', result: { images: [] } };

    expect(mediaGeneratedEntriesOf('image_tool', status)).toEqual([]);
    expect(mediaGeneratedEntriesOf('image_tool', { models: [], active_model: 'x' })).toEqual([]);
    expect(mediaGeneratedEntriesOf('image_tool', { error: 'prompt is required' })).toEqual([]);
    expect(mediaGeneratedEntriesOf('web_search', startedTasks('img-1'))).toEqual([]);
  });

  it('ignores tasks without an id and results that are not objects', () => {
    expect(
      mediaGeneratedEntriesOf('image_tool', { tasks: [{ task_id: '' }, { status: 'pending' }, null, 'x'] }),
    ).toEqual([]);
    expect(mediaGeneratedEntriesOf('image_tool', 'not json')).toEqual([]);
    expect(mediaGeneratedEntriesOf('image_tool', [startedTasks('img-1')])).toEqual([]);
    expect(mediaGeneratedEntriesOf('image_tool', null)).toEqual([]);
  });
});

describe('readMediaGeneratedEntries', () => {
  it('keeps well-formed entries and drops everything else', () => {
    const raw = [
      { kind: 'image', task_id: 'img-1' },
      { kind: 'video', task_id: 'vid-1' },
      { kind: 'image', media: 'media://m1', model: 'gpt-image-2.6-sunburst' },
      { kind: 'tts', media: 'media://m2', duration_seconds: 2 },
      { kind: 'tts', task_id: 'tts-1' },
      { kind: 'video', media: 'media://m3' },
      { kind: 'image', media: 'https://cdn.example/a.png' },
      { kind: 'image' },
      { task_id: 'img-2' },
      null,
      'text',
    ];

    expect(readMediaGeneratedEntries(raw)).toEqual([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'video', task_id: 'vid-1' },
      { kind: 'image', media: 'media://m1', model: 'gpt-image-2.6-sunburst' },
      { kind: 'tts', media: 'media://m2', duration_seconds: 2 },
    ]);
  });

  it.each([[undefined], [null], ['x'], [{ kind: 'image', task_id: 'a' }], [42]])('reads %j as no entries', (raw) => {
    expect(readMediaGeneratedEntries(raw)).toEqual([]);
  });
});

describe('mergeMediaGeneratedEntries', () => {
  it('appends new entries after the registered ones', () => {
    const prior = [{ kind: 'image', task_id: 'img-1' }];

    expect(mergeMediaGeneratedEntries(prior, [{ kind: 'video', task_id: 'vid-1' }])).toEqual([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'video', task_id: 'vid-1' },
    ]);
  });

  it('does not register the same entry twice, even within one call', () => {
    const merged = mergeMediaGeneratedEntries(
      [{ kind: 'image', task_id: 'img-1' }],
      [
        { kind: 'image', task_id: 'img-1' },
        { kind: 'image', media: 'media://m', model: 'x' },
        { kind: 'image', media: 'media://m', model: 'x' },
      ],
    );

    expect(merged).toEqual([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'image', media: 'media://m', model: 'x' },
    ]);
  });

  it('treats the same media reported with a different model as a different entry', () => {
    expect(
      mergeMediaGeneratedEntries(
        [{ kind: 'image', media: 'media://m', model: 'a' }],
        [{ kind: 'image', media: 'media://m', model: 'b' }],
      ),
    ).toHaveLength(2);
  });

  it('starts from an empty list when nothing valid was registered before', () => {
    expect(mergeMediaGeneratedEntries('garbage', [{ kind: 'image', task_id: 'img-1' }])).toEqual([
      { kind: 'image', task_id: 'img-1' },
    ]);
  });
});

describe('isMediaTaskEntry', () => {
  it('tells task entries from stored-media entries', () => {
    expect(isMediaTaskEntry({ kind: 'image', task_id: 'img-1' })).toBe(true);
    expect(isMediaTaskEntry({ kind: 'image', media: 'media://m' })).toBe(false);
  });
});
