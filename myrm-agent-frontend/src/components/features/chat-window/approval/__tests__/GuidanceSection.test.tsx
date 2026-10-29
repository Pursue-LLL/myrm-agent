/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import GuidanceSection from '../GuidanceSection';

function Harness({ initial = '', startOpen = false }: { initial?: string; startOpen?: boolean }) {
  const [value, setValue] = useState(initial);
  const [open, setOpen] = useState(startOpen);
  return <GuidanceSection value={value} onChange={setValue} open={open} onOpenChange={setOpen} />;
}

describe('GuidanceSection', () => {
  it('stays collapsed without a badge when nothing was written', () => {
    render(<Harness />);

    expect(screen.queryByPlaceholderText('guidance.placeholder')).toBeNull();
    expect(screen.queryByText('guidance.hasGuidance')).toBeNull();
  });

  it('opens on click and passes what is typed to the card', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('guidance.toggle'));
    fireEvent.change(screen.getByPlaceholderText('guidance.placeholder'), { target: { value: 'use the staging db' } });

    expect((screen.getByPlaceholderText('guidance.placeholder') as HTMLTextAreaElement).value).toBe(
      'use the staging db',
    );
  });

  it('flags written guidance on the collapsed header so it is not forgotten', () => {
    render(<Harness initial="use the staging db" />);

    expect(screen.getByText('guidance.hasGuidance')).toBeTruthy();
  });

  it('does not flag whitespace-only guidance', () => {
    render(<Harness initial="   " />);

    expect(screen.queryByText('guidance.hasGuidance')).toBeNull();
  });
});
