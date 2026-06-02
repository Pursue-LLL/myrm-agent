'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Settings } from 'lucide-react';
import Image from 'next/image';
import { useLocale } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { AgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { getAgent, type Agent } from '@/services/agent';

interface AgentInfoBannerProps {
  agentId: string;
  className?: string;
}

export default function AgentInfoBanner({ agentId, className }: AgentInfoBannerProps) {
  const router = useRouter();
  const locale = useLocale();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadAgent = async () => {
      try {
        const data = await getAgent(agentId);
        setAgent(data);
      } catch (error) {
        console.error('Failed to load agent:', error);
      } finally {
        setLoading(false);
      }
    };
    loadAgent();
  }, [agentId]);

  if (loading || !agent) return null;

  const renderAvatar = () => {
    const parsed = parseAvatarUrl(agent.avatar_url, agent.id);

    if (parsed?.type === 'icon') {
      return <AgentIcon iconId={parsed.iconId} size="sm" />;
    }

    if (parsed?.type === 'emoji') {
      return <span className="text-2xl">{parsed.emoji}</span>;
    }

    if (parsed?.type === 'image') {
      return (
        <Image
          src={parsed.src}
          alt={agent.name}
          width={32}
          height={32}
          unoptimized={parsed.src.startsWith('http')}
          className="w-8 h-8 rounded-full object-cover"
        />
      );
    }

    const gradients = [
      { from: 'from-primary', to: 'to-violet-500' },
      { from: 'from-blue-500', to: 'to-cyan-500' },
      { from: 'from-emerald-500', to: 'to-teal-500' },
      { from: 'from-orange-500', to: 'to-amber-500' },
      { from: 'from-pink-500', to: 'to-rose-500' },
      { from: 'from-indigo-500', to: 'to-purple-500' },
    ];

    const gradientIdx = parsed?.type === 'gradient' ? parsed.index : 0;
    const gradient = gradients[gradientIdx % gradients.length];

    return (
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center',
          'bg-gradient-to-br',
          gradient.from,
          gradient.to,
        )}
      >
        <span className="text-sm font-semibold text-white">{agent.name[0]}</span>
      </div>
    );
  };

  return (
    <div className={cn('flex items-center gap-3 px-4 py-2 bg-muted/50 border-b border-border', className)}>
      {renderAvatar()}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{getBuiltinAgentName(agent.id, agent.name, locale)}</p>
        {agent.description && (
          <p className="text-xs text-muted-foreground truncate">
            {getBuiltinAgentDescription(agent.id, agent.description, locale)}
          </p>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`/settings?tab=agents&agentId=${agent.id}`)}
        className="flex items-center gap-1"
      >
        <Settings className="w-4 h-4" />
        <span className="hidden sm:inline">Switch</span>
      </Button>
    </div>
  );
}
