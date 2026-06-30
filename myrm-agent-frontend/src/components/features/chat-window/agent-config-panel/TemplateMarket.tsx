'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { getTemplates, instantiateTemplate, type TemplateListItem } from '@/services/agent';
import { cn } from '@/lib/utils/classnameUtils';
import { Bot, Plus, Loader2, Users } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { resolveLucideIcon } from '@/components/agent/agent-icons';

interface TemplateMarketProps {
  className?: string;
  onInstantiated?: (agentId: string) => void;
}

const renderAvatar = (avatarUrl: string | null | undefined, isTeam: boolean) => {
  if (avatarUrl?.startsWith('lucide:')) {
    const IconComponent = resolveLucideIcon(avatarUrl.slice(7));
    if (IconComponent) {
      return <IconComponent size={16} />;
    }
  }
  return isTeam ? <Users size={16} /> : <Bot size={16} />;
};

const TemplateMarket = ({ className, onInstantiated }: TemplateMarketProps) => {
  const t = useTranslations('agent.configPanel');
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [instantiatingId, setInstantiatingId] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    const fetchTemplates = async () => {
      try {
        const backendReady = await ensureLocalBackendReady();
        if (!backendReady || cancelled) {
          return;
        }
        const data = await getTemplates();
        if (!cancelled) {
          setTemplates(data);
        }
      } catch {
        // Template market is optional; hide section when backend is unavailable.
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchTemplates();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleInstantiate = async (templateId: string) => {
    if (instantiatingId) return;
    setInstantiatingId(templateId);
    try {
      const newAgent = await instantiateTemplate(templateId);
      toast.success(t('instantiateSuccess') || 'Agent created from template!');
      if (onInstantiated) {
        onInstantiated(newAgent.id);
      } else {
        router.push(`/?agent_id=${newAgent.id}`);
      }
    } catch (e) {
      console.error(e);
      toast.error(t('instantiateError') || 'Failed to instantiate template');
    } finally {
      setInstantiatingId(null);
    }
  };

  if (loading) {
    return (
      <div className={cn("flex justify-center p-4", className)}>
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (templates.length === 0) {
    return null;
  }

  const individualTemplates = templates.filter(item => item.agent_type !== 'team');
  const teamTemplates = templates.filter(item => item.agent_type === 'team');

  return (
    <div className={cn("space-y-3 pt-2", className)}>
      <div className="flex items-center gap-2 px-1">
        <div className="flex-1 h-px bg-border/50" />
        <span className="text-xs text-muted-foreground">{t('templateMarket') || 'Template Market'}</span>
        <div className="flex-1 h-px bg-border/50" />
      </div>
      
      {teamTemplates.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {teamTemplates.map(template => (
            <TeamTemplateCard
              key={template.id}
              template={template}
              instantiatingId={instantiatingId}
              onInstantiate={handleInstantiate}
            />
          ))}
        </div>
      )}

      {individualTemplates.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {individualTemplates.map(template => (
            <div 
              key={template.id}
              className={cn(
                "relative flex flex-col gap-2 p-3 rounded-xl",
                "border border-border/40 bg-card/40 backdrop-blur-sm",
                "hover:border-primary/30 hover:bg-primary/5 transition-all",
                "group cursor-pointer"
              )}
              onClick={() => handleInstantiate(template.id)}
            >
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary shrink-0">
                  {renderAvatar(template.avatar_url, false)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">{template.name}</div>
                  {template.description && (
                    <div className="text-xs text-muted-foreground truncate">{template.description}</div>
                  )}
                </div>
                <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-background border border-border/50 opacity-0 group-hover:opacity-100 transition-opacity">
                  {instantiatingId === template.id ? (
                    <Loader2 size={12} className="animate-spin text-primary" />
                  ) : (
                    <Plus size={12} className="text-primary" />
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

function TeamTemplateCard({
  template,
  instantiatingId,
  onInstantiate,
}: {
  template: TemplateListItem;
  instantiatingId: string | null;
  onInstantiate: (id: string) => void;
}) {
  return (
    <div
      className={cn(
        "relative flex flex-col gap-2.5 p-3.5 rounded-xl",
        "border border-border/40 bg-card/40 backdrop-blur-sm",
        "hover:border-primary/30 hover:bg-primary/5 transition-all",
        "group cursor-pointer"
      )}
      onClick={() => onInstantiate(template.id)}
    >
      <div className="flex items-center gap-2.5">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 text-primary shrink-0">
          {renderAvatar(template.avatar_url, true)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-foreground truncate">{template.name}</span>
            <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-primary/10 text-primary">
              Team
            </span>
          </div>
          {template.description && (
            <div className="text-xs text-muted-foreground line-clamp-1 mt-0.5">{template.description}</div>
          )}
        </div>
        <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-background border border-border/50 opacity-0 group-hover:opacity-100 transition-opacity">
          {instantiatingId === template.id ? (
            <Loader2 size={12} className="animate-spin text-primary" />
          ) : (
            <Plus size={12} className="text-primary" />
          )}
        </div>
      </div>

      {template.members && template.members.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-[46px]">
          {template.members.map((member) => (
            <span
              key={member.role}
              className="inline-flex items-center px-2 py-0.5 text-[11px] rounded-md bg-muted/60 text-muted-foreground"
            >
              {member.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(TemplateMarket);
