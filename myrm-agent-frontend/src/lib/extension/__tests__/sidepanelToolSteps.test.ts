/**
 * Side Panel tool-progress rows: the markup a tool call leaves in the message.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { addToolStep, updateLastToolStep } from '../../../../../myrm-agent-extension/src/sidepanel/tool_steps.js';

let container: HTMLElement;

beforeEach(() => {
  container = document.createElement('div');
});

describe('addToolStep', () => {
  it('appends a row with the status icon and the tool name', () => {
    addToolStep(container, 'file_write_tool', 'running');

    const step = container.querySelector('.tool-step');
    expect(step?.className).toBe('tool-step running');
    expect(step?.getAttribute('data-tool')).toBe('file_write_tool');
    expect(step?.querySelector('.icon')?.textContent).toBe('◎');
    expect(step?.querySelector('.name')?.textContent).toBe('file_write_tool');
  });

  it('writes the tool name as text, never as markup', () => {
    addToolStep(container, '<img src=x onerror=alert(1)>', 'running');

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.name')?.textContent).toBe('<img src=x onerror=alert(1)>');
  });

  it('shows the running icon for a status it does not know', () => {
    // The stream is an external source, so the row must survive a status outside the declared domain.
    addToolStep(container, 'a', 'unknown' as Parameters<typeof addToolStep>[2]);

    expect(container.querySelector('.icon')?.textContent).toBe('◎');
  });
});

describe('updateLastToolStep', () => {
  it('settles only the most recent row', () => {
    addToolStep(container, 'first', 'running');
    addToolStep(container, 'second', 'running');

    updateLastToolStep(container, 'second', 'done');

    const [first, second] = [...container.querySelectorAll('.tool-step')];
    expect(first.className).toBe('tool-step running');
    expect(second.className).toBe('tool-step done');
    expect(second.querySelector('.icon')?.textContent).toBe('✓');
  });

  it('marks a failed call', () => {
    addToolStep(container, 'a', 'running');

    updateLastToolStep(container, 'a', 'error');

    expect(container.querySelector('.icon')?.textContent).toBe('✗');
  });

  it('does nothing when no row exists yet', () => {
    expect(() => updateLastToolStep(container, 'a', 'done')).not.toThrow();
    expect(container.children).toHaveLength(0);
  });
});
