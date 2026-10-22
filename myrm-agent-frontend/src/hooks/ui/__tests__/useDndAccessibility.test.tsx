import { useCallback } from 'react';
import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DndContext, KeyboardSensor, defaultScreenReaderInstructions, useSensor, useSensors } from '@dnd-kit/core';
import type { Active, Over } from '@dnd-kit/core/dist/store';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { Announcements, UniqueIdentifier } from '@dnd-kit/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';
import type { MockLocale } from '@/test-utils/realIntl';
import enMessages from '../../../../locales/en.json';
import zhMessages from '../../../../locales/zh.json';
import { useDndAccessibility, useDndItemLabels } from '../useDndAccessibility';

type Locale = MockLocale;

const locale = vi.hoisted(() => ({ current: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale.current));

const TASK_ID = 'a1b2c3d4e5f6';
const TITLES: Record<string, string> = { [TASK_ID]: 'Fix login', other: 'Write docs' };
const COLUMNS: Record<Locale, string> = { en: 'Ready', zh: '就绪' };

const active = (id: string) => ({ id }) as Active;
const over = (id: string) => ({ id }) as Over;

function renderAccessibility(language: Locale) {
  locale.current = language;
  const labelOf = (id: UniqueIdentifier) => (id === 'ready' ? COLUMNS[language] : TITLES[String(id)]);
  return renderHook(() => useDndAccessibility(useCallback(labelOf, [])));
}

/** dnd-kit fires one hover event for the starting position in the same batch as the pick-up. */
function startPositionHover(announcements: Announcements, startTarget: string) {
  return announcements.onDragOver({ active: active(TASK_ID), over: over(startTarget) });
}

function dndText(language: Locale) {
  return (language === 'en' ? enMessages : zhMessages).common.dnd;
}

describe('useDndAccessibility announcements', () => {
  beforeEach(() => {
    locale.current = 'en';
  });

  it.each<Locale>(['en', 'zh'])('reads titles and column names, never raw ids (%s)', (language) => {
    const { announcements } = renderAccessibility(language).result.current;
    const text = dndText(language);
    const format = (template: string, values: Record<string, string>) =>
      Object.entries(values).reduce((out, [key, value]) => out.replace(`{${key}}`, value), template);

    const spoken = [
      announcements.onDragStart({ active: active(TASK_ID) }),
      startPositionHover(announcements, 'other'),
      announcements.onDragOver({ active: active(TASK_ID), over: over('ready') }),
      announcements.onDragOver({ active: active(TASK_ID), over: null }),
      announcements.onDragEnd({ active: active(TASK_ID), over: over('ready') }),
      announcements.onDragEnd({ active: active(TASK_ID), over: null }),
      announcements.onDragCancel({ active: active(TASK_ID), over: null }),
    ];

    expect(spoken).toEqual([
      format(text.pickedUp, { item: 'Fix login' }),
      undefined,
      format(text.movedOver, { item: 'Fix login', target: COLUMNS[language] }),
      format(text.leftTarget, { item: 'Fix login' }),
      format(text.droppedOn, { item: 'Fix login', target: COLUMNS[language] }),
      format(text.dropped, { item: 'Fix login' }),
      format(text.cancelled, { item: 'Fix login' }),
    ]);
    for (const sentence of spoken) {
      expect(sentence ?? '').not.toContain(TASK_ID);
      expect(sentence ?? '').not.toContain('ready');
    }
  });

  it.each(['ready', TASK_ID])(
    'keeps "picked up" audible by skipping the hover event dnd-kit fires at the starting position (over %s)',
    (startTarget) => {
      const { announcements } = renderAccessibility('en').result.current;

      announcements.onDragStart({ active: active(TASK_ID) });

      expect(announcements.onDragOver({ active: active(TASK_ID), over: over(startTarget) })).toBeUndefined();
    },
  );

  it('announces only the first hover after pick-up as the starting position', () => {
    const { announcements } = renderAccessibility('en').result.current;

    announcements.onDragStart({ active: active(TASK_ID) });
    startPositionHover(announcements, 'ready');

    expect(announcements.onDragOver({ active: active(TASK_ID), over: over('ready') })).toBe(
      '“Fix login” is over “Ready”.',
    );
  });

  it('skips the starting-position hover again for every new drag', () => {
    const { announcements } = renderAccessibility('en').result.current;

    announcements.onDragStart({ active: active(TASK_ID) });
    startPositionHover(announcements, 'ready');
    announcements.onDragOver({ active: active(TASK_ID), over: over('other') });
    announcements.onDragEnd({ active: active(TASK_ID), over: over('other') });
    announcements.onDragStart({ active: active(TASK_ID) });

    expect(announcements.onDragOver({ active: active(TASK_ID), over: over('ready') })).toBeUndefined();
  });

  it.each<Locale>(['en', 'zh'])('says so when a sortable item is back in its own slot (%s)', (language) => {
    const { announcements } = renderAccessibility(language).result.current;
    announcements.onDragStart({ active: active(TASK_ID) });
    startPositionHover(announcements, TASK_ID);
    announcements.onDragOver({ active: active(TASK_ID), over: over('other') });

    expect(announcements.onDragOver({ active: active(TASK_ID), over: over(TASK_ID) })).toBe(
      dndText(language).backAtStart.replace('{item}', 'Fix login'),
    );
  });

  it('reports a drop on its own position as a plain drop', () => {
    const { announcements } = renderAccessibility('zh').result.current;

    expect(announcements.onDragEnd({ active: active(TASK_ID), over: over(TASK_ID) })).toBe('“Fix login”已放下。');
  });

  it.each<Locale>(['en', 'zh'])('falls back to the generic noun instead of an unknown id (%s)', (language) => {
    const { announcements } = renderAccessibility(language).result.current;

    const spoken = announcements.onDragStart({ active: active('ghost-id') });

    expect(spoken).toContain(dndText(language).unknownItem);
    expect(spoken).not.toContain('ghost-id');
  });

  it.each<Locale>(['en', 'zh'])('replaces the English-only default instructions (%s)', (language) => {
    const { screenReaderInstructions } = renderAccessibility(language).result.current;

    expect(screenReaderInstructions.draggable).toBe(dndText(language).instructions);
    expect(screenReaderInstructions.draggable).not.toBe(defaultScreenReaderInstructions.draggable);
  });

  it('keeps the same configuration object while the label resolver is stable', () => {
    locale.current = 'en';
    const labelOf = (id: UniqueIdentifier) => String(id);
    const { result, rerender } = renderHook(({ resolver }) => useDndAccessibility(resolver), {
      initialProps: { resolver: labelOf },
    });
    const first = result.current;

    rerender({ resolver: labelOf });
    expect(result.current).toBe(first);

    rerender({ resolver: (id: UniqueIdentifier) => String(id) });
    expect(result.current).not.toBe(first);
  });
});

function SortableRow({ id, title }: { id: string; title: string }) {
  const { roleDescription, handleLabel } = useDndItemLabels();
  const { attributes, listeners, setNodeRef } = useSortable({ id, attributes: { roleDescription } });
  return (
    <li ref={setNodeRef}>
      <button type="button" aria-label={handleLabel} {...attributes} {...listeners}>
        {title}
      </button>
    </li>
  );
}

function Harness() {
  const labelOf = useCallback((id: UniqueIdentifier) => TITLES[String(id)], []);
  const accessibility = useDndAccessibility(labelOf);
  const sensors = useSensors(useSensor(KeyboardSensor));
  return (
    <DndContext sensors={sensors} accessibility={accessibility}>
      <SortableContext items={[TASK_ID, 'other']} strategy={verticalListSortingStrategy}>
        <ul>
          <SortableRow id={TASK_ID} title="Fix login" />
          <SortableRow id="other" title="Write docs" />
        </ul>
      </SortableContext>
    </DndContext>
  );
}

describe('dnd-kit keyboard drag with the localized accessibility layer', () => {
  afterEach(() => {
    locale.current = 'en';
  });

  it.each<Locale>(['en', 'zh'])(
    'exposes localized instructions, role description and live region (%s)',
    async (language) => {
      locale.current = language;
      const user = userEvent.setup();
      render(<Harness />);
      const text = dndText(language);
      const [handle] = screen.getAllByRole('button', { name: text.handleLabel });
      expectDefined(handle, 'first drag handle');
      expect(handle).toHaveAttribute('aria-roledescription', text.roleDescription);
      const instructionsId = handle.getAttribute('aria-describedby');
      expectNonNull(instructionsId, 'aria-describedby');
      expect(document.getElementById(instructionsId)).toHaveTextContent(text.instructions);

      await act(async () => handle.focus());
      await user.keyboard(' ');
      expect(screen.getByRole('status')).toHaveTextContent(text.pickedUp.replace('{item}', 'Fix login'));

      await user.keyboard('{Escape}');
      expect(screen.getByRole('status')).toHaveTextContent(text.cancelled.replace('{item}', 'Fix login'));
    },
  );
});
