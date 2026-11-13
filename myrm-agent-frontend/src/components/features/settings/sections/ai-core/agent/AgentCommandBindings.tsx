'use client';

/**
 * [INPUT]
 * @/hooks/agent/useAgentCommandBindings::AgentCommandBindingsState (POS: 命令绑定草稿状态)
 * ./CommandBindingsEditor (POS: 命令绑定行列表编辑器)
 *
 * [OUTPUT]
 * AgentCommandBindings: Agent 能力页的斜杠命令卡片
 *
 * [POS]
 * 命令绑定卡片外壳：新建态提示先保存、加载中与加载失败占位，加载完成后渲染编辑器。
 * 保存由面板统一的保存按钮触发，卡片内不放独立保存入口。
 */

import { useTranslations } from 'next-intl';
import type { AgentCommandBindingsState } from '@/hooks/agent/useAgentCommandBindings';
import { CommandBindingsEditor } from './CommandBindingsEditor';

export function AgentCommandBindings({ state }: { state: AgentCommandBindingsState }) {
  const t = useTranslations('agent.commandBindings');

  return (
    <div className="space-y-3 rounded-xl border border-border/50 bg-card/60 p-4">
      <div>
        <h4 className="text-sm font-medium text-foreground">{t('title')}</h4>
        <p className="mt-0.5 text-xs text-muted-foreground">{t('description')}</p>
      </div>
      {state.unavailable ? (
        <Placeholder>{t('saveFirst')}</Placeholder>
      ) : state.status === 'error' ? (
        <p className="text-xs text-destructive-text">{t('loadFailed')}</p>
      ) : state.status === 'ready' ? (
        <CommandBindingsEditor value={state.bindings} issues={state.issues} onChange={state.setBindings} />
      ) : (
        <Placeholder>{t('loading')}</Placeholder>
      )}
    </div>
  );
}

function Placeholder({ children }: { children: string }) {
  return (
    <p className="rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
      {children}
    </p>
  );
}
