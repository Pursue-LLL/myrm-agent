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

/**
 * Every control on the phone first screen reaches a 44px touch target while its drawn size stays put. The figures
 * come from hit-testing (`elementFromPoint`) a 390x844 touch emulation; each entry pins the tokens that produce them.
 * An absolutely positioned box is offset from the padding edge, so bordered controls need 1px more per side.
 */
const TOUCH_TARGETS: Array<{ file: string; control: string; tokens: string[] }> = [
  {
    file: '../../../layout/AppLayout.tsx',
    control: 'sidebar toggle',
    tokens: ['after:absolute', 'after:-inset-[5px]'],
  },
  {
    file: '../WorkspaceDirPicker.tsx',
    control: 'workspace row',
    tokens: ['max-sm:after:absolute', 'max-sm:after:inset-x-0', 'max-sm:after:-inset-y-[8px]'],
  },
  {
    file: '../../message-input-actions/SearchModeSelector.tsx',
    control: 'Fast / Agent switch',
    tokens: ['max-sm:min-w-11', 'max-sm:after:absolute', 'max-sm:after:inset-x-0', 'max-sm:after:-inset-y-1.5'],
  },
  {
    file: '../../message-input-actions/AttachButton.tsx',
    control: 'attach button',
    tokens: ['max-sm:after:absolute', 'max-sm:after:-inset-y-1.5', 'max-sm:after:-left-2.5', 'max-sm:after:-right-0.5'],
  },
  {
    file: '../composer/ComposerSendControls.tsx',
    control: 'send button',
    tokens: ['-inset-y-[5.5px]', '-left-0.5', '-right-[9px]', 'hidden max-sm:block'],
  },
  {
    file: '../SamplePrompts.tsx',
    control: 'time-slot pills',
    tokens: [
      'max-sm:-my-[8px]',
      'max-sm:py-[8px]',
      'max-sm:relative',
      'max-sm:after:absolute',
      'max-sm:after:inset-x-0',
      'max-sm:after:-inset-y-[8px]',
      'flex w-full flex-col gap-3',
    ],
  },
];

describe('empty chat phone first-screen contract', () => {
  it.each(SWIPEABLE_ROWS)('keeps the $row on one swipeable row below the sm breakpoint', ({ file, tokens }) => {
    const source = read(file);

    expect(tokens.filter((token) => !source.includes(token))).toEqual([]);
  });

  it.each(TOUCH_TARGETS)('keeps the $control on a 44px touch target below the sm breakpoint', ({ file, tokens }) => {
    const source = read(file);

    expect(tokens.filter((token) => !source.includes(token))).toEqual([]);
  });

  it('keeps the send button free of positioning words and its slot out of the way of the attach button', () => {
    const source = read('../composer/ComposerSendControls.tsx');
    const sendClassName = source.match(/className="([^"]*message-send-btn[^"]*)"/)?.[1] ?? '';

    // brand.css treats any class list containing fixed / absolute / sticky as already positioned and drops the
    // brand elevation's `position: relative; z-index`, so the touch box has to be a child element, not an `after:`.
    expect(sendClassName).toContain('btn-brand-elevation');
    expect(sendClassName).not.toMatch(/fixed|absolute|sticky/);
    // The slot's 8px padding ring overlaps the attach button on phones (4px gap); it must not take pointer input.
    expect(source).toContain('brand-elevation-slot pointer-events-none');
    expect(sendClassName).toContain('pointer-events-auto');
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
    const textareaIndex = composer.indexOf('<ComposerTextarea');
    const pickerIndex = composer.indexOf('{!hideChatWorkspacePicker && <WorkspaceDirPicker />}');
    const actionBarIndex = composer.indexOf('<MobileComposerEntry');

    expect(textareaIndex).toBeGreaterThan(0);
    expect(pickerIndex).toBeGreaterThan(textareaIndex);
    expect(pickerIndex).toBeLessThan(actionBarIndex);
    // One render site: the desktop toolbar must not hold a second copy.
    expect(composer.match(/<WorkspaceDirPicker \/>/g)).toHaveLength(1);
  });

  it('renders the composer text at 16px on phones so iOS Safari does not zoom the page on focus', () => {
    const textarea = read('../composer/ComposerTextarea.tsx').match(/<TextareaAutosize[\s\S]*?\/>/)?.[0] ?? '';

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
