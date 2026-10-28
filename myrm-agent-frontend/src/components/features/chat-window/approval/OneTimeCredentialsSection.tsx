'use client';

/**
 * [INPUT]
 * - @/components/approval/MaskedCredentialInputCard (POS: 一次性凭据录入表单)
 * - next-intl::useTranslations (POS: toolApproval.maskedCredentials 文案)
 *
 * [OUTPUT]
 * - OneTimeCredentialsSection: 命令审批卡里「这条命令需要密码或密钥」的折叠入口
 *
 * [POS]
 * shell 审批卡的凭据入口；折叠只隐藏表单、不卸载，已录入的状态不会因收起而丢失。
 */

import { ChevronDown, ChevronRight, Key } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useState } from 'react';

import {
  MaskedCredentialInputCard,
  type MaskedCredentialInputCardProps,
} from '@/components/approval/MaskedCredentialInputCard';
import { Button } from '@/components/primitives/button';

type OneTimeCredentialsSectionProps = MaskedCredentialInputCardProps;

export default function OneTimeCredentialsSection(props: OneTimeCredentialsSectionProps) {
  const t = useTranslations('toolApproval.maskedCredentials');
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="h-7 px-2 text-xs text-warning hover:bg-warning/10 hover:text-warning"
      >
        <Key className="mr-1.5 h-3.5 w-3.5" />
        {props.staged ? t('readyCount', { count: props.staged.items.length }) : t('open')}
        <Chevron className="ml-1 h-3 w-3" />
      </Button>
      <div hidden={!open}>
        <MaskedCredentialInputCard {...props} />
      </div>
    </div>
  );
}
