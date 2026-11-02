import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * jsdom has no layout, so the phone first screen (390x844: composer and workspace card visible without scrolling,
 * nothing wrapping into extra rows) is pinned through the responsive tokens that produce it. Each entry was
 * measured in a real mobile emulation; removing a token brings the measured defect back.
 */
const read = (relativePath: string) => readFileSync(resolve(__dirname, relativePath), 'utf8');

const SWIPEABLE_ROWS: Array<{ file: string; row: string; tokens: string[] }> = [
  {
    file: '../agent-config-panel/FeaturedExpertChips.tsx',
    row: 'featured experts strip',
    tokens: ['overflow-x-auto', 'sm:flex-wrap', 'sm:overflow-visible'],
  },
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

  it('lays the workspace mode tabs out as three equal cells with top-aligned icons whose labels wrap or hyphenate, never clipped, below sm', () => {
    const source = read('../WorkModeTabs.tsx');

    expect(source).toContain('grid w-full grid-cols-3');
    expect(source.match(/mode: '(?:local|cloud|chat)'/g)).toHaveLength(3);
    expect(
      source.match(/'flex min-w-0 flex-col [^']*justify-start[^']*sm:flex-row[^']*sm:justify-center[^']*'/g),
    ).toHaveLength(1);
    expect(source).toContain("MODE_LABEL_CLASS = 'max-w-full text-balance hyphens-auto break-words text-center");
    expect(source.match(/<span className=\{MODE_LABEL_CLASS\}>/g)).toHaveLength(1);
  });

  it('halves the workspace mode tab side padding below 375px so each label gets 8px more width', () => {
    expect(read('../WorkModeTabs.tsx').match(/'flex min-w-0 flex-col [^']*max-\[375px\]:px-1[^']*'/g)).toHaveLength(1);
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

    expect(bannerStack?.[0]).toContain('<MemoryRecallDegradedBanner');
    expect(bannerStack?.[0]).toContain('<YoloModeBanner');
  });
});
