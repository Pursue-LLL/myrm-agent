'use client';

import React, { useEffect, useState } from 'react';
import { useLocale } from 'next-intl';
import { AgentAvatar } from './AgentAvatar';
import { getBuiltinAgentName } from './builtin-agent-i18n';
import { cn } from '@/lib/utils';
import { ChevronDown, Check } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Button } from '@/components/primitives/button';

export interface AgentProfile {
  id: string;
  name: string;
  description?: string | null;
  avatar_url?: string | null;
  is_built_in: boolean;
  system_prompt?: string | null;
  model_selection?: { providerId: string; model: string } | null;
}

interface AgentPickerProps {
  value?: string;
  onChange?: (agentId: string) => void;
  className?: string;
}

export function AgentPicker({ value, onChange, className }: AgentPickerProps) {
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch agents from API
    const fetchAgents = async () => {
      try {
        setLoading(true);
        // In a real app, this would be an API call
        // const res = await fetch('/api/agents');
        // const data = await res.json();
        // setAgents(data.data.items);

        // Mock data for now
        setAgents([
          { id: 'main', name: 'Main Agent', is_built_in: true },
          { id: 'coder', name: 'Coder Agent', is_built_in: true },
        ]);
      } catch (error) {
        console.error('Failed to fetch agents:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAgents();
  }, []);

  const selectedAgent = agents.find((a) => a.id === value) || agents[0];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-[200px] justify-between px-3', className)}
        >
          {selectedAgent ? (
            <div className="flex items-center gap-2 truncate">
              <AgentAvatar
                url={selectedAgent.avatar_url}
                name={selectedAgent.name}
                agentId={selectedAgent.id}
                className="h-5 w-5"
              />
              <span className="truncate">{getBuiltinAgentName(selectedAgent.id, selectedAgent.name, locale)}</span>
            </div>
          ) : (
            'Select Agent...'
          )}
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[200px] p-0" align="start">
        <div className="flex flex-col max-h-[300px] overflow-y-auto p-1">
          {loading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">Loading...</div>
          ) : agents.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">No agents found</div>
          ) : (
            agents.map((agent) => (
              <div
                key={agent.id}
                className={cn(
                  'relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
                  value === agent.id ? 'bg-accent text-accent-foreground' : '',
                )}
                onClick={() => {
                  onChange?.(agent.id);
                  setOpen(false);
                }}
              >
                <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} className="h-6 w-6" />
                <div className="flex flex-col flex-1 truncate">
                  <span className="truncate">{getBuiltinAgentName(agent.id, agent.name, locale)}</span>
                  {agent.is_built_in && <span className="text-[10px] text-muted-foreground">Built-in</span>}
                </div>
                {value === agent.id && <Check className="h-4 w-4 shrink-0" />}
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
