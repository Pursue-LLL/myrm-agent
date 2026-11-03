/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import TimezoneSelector from '../TimezoneSelector';

function openSelector() {
  render(<TimezoneSelector value="Asia/Shanghai" onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /Asia\/Shanghai|Asia Shanghai/ }));
}

describe('TimezoneSelector copy', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('labels the search box and the popular group in English', () => {
    openSelector();

    expect(screen.getByPlaceholderText('Search time zones...')).toBeInTheDocument();
    expect(screen.getByText('Popular')).toBeInTheDocument();
  });

  it('labels the search box and the popular group in Chinese', () => {
    intl.locale = 'zh';
    openSelector();

    expect(screen.getByPlaceholderText('搜索时区...')).toBeInTheDocument();
    expect(screen.getByText('常用')).toBeInTheDocument();
  });

  it('says so when no time zone matches the search', () => {
    openSelector();

    fireEvent.change(screen.getByPlaceholderText('Search time zones...'), { target: { value: 'no-such-zone-xyz' } });

    expect(screen.getByText('No results')).toBeInTheDocument();
    expect(screen.queryByText('Popular')).not.toBeInTheDocument();
  });
});
