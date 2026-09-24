'use client';

/**
 * [INPUT]
 * lucide-react::CreditCard, ShieldCheck, Clock, AlertCircle
 * @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * SpendReceiptBadge: 精致的微扣款收据小芯片，展示自主支付记录与防篡改验证标识
 *
 * [POS]
 * Presentation chip rendered inside agent message blocks or tool outputs when autonomous
 * micro-payments occur.
 */

import React, { memo } from 'react';
import { CreditCard, ShieldCheck, Clock, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export interface SpendReceiptBadgeProps {
  merchantDomain: string;
  amountCents: number;
  currency?: string;
  status: 'reserved' | 'committed' | 'refunded' | 'rejected';
  hasEntryHash?: boolean;
  className?: string;
}

export const SpendReceiptBadge: React.FC<SpendReceiptBadgeProps> = memo(
  ({
    merchantDomain,
    amountCents,
    currency = 'USD',
    status,
    hasEntryHash = false,
    className,
  }) => {
    const formattedAmount = (amountCents / 100).toFixed(2);

    const statusConfig = {
      committed: {
        badgeClass:
          'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
        icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />,
        text: 'Paid & Verified',
      },
      reserved: {
        badgeClass:
          'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
        icon: <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0 animate-spin" />,
        text: 'Reserved',
      },
      refunded: {
        badgeClass: 'bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border-zinc-500/20',
        icon: <CreditCard className="w-3.5 h-3.5 text-zinc-500 shrink-0" />,
        text: 'Refunded',
      },
      rejected: {
        badgeClass: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
        icon: <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />,
        text: 'Blocked',
      },
    }[status];

    return (
      <div
        className={cn(
          'inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border shadow-xs transition-colors',
          statusConfig.badgeClass,
          className
        )}
      >
        {statusConfig.icon}
        <span className="font-semibold">{merchantDomain}</span>
        <span className="opacity-60">•</span>
        <span>
          {currency === 'USD' ? '$' : `${currency} `}
          {formattedAmount}
        </span>
        <span className="opacity-60">•</span>
        <span className="text-[10px] uppercase tracking-wider">{statusConfig.text}</span>
        {hasEntryHash && status === 'committed' && (
          <span
            className="w-1.5 h-1.5 rounded-full bg-emerald-500"
            title="HMAC Ledger Hash Verified"
          />
        )}
      </div>
    );
  }
);

SpendReceiptBadge.displayName = 'SpendReceiptBadge';
