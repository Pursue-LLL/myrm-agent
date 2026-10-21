'use client';

import { memo } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import AgentReadinessList from '@/components/agent/AgentReadinessList';
import { IconAlertTriangle, IconCheckCircle, IconLoader } from '@/components/features/icons/PremiumIcons';
import { agentSettingsHref } from '@/components/features/loadout/loadoutDeepLinks';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Badge } from '@/components/primitives/badge';

import { listNames } from './PluginImportParts';
import type { PluginAgentResult, PluginComponentFailure, PluginConfirmResult } from './pluginImportTypes';
import { useImportedAgentReadiness, type ImportedAgentReadiness } from './useImportedAgentReadiness';

// Failure codes the server reports; anything else gets the generic sentence rather than raw text.
const KNOWN_FAILURE_CODES = new Set([
  'skills_not_supported',
  'oversized_content',
  'security_issues',
  'INVALID_SKILL_NAME',
  'LIFECYCLE_SCRIPT_BLOCKED',
  'SECURITY_SCORE_BELOW_THRESHOLD',
  'DOWNGRADE_BLOCKED',
  'install_failed',
  'enable_failed',
  'stdio_not_allowed',
  'persist_failed',
  'invalid_agent',
]);

function FailureList({ failures }: { failures: PluginComponentFailure[] }) {
  const t = useTranslations('settings.plugins.import.failures');
  return (
    <Alert variant="destructive">
      <IconAlertTriangle className="h-4 w-4" />
      <AlertTitle>{t('title')}</AlertTitle>
      <AlertDescription>
        <ul className="mt-1 space-y-1">
          {failures.map((failure) => (
            <li key={`${failure.component}:${failure.name}`} className="text-xs">
              <span className="font-medium">
                {t(`components.${failure.component}`)} · {failure.name}
              </span>
              {' — '}
              {t(
                `codes.${KNOWN_FAILURE_CODES.has(failure.code) ? failure.code : 'generic'}` as Parameters<typeof t>[0],
              )}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function ReadinessBlock({ state }: { state: ImportedAgentReadiness }) {
  const t = useTranslations('settings.plugins.import.result');
  if (state.status === 'loading') {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <IconLoader className="h-3.5 w-3.5 animate-spin" />
        {t('checking')}
      </p>
    );
  }
  if (state.status === 'unavailable') {
    return <p className="text-xs text-muted-foreground">{t('readinessUnavailable')}</p>;
  }
  if (state.report.items.length === 0) {
    return (
      <p className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400">
        <IconCheckCircle className="h-3.5 w-3.5" />
        {t('allReady')}
      </p>
    );
  }
  return <AgentReadinessList items={state.report.items} withLinks />;
}

function ImportedAgentCard({ agent, readiness }: { agent: PluginAgentResult; readiness: ImportedAgentReadiness }) {
  const t = useTranslations('settings.plugins.import.result');
  const notes = [
    agent.withheld_tools.length > 0 && t('withheldTools', { tools: listNames(agent.withheld_tools) }),
    agent.unresolved_skills.length > 0 && t('unresolvedSkills', { names: listNames(agent.unresolved_skills) }),
    agent.unresolved_connectors.length > 0 &&
      t('unresolvedConnectors', { names: listNames(agent.unresolved_connectors) }),
    agent.unresolved_subagents.length > 0 && t('unresolvedSubagents', { names: listNames(agent.unresolved_subagents) }),
  ].filter((note): note is string => typeof note === 'string');

  return (
    <div className="divide-y rounded-xl border bg-background">
      <div className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">{agent.stored_name}</p>
            <Badge
              variant={agent.action === 'replaced' ? 'secondary' : 'default'}
              className="px-1.5 py-0 text-[10px] font-normal"
            >
              {agent.action === 'replaced' ? t('replaced') : t('created')}
            </Badge>
          </div>
          {agent.stored_name !== agent.package_name && (
            <p className="mt-0.5 text-xs text-muted-foreground">{t('renamedFrom', { name: agent.package_name })}</p>
          )}
          {agent.previous_version_saved && (
            <p className="mt-0.5 text-xs text-muted-foreground">{t('previousVersionSaved')}</p>
          )}
          {notes.map((note) => (
            <p key={note} className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
              {note}
            </p>
          ))}
        </div>
        <Link
          href={agentSettingsHref(agent.agent_id)}
          className="shrink-0 text-xs font-medium text-primary hover:underline"
        >
          {t('openAgent')}
        </Link>
      </div>
      <div className="p-4">
        <ReadinessBlock state={readiness} />
      </div>
    </div>
  );
}

/** What actually happened after confirm: counts, failures, secrets to fill in, and per-agent readiness. */
export const PluginImportResult = memo(({ result }: { result: PluginConfirmResult }) => {
  const t = useTranslations('settings.plugins.import');
  const readinessOf = useImportedAgentReadiness(result.agents.map((agent) => agent.agent_id));

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-xl border bg-background p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10">
          <IconCheckCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
        </div>
        <div className="min-w-0">
          <h3 className="text-base font-medium">{t('success.title')}</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t('success.description', {
              agents: result.imported_agents,
              skills: result.imported_skills,
              servers: result.imported_servers,
            })}
          </p>
        </div>
      </div>

      {result.failures.length > 0 && <FailureList failures={result.failures} />}

      {(result.required_secret_keys.length > 0 || result.imported_servers > 0) && (
        <Alert>
          <AlertDescription className="space-y-1 text-xs">
            {result.required_secret_keys.length > 0 && (
              <p>{t('success.requiredKeys', { keys: result.required_secret_keys.join(', ') })}</p>
            )}
            {result.imported_servers > 0 && <p>{t('success.disabledHint')}</p>}
          </AlertDescription>
        </Alert>
      )}

      {result.agents.map((agent) => (
        <ImportedAgentCard key={agent.agent_id} agent={agent} readiness={readinessOf(agent.agent_id)} />
      ))}
    </div>
  );
});
PluginImportResult.displayName = 'PluginImportResult';
