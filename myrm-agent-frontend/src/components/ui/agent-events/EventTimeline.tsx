'use client';

/**
 * Agent Event Timeline Component
 *
 * 展示 Agent 执行过程中的事件时间线，包括：
 * - 工具调用（开始/结束）
 * - 命令执行（开始/输出/结束）
 * - 文件变更
 * - 权限请求
 * - 错误信息
 *
 * 仅 Tauri/Self-hosted 模式显示
 */

import { useTranslations } from 'next-intl';
import { useMemo } from 'react';

import { AlertCircle, ChevronRight, Clock, Code, FileEdit, Loader2, Lock, Terminal, Wrench } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';

import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';

// Event types
export type EventType =
  | 'tool_call_start'
  | 'tool_call_end'
  | 'command_start'
  | 'command_output'
  | 'command_end'
  | 'file_diff'
  | 'artifact_created'
  | 'permission_request'
  | 'permission_response'
  | 'thinking'
  | 'assistant_message'
  | 'error';

export type EventLevel = 'info' | 'warning' | 'error';

export interface AgentEvent {
  id: string;
  turn_id: string;
  event_type: EventType;
  level: EventLevel;
  event_index: number;
  payload: Record<string, unknown>;
  tool_name?: string;
  file_path?: string;
  duration_ms?: number;
  created_at: string;
}

interface EventTimelineProps {
  events: AgentEvent[];
  className?: string;
  onEventClick?: (event: AgentEvent) => void;
}

// Event icon mapping
const getEventIcon = (eventType: EventType, level: EventLevel) => {
  if (level === 'error') {
    return <AlertCircle className="h-4 w-4 text-destructive" />;
  }

  switch (eventType) {
    case 'tool_call_start':
    case 'tool_call_end':
      return <Wrench className="h-4 w-4 text-blue-500" />;
    case 'command_start':
    case 'command_output':
    case 'command_end':
      return <Terminal className="h-4 w-4 text-green-500" />;
    case 'file_diff':
      return <FileEdit className="h-4 w-4 text-orange-500" />;
    case 'artifact_created':
      return <Code className="h-4 w-4 text-purple-500" />;
    case 'permission_request':
    case 'permission_response':
      return <Lock className="h-4 w-4 text-yellow-500" />;
    case 'thinking':
    case 'assistant_message':
      return <Clock className="h-4 w-4 text-muted-foreground" />;
    case 'error':
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
};

// Format duration
const formatDuration = (ms?: number): string => {
  if (!ms) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

// Single event item
function EventItem({ event, onClick }: { event: AgentEvent; onClick?: (event: AgentEvent) => void }) {
  const t = useTranslations('agentEvents');

  const title = useMemo(() => {
    switch (event.event_type) {
      case 'tool_call_start':
        return `${t('toolCallStart')}: ${event.tool_name || 'Unknown'}`;
      case 'tool_call_end':
        return `${t('toolCallEnd')}: ${event.tool_name || 'Unknown'}`;
      case 'command_start':
        return t('commandStart');
      case 'command_output':
        return t('commandOutput');
      case 'command_end':
        return t('commandEnd');
      case 'file_diff':
        return `${t('fileDiff')}: ${event.file_path || 'Unknown'}`;
      case 'artifact_created':
        return `${t('artifactCreated')}: ${event.file_path || 'Unknown'}`;
      case 'permission_request':
        return t('permissionRequest');
      case 'permission_response':
        return t('permissionResponse');
      case 'thinking':
        return t('thinking');
      case 'assistant_message':
        return t('assistantMessage');
      case 'error':
        return t('error');
      default:
        return event.event_type;
    }
  }, [event, t]);

  const hasDetails = useMemo(() => {
    const payload = event.payload as Record<string, unknown> | undefined;
    return Boolean(
      payload &&
      (payload.input || payload.output || payload.command || payload.diff || payload.content || payload.message),
    );
  }, [event.payload]);

  return (
    <Collapsible>
      <div
        className={cn(
          'group relative flex items-start gap-3 rounded-lg border p-3 transition-colors',
          'hover:bg-muted/50',
          event.level === 'error' && 'border-destructive/50 bg-destructive/5',
          event.level === 'warning' && 'border-yellow-500/50 bg-yellow-500/5',
        )}
        onClick={() => onClick?.(event)}
      >
        {/* Timeline connector */}
        <div className="absolute bottom-0 left-[1.35rem] top-12 w-px bg-border" />

        {/* Icon */}
        <div className="relative z-10 flex h-6 w-6 items-center justify-center rounded-full bg-background ring-2 ring-border">
          {getEventIcon(event.event_type, event.level)}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{title}</span>
            {event.duration_ms && (
              <Badge variant="outline" className="text-xs">
                {formatDuration(event.duration_ms)}
              </Badge>
            )}
            {event.level === 'error' && (
              <Badge variant="destructive" className="text-xs">
                Error
              </Badge>
            )}
            {event.level === 'warning' && (
              <Badge variant="outline" className="border-yellow-500 text-xs text-yellow-500">
                Warning
              </Badge>
            )}
          </div>

          <div className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleTimeString()}</div>

          {/* Expandable details */}
          {hasDetails && (
            <>
              <CollapsibleTrigger className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                <ChevronRight className="h-3 w-3 transition-transform group-data-[state=open]:rotate-90" />
                {t('showDetails')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2">
                <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-xs">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </CollapsibleContent>
            </>
          )}
        </div>
      </div>
    </Collapsible>
  );
}

export function EventTimeline({ events, className, onEventClick }: EventTimelineProps) {
  const t = useTranslations('agentEvents');

  if (events.length === 0) {
    return <div className={cn('py-8 text-center text-muted-foreground', className)}>{t('noEvents')}</div>;
  }

  return (
    <div className={cn('space-y-2', className)}>
      {events.map((event) => (
        <EventItem key={event.id} event={event} onClick={onEventClick} />
      ))}
    </div>
  );
}

// Loading state
export function EventTimelineLoading() {
  return (
    <div className="flex items-center justify-center py-8">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}
