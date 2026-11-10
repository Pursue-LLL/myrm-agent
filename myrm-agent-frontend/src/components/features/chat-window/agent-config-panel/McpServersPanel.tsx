'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { Plug, Search } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import type { MCPServiceConfig } from '@/store/config/types';
import { AddMoreButton, SelectableCard } from './AgentConfigSelectableCard';

const MCPToolSelector = dynamic(() => import('./MCPToolSelector'), { ssr: false });

interface McpServersPanelProps {
  enabledMcps: MCPServiceConfig[];
  selectedNames: string[];
  toolSelections: Record<string, string[]>;
  onToggle: (name: string) => void;
  onToolSelectionChange: (serverName: string, tools: string[] | undefined) => void;
  onAddMore: () => void;
}

/** MCP 卡片：勾选要用的服务器，并按服务器细选可用工具。 */
export const McpServersPanel = ({
  enabledMcps,
  selectedNames,
  toolSelections,
  onToggle,
  onToolSelectionChange,
  onAddMore,
}: McpServersPanelProps) => {
  const t = useTranslations('agent.configEditor');
  const [searchQuery, setSearchQuery] = useState('');
  const filteredMcps = enabledMcps.filter((mcp) => mcp.name.toLowerCase().includes(searchQuery.toLowerCase()));

  return (
    <div className="space-y-4">
      {enabledMcps.length > 0 && (
        <>
          <div className="relative">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="pl-10 h-10 bg-muted/40 border-0 rounded-xl placeholder:text-muted-foreground/50 focus:bg-muted/60 transition-colors"
            />
          </div>
          <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
            {filteredMcps.map((mcp) => {
              const isEnabled = selectedNames.includes(mcp.name);
              return (
                <div key={mcp.name}>
                  <SelectableCard
                    id={`mcp-${mcp.name}`}
                    label={mcp.name}
                    description={mcp.description || mcp.type}
                    checked={isEnabled}
                    onCheckedChange={() => onToggle(mcp.name)}
                    icon={<Plug size={14} />}
                    colorClass="text-purple-500"
                  />
                  <MCPToolSelector
                    mcpConfig={mcp}
                    serverName={mcp.name}
                    selectedTools={toolSelections[mcp.name]}
                    onSelectionChange={onToolSelectionChange}
                    isServerEnabled={isEnabled}
                  />
                </div>
              );
            })}
          </div>
        </>
      )}
      {enabledMcps.length === 0 && (
        <div className="py-6 text-center">
          <p className="text-sm text-muted-foreground mb-3">{t('noEnabledMcp')}</p>
        </div>
      )}
      <AddMoreButton label={t('addMore')} onClick={onAddMore} />
    </div>
  );
};
