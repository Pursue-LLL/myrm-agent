/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { useTranslations } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '#locales/en.json';
import zh from '#locales/zh.json';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import PtcHintBadges from '../PtcHintBadges';

/** The card hands the badges what the server sent, a plain record of flags. */
type Sent = Record<string, boolean>;

const Badges = ({ annotations }: { annotations: Sent }) => {
  const t = useTranslations('toolApproval');
  return <PtcHintBadges annotations={annotations} t={t} />;
};

beforeEach(() => {
  intl.locale = 'en';
});

afterEach(() => {
  cleanup();
});

describe('PtcHintBadges', () => {
  it('shows nothing when the provider declares nothing that calls for care', () => {
    const { container } = render(<Badges annotations={{}} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('badges a destructive and an open-world declaration, each worded as a declaration', () => {
    render(<Badges annotations={{ destructiveHint: true, openWorldHint: true }} />);

    expect(screen.getByText('Declared destructive')).toHaveAttribute(
      'title',
      "The tool's provider declares that it makes irreversible changes. Take extra care.",
    );
    expect(screen.getByText('Declared external access')).toHaveAttribute(
      'title',
      "The tool's provider declares that it reaches external systems or the network.",
    );
  });

  it('words the same declarations in Chinese', () => {
    intl.locale = 'zh';
    render(<Badges annotations={{ destructiveHint: true, openWorldHint: true }} />);

    expect(screen.getByText('声明破坏性')).toBeInTheDocument();
    expect(screen.getByText('声明访问外部')).toBeInTheDocument();
  });

  it('shows only the badge a declaration earns', () => {
    render(<Badges annotations={{ openWorldHint: true }} />);

    expect(screen.getByText('Declared external access')).toBeInTheDocument();
    expect(screen.queryByText('Declared destructive')).toBeNull();
  });

  it('never reassures: a read-only claim that still arrives earns no badge', () => {
    const { container } = render(<Badges annotations={{ readOnlyHint: true }} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows a destructive declaration alone, however read-only the same provider calls the tool', () => {
    render(<Badges annotations={{ readOnlyHint: true, destructiveHint: true }} />);

    expect(screen.getAllByText(/./, { selector: 'span' })).toHaveLength(1);
    expect(screen.getByText('Declared destructive')).toBeInTheDocument();
  });
});

describe('the approval badge copy in the language packs', () => {
  it.each([
    ['English', en.toolApproval.ptc],
    ['Chinese', zh.toolApproval.ptc],
  ])('has no read-only wording in %s', (_language, ptc) => {
    expect(Object.keys(ptc).filter((key) => /readOnly/i.test(key))).toEqual([]);
  });
});
