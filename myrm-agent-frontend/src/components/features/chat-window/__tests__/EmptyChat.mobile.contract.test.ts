import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * jsdom has no layout, so the phone first screen (390x844: composer and its workspace row visible without
 * scrolling, nothing wrapping into extra rows) is pinned through the responsive tokens that produce it. Each
 * entry was measured in a real mobile emulation; removing a token brings the measured defect back.
 */
const read = (relativePath: string) => readFileSync(resolve(__dirname, relativePath), 'utf8');

const SWIPEABLE_ROWS: Array<{ file: string; row: string; tokens: string[] }> = [
  {
    file: '../SamplePrompts.tsx',
    row: 'time-slot pills and prompt cards',
    tokens: ['overflow-x-auto', 'sm:flex-wrap', 'snap-x', 'sm:grid', 'lg:grid-cols-4'],
  },
];

describe('empty chat phone first-screen contract', () => {
  it.each(SWIPEABLE_ROWS)('keeps the $row on one swipeable row below the sm breakpoint', ({ file, tokens }) => {
    const source = read(file);

    expect(tokens.filter((token) => !source.includes(token))).toEqual([]);
  });

  it('keeps the featured experts strip on one swipeable row at every width, so its placeholder is the same box', () => {
    const source = read('../agent-config-panel/FeaturedExpertChips.tsx');

    expect(source).toContain('overflow-x-auto');
    // A wrapping row would make the strip's height depend on the chip names.
    expect(source).not.toContain('flex-wrap');
  });

  it('keeps the workspace row on one line: the path truncates instead of pushing the chevron out', () => {
    const source = read('../WorkspaceDirPicker.tsx');

    expect(source).toContain("'group mt-2 flex min-w-0 items-center gap-2 rounded-xl border px-3 py-1.5");
    expect(source).toContain("'w-fit max-w-full border-primary/25 bg-primary/5");
    expect(source).toContain("'w-full border-dashed border-border bg-muted/40");
    expect(source).toContain('className="min-w-0 flex-1 truncate font-medium"');
    expect(source).toContain('className="h-3.5 w-3.5 shrink-0 opacity-50');
  });

  it('renders the workspace row under the composer textarea, so phones do not depend on the desktop-only toolbar', () => {
    const composer = read('../MessageInput.tsx');
    const pickerIndex = composer.indexOf('{!hideChatWorkspacePicker && <WorkspaceDirPicker />}');
    const actionBarIndex = composer.indexOf('{/* 操作栏 */}');

    expect(pickerIndex).toBeGreaterThan(0);
    expect(pickerIndex).toBeLessThan(actionBarIndex);
    // One render site: the desktop toolbar must not hold a second copy.
    expect(composer.match(/<WorkspaceDirPicker \/>/g)).toHaveLength(1);
  });

  it('renders the composer text at 16px on phones so iOS Safari does not zoom the page on focus', () => {
    const textarea = read('../MessageInput.tsx').match(/<TextareaAutosize[\s\S]*?\/>/)?.[0] ?? '';

    expect(textarea).toContain('text-base sm:text-sm');
  });

  it('keeps the viewport-relative top gap at the phone value until the sm breakpoint', () => {
    expect(read('../EmptyChat.tsx')).toContain('pt-[8vh] sm:pt-[20vh]');
  });

  it('keeps the system banners clear of the sidebar toggle that AppLayout floats at the top-left', () => {
    const emptyBranch = read('../ChatWindow.tsx').split('<EmptyChat />')[0] ?? '';
    const bannerStack = emptyBranch.match(
      /<div className="max-lg:pl-12">[\s\S]*<\/div>\s*<div className="flex h-full w-full">/,
    );

    expect(bannerStack?.[0]).toContain('<EStopBanner');
    expect(bannerStack?.[0]).toContain('<YoloModeBanner');
  });
});
