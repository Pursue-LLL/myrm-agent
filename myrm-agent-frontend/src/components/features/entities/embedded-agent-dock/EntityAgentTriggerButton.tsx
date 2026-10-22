import React from 'react';
import {
  Bot,
  User,
  Building,
  DollarSign,
  FolderKanban,
  FileText,
  Sparkles,
} from 'lucide-react';
import { useEntityEmbeddedAgentStore } from './useEntityEmbeddedAgentStore';
import type { BusinessEntitySnapshot, BusinessEntityType } from './entityEmbeddedAgentTypes';

interface EntityAgentTriggerButtonProps {
  entity: BusinessEntitySnapshot;
  className?: string;
}

export const EntityAgentTriggerButton: React.FC<EntityAgentTriggerButtonProps> = ({
  entity,
  className = '',
}) => {
  const { openEntityDock } = useEntityEmbeddedAgentStore();

  const getEntityIcon = (type: BusinessEntityType): React.ReactElement => {
    switch (type) {
      case 'contact':
        return <User className="w-3.5 h-3.5" />;
      case 'company':
        return <Building className="w-3.5 h-3.5" />;
      case 'deal':
        return <DollarSign className="w-3.5 h-3.5" />;
      case 'project':
        return <FolderKanban className="w-3.5 h-3.5" />;
      case 'document':
        return <FileText className="w-3.5 h-3.5" />;
      default:
        return <Bot className="w-3.5 h-3.5" />;
    }
  };

  return (
    <button
      type="button"
      onClick={() => openEntityDock(entity)}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all rounded-lg border bg-indigo-950/40 hover:bg-indigo-900/60 border-indigo-500/30 hover:border-indigo-500/50 text-indigo-300 hover:text-white shadow-sm ${className}`}
      aria-label={`呼出 ${entity.title} 的专属智能体`}
    >
      <span className="p-0.5 rounded bg-indigo-500/20 text-indigo-400">
        {getEntityIcon(entity.type)}
      </span>
      <span>专属智能体</span>
      <Sparkles className="w-3 h-3 text-amber-400" />
    </button>
  );
};
