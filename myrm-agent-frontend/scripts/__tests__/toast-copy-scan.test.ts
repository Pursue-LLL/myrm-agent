// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findToastCopySites } from '../toast-copy-scan';

const texts = (source: string, fileName?: string): string[] =>
  findToastCopySites(source, fileName).map((site) => site.text);

describe('findToastCopySites: toast messages', () => {
  it('flags literal copy passed to toast and every message-bearing method', () => {
    expect(texts(`toast('Saved the file')`)).toEqual(['Saved the file']);
    expect(texts(`toast.success('已复制到剪贴板')`)).toEqual(['已复制到剪贴板']);
    expect(texts(`toast.error('Failed to save')`)).toEqual(['Failed to save']);
    expect(texts(`toast.warning('Low disk space')`)).toEqual(['Low disk space']);
    expect(texts(`toast.info('Syncing now')`)).toEqual(['Syncing now']);
    expect(texts(`toast.message('Heads up')`)).toEqual(['Heads up']);
    expect(texts(`toast.loading('Uploading')`)).toEqual(['Uploading']);
  });

  it('treats a single word as copy because a toast message is always user-facing', () => {
    expect(texts(`toast.success('Copied')`)).toEqual(['Copied']);
    expect(texts(`toast.error('失败')`)).toEqual(['失败']);
  });

  it('flags the static words of a template literal and ignores one that has no words', () => {
    expect(texts('toast.info(`Cache reset: ${reason}`)')).toEqual(['Cache reset:']);
    expect(texts('toast.success(`${count}`)')).toEqual([]);
  });

  it('flags the literal half of a fallback, ternary or nullish expression', () => {
    expect(texts(`toast.error(err.message || 'Download failed')`)).toEqual(['Download failed']);
    expect(texts(`toast.error(err instanceof Error ? err.message : 'Installation failed')`)).toEqual([
      'Installation failed',
    ]);
    expect(texts(`toast.error(msg ?? 'Plan revision error')`)).toEqual(['Plan revision error']);
    expect(texts(`toast.error(a ? 'First text' : 'Second text')`)).toEqual(['First text', 'Second text']);
  });

  it('flags the dead literal fallback behind a translator call, because t() never returns an empty value', () => {
    expect(texts(`toast.success(t('saved') || 'Saved successfully')`)).toEqual(['Saved successfully']);
    expect(texts(`toast.error(result.reason || t('replanFailed') || 'Plan revision failed')`)).toEqual([
      'Plan revision failed',
    ]);
  });

  it('flags a fallback nested in a `${}` span of a template message', () => {
    expect(texts("toast.info(`${t('a') || 'Eco mode'}: ${n}`)")).toEqual(['Eco mode']);
  });

  it('accepts messages that come from translations or variables', () => {
    expect(texts(`toast.error(t('saveFailed'))`)).toEqual([]);
    expect(texts(`toast.error(err.message || t('saveFailed'))`)).toEqual([]);
    expect(texts(`toast.error(message)`)).toEqual([]);
    expect(texts(`toast.success(t('saved'), { duration: 3000 })`)).toEqual([]);
  });

  it('ignores toast members that carry no message and unrelated callees', () => {
    expect(texts(`toast.dismiss('toast-id-42')`)).toEqual([]);
    expect(texts(`toast.promise(task, { loading: t('a'), success: t('b'), error: t('c') })`)).toEqual([]);
    expect(texts(`notify('Failed to save')`)).toEqual([]);
    expect(texts(`logger.error('Failed to save')`)).toEqual([]);
    expect(texts(`api.toast('Failed to save')`)).toEqual([]);
    expect(texts(`const label = t('title') || 'Default title'`)).toEqual([]);
  });
});

describe('findToastCopySites: toast options', () => {
  it('flags the object form title and description', () => {
    expect(
      texts(`toast({ title: 'Export finished', description: 'The file is ready', variant: 'destructive' })`),
    ).toEqual(['Export finished', 'The file is ready']);
    expect(texts(`toast({ title: t('done'), description: t('doneHint') })`)).toEqual([]);
  });

  it('flags a literal description and action label in the options argument', () => {
    expect(texts(`toast.error(t('failed'), { description: 'Check the network' })`)).toEqual(['Check the network']);
    expect(texts(`toast.error(t('failed'), { description: err.message || 'Try again later' })`)).toEqual([
      'Try again later',
    ]);
    expect(texts(`toast.info(t('undo'), { action: { label: 'Undo', onClick } })`)).toEqual(['Undo']);
    expect(texts(`toast.info(t('undo'), { cancel: { label: 'Dismiss', onClick } })`)).toEqual(['Dismiss']);
    expect(texts(`toast.info(t('undo'), { action: { label: t('undoLabel'), onClick } })`)).toEqual([]);
  });

  it('flags the literal states of toast.promise', () => {
    expect(texts(`toast.promise(task, { loading: 'Saving', success: t('b'), error: 'Save failed' })`)).toEqual([
      'Saving',
      'Save failed',
    ]);
  });
});

describe('findToastCopySites: toast receivers', () => {
  it('follows `import { toast as alias }` and the pushToast forwarding object', () => {
    const aliased = `import { toast as appToast } from '@/lib/utils/toast';\nappToast.error('Failed to save');`;
    expect(texts(aliased)).toEqual(['Failed to save']);
    expect(texts(`pushToast.warning(t('x') || 'Budget exceeded', { description: 'Low balance' })`)).toEqual([
      'Budget exceeded',
      'Low balance',
    ]);
  });

  it('does not treat an unrelated alias as a toast', () => {
    const other = `import { notify as appToast } from './notify';\nappToast.error('Failed to save');`;
    expect(texts(other)).toEqual([]);
  });
});

describe('findToastCopySites: positions and file kinds', () => {
  it('reports the 1-based line of the literal', () => {
    const source = ['function save() {', '  toast.error(', `    'Failed to save'`, '  );', '}'].join('\n');
    expect(findToastCopySites(source)).toEqual([{ line: 3, text: 'Failed to save' }]);
  });

  it('parses .ts files that contain angle-bracket generics', () => {
    const source = `const value = <string>input;\ntoast.error('Failed to save');`;
    expect(texts(source, 'store.ts')).toEqual(['Failed to save']);
  });

  it('parses .tsx files that contain JSX', () => {
    const source = `const view = <button onClick={() => toast.error('Failed to save')} />;`;
    expect(texts(source, 'view.tsx')).toEqual(['Failed to save']);
  });
});
