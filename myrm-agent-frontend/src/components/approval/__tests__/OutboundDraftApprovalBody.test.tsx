'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OutboundDraftApprovalBody } from '../OutboundDraftApprovalBody';
import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload, ApprovalPayloadData } from '@/store/useApprovalStore';

const stableT = (key: string) => `toolApproval.${key}`;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const heldReply: ApprovalPayloadData = {
  draft_content: 'Here is the report',
  original_content: 'Can you send me the report?',
  channel: 'telegram',
  recipient_id: 'chat-1',
  outbound: {
    media: [
      { media_type: 'document', path: '/workspace/out/report.pdf', filename: 'Q3 report.pdf' },
      { media_type: 'image', path: 'C:\\tmp\\shot.png' },
      { media_type: 'document', url: 'https://example.test/files/a.zip' },
    ],
  },
};

describe('OutboundDraftApprovalBody', () => {
  it('lists the attachments the held reply will carry, named as the recipient sees them', () => {
    render(<OutboundDraftApprovalBody payload={heldReply} />);

    expect(screen.getByText('Here is the report')).toBeInTheDocument();
    expect(screen.getByText('Q3 report.pdf')).toBeInTheDocument();
    expect(screen.getByText('shot.png')).toBeInTheDocument();
    expect(screen.getByText('https://example.test/files/a.zip')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });

  it('shows no attachment list for a text-only reply', () => {
    render(<OutboundDraftApprovalBody payload={{ draft_content: 'hello' }} />);

    expect(screen.getByText('hello')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('is what the approval card renders for outbound_draft approvals', () => {
    const approval: ApprovalPayload = {
      approval_id: 'approval-draft',
      user_id: 'user-1',
      action_type: 'outbound_draft',
      status: 'PENDING',
      severity: 'info',
      payload: heldReply,
    };

    render(
      <PolymorphicApprovalCard approval={approval} onResolve={async () => Promise.resolve()} isSubmitting={false} />,
    );

    expect(screen.getByText('toolApproval.outboundDraftTitle')).toBeInTheDocument();
    expect(screen.getByText('Q3 report.pdf')).toBeInTheDocument();
  });
});
