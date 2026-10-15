/**
 * [INPUT]
 * src 下全部非测试的 .tsx 源文件。
 * [OUTPUT]
 * Vitest: 每个 @dnd-kit 拖拽站点都接入了本地化的屏幕阅读器文案层。
 * [POS]
 * 新增拖拽站点时的防遗漏守卫：dnd-kit 自带的说明与播报只有英文且直接念内部 id，
 * 漏接的站点会在中文界面里读出英文和 id。
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = join(process.cwd(), 'src');

function sourceFiles(): { path: string; text: string }[] {
  return readdirSync(SRC_ROOT, { recursive: true, encoding: 'utf8' })
    .filter((file) => file.endsWith('.tsx') && !file.includes('__tests__') && !file.includes('.test.'))
    .map((file) => ({
      path: relative(process.cwd(), join(SRC_ROOT, file)),
      text: readFileSync(join(SRC_ROOT, file), 'utf8'),
    }));
}

/** 每个 `<DndContext` 开标签起的一段文本，属性（含 accessibility）都在其中。 */
function dndContextOpeningTags(text: string): string[] {
  return [...text.matchAll(/<DndContext\b/g)].map((match) => text.slice(match.index, match.index + 400));
}

const files = sourceFiles();
const withDndContext = files.filter((file) => file.text.includes('<DndContext'));
const withDragItems = files.filter((file) => /\b(useSortable|useDraggable)\(/.test(file.text));

describe('dnd-kit accessibility coverage', () => {
  it('finds the known drag-and-drop sites, so the scan cannot silently go empty', () => {
    expect(withDndContext.length).toBeGreaterThanOrEqual(5);
    expect(withDragItems.length).toBeGreaterThanOrEqual(5);
  });

  it.each(withDndContext.map((file) => [file.path, file.text]))(
    '%s passes localized accessibility to every DndContext',
    (_path, text) => {
      for (const openingTag of dndContextOpeningTags(text)) {
        expect(openingTag).toContain('accessibility={');
      }
    },
  );

  it.each(withDragItems.map((file) => [file.path, file.text]))(
    '%s localizes the role description of its drag items',
    (_path, text) => {
      expect(text).toContain('useDndItemLabels');
      expect(text).toMatch(/attributes:\s*\{\s*roleDescription\s*\}/);
    },
  );
});
