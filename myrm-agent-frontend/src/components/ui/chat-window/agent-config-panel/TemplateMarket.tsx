'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { getTemplates, instantiateTemplate, type TemplateListItem } from '@/services/agent';
import { cn } from '@/lib/utils/classnameUtils';
import { Bot, Plus, Loader2 } from 'lucide-react';
import * as LucideIcons from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

interface TemplateMarketProps {
  className?: string;
  onInstantiated?: (agentId: string) => void;
}

const renderAvatar = (avatarUrl: string | null | undefined) => {
  if (avatarUrl?.startsWith('lucide:')) {
    const iconName = avatarUrl.split(':')[1];
    if (iconName) {
      // Convert kebab-case 'line-chart' to PascalCase 'LineChart'
      const componentName = iconName.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('');
      const IconComponent = (LucideIcons as any)[componentName];
      if (IconComponent) {
        return <IconComponent size={16} />;
      }
    }
  }
  return <Bot size={16} />;
};

const TemplateMarket = ({ className, onInstantiated }: TemplateMarketProps) => {
  const t = useTranslations('agent.configPanel');
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [instantiatingId, setInstantiatingId] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const data = await getTemplates();
        setTemplates(data);
      } catch (e) {
        console.error('Failed to fetch templates:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchTemplates();
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
    return null; // hide if no templates
  }

  return (
    <div className={cn("space-y-3 pt-2", className)}>
      <div className="flex items-center gap-2 px-1">
        <div className="flex-1 h-px bg-border/50" />
        <span className="text-xs text-muted-foreground">{t('templateMarket') || 'Template Market'}</span>
        <div className="flex-1 h-px bg-border/50" />
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {templates.map(template => (
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
                {renderAvatar(template.avatar_url)}
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
    </div>
  );
};

export default memo(TemplateMarket);
