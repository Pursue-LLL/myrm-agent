'use client';

/**
 * [INPUT]
 * @/components/ui/memory/SharedContextTargetBinding (POS: Shared Context runtime binding component)
 *
 * [OUTPUT]
 * AgentSharedContextBinding: Agent-scoped Shared Context binding entry.
 *
 * [POS]
 * Agent settings adapter that binds the reusable Shared Context target UI to the current Agent.
 */

import { useTranslations } from 'next-intl';

import { SharedContextTargetBinding } from '@/components/ui/memory/SharedContextTargetBinding';

interface AgentSharedContextBindingProps {
  agentId: string | null;
  isNew: boolean;
}

export function AgentSharedContextBinding({ agentId, isNew }: AgentSharedContextBindingProps) {
  const t = useTranslations('agent.sharedContexts');

  return (
    <SharedContextTargetBinding
      targetType="agent"
      targetId={agentId}
      targetLabel={t('targetLabel')}
      disabled={isNew || !agentId}
      disabledMessage={t('saveFirst')}
    />
  );
}
