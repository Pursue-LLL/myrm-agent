/**
 * [INPUT]
 * - ../ChannelLimitInput (POS: box under test)
 *
 * [OUTPUT]
 * - Test suite for how the inline limit box of a channel takes the keyboard
 *
 * [POS]
 * Leaving the box saves what was typed, and Enter is another way of leaving it, so a limit is never saved twice or by
 * two paths; Escape takes back what was typed without saving it.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ChannelLimitInput from '../ChannelLimitInput';

function renderBox() {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(<ChannelLimitInput value={2} label="dailyLimit" onSave={onSave} />);
  return { box: screen.getByRole<HTMLInputElement>('spinbutton', { name: 'dailyLimit' }), onSave };
}

describe('ChannelLimitInput keyboard', () => {
  it('saves the typed limit once on Enter and leaves the box', async () => {
    const user = userEvent.setup();
    const { box, onSave } = renderBox();

    await user.tripleClick(box);
    await user.keyboard('5{Enter}');

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(5);
    expect(box).not.toHaveFocus();
  });

  it('saves the typed limit when the box is left, as before', async () => {
    const user = userEvent.setup();
    const { box, onSave } = renderBox();

    await user.tripleClick(box);
    await user.keyboard('7');
    await user.tab();

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(7);
  });

  it('takes back what was typed on Escape and saves nothing, not even when the box is left afterwards', async () => {
    const user = userEvent.setup();
    const { box, onSave } = renderBox();

    await user.tripleClick(box);
    await user.keyboard('5{Escape}');

    expect(box.value).toBe('2');
    await user.tab();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('sends nothing on Enter when nothing was typed', async () => {
    const user = userEvent.setup();
    const { box, onSave } = renderBox();

    await user.click(box);
    await user.keyboard('{Enter}');

    expect(onSave).not.toHaveBeenCalled();
  });
});
