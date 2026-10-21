'use client';

import { memo, type ComponentType, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';

import {
  IconBan,
  IconBot,
  IconFolder,
  IconKey,
  IconPlug,
  IconShieldCheck,
  type IconProps,
} from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { ExpertExportOmittedItem, ExpertExportPreview } from '@/services/expertPackage';
import { formatFileSize } from '@/types/artifact';

const MAX_LISTED_WORKSPACE_FILES = 6;

function Section({
  icon: Icon,
  title,
  tone = 'default',
  children,
}: {
  icon: ComponentType<IconProps>;
  title: string;
  tone?: 'default' | 'muted';
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Icon className={cn('h-4 w-4', tone === 'muted' ? 'text-muted-foreground' : 'text-primary')} />
        {title}
      </h4>
      <ul className="divide-y overflow-hidden rounded-lg border bg-card">{children}</ul>
    </section>
  );
}

function Row({ children }: { children: ReactNode }) {
  return <li className="flex flex-col gap-1 px-3 py-2.5">{children}</li>;
}

function OmittedRow({ item }: { item: ExpertExportOmittedItem }) {
  const t = useTranslations('agent.expertExport');
  return (
    <Row>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
          {t(`omittedKinds.${item.kind}` as Parameters<typeof t>[0])}
        </Badge>
        <span className="min-w-0 break-all text-sm font-medium">{item.name}</span>
        {item.owner && (
          <span className="text-xs text-muted-foreground">{t('omittedOwner', { owner: item.owner })}</span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t(`omitReason.${item.reason}` as Parameters<typeof t>[0])}</p>
    </Row>
  );
}

/** What the package will contain and what stays behind: the upper half of the expert export dialog. */
const ExpertExportClosure = memo(({ preview }: { preview: ExpertExportPreview }) => {
  const t = useTranslations('agent.expertExport');
  const { experts, skills, connectors, workspace_files: workspaceFiles, omitted } = preview;
  const hiddenWorkspaceFiles = Math.max(0, workspaceFiles.length - MAX_LISTED_WORKSPACE_FILES);

  return (
    <div className="space-y-4">
      <Section icon={IconBot} title={t('sections.experts', { count: experts.length })}>
        {experts.map((expert) => (
          <Row key={expert.name}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{expert.name}</span>
              <Badge
                variant={expert.is_entry ? 'default' : 'secondary'}
                className="px-1.5 py-0 text-[10px] font-normal"
              >
                {expert.is_entry ? t('roles.entry') : t('roles.sub')}
              </Badge>
            </div>
            {expert.description && <p className="line-clamp-2 text-xs text-muted-foreground">{expert.description}</p>}
            {expert.recommended_model && (
              <p className="text-[11px] text-muted-foreground">
                {t('recommendedModel', { model: expert.recommended_model })}
              </p>
            )}
          </Row>
        ))}
      </Section>

      {skills.length > 0 && (
        <Section icon={IconShieldCheck} title={t('sections.skills', { count: skills.length })}>
          {skills.map((skill) => (
            <Row key={`${skill.source}:${skill.name}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{skill.name}</span>
                {skill.source === 'custom' ? (
                  <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
                    {t('skill.files', { count: skill.file_count })}
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">
                    {t('skill.preset')}
                  </Badge>
                )}
                {skill.origin && (
                  <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
                    {t('skill.origin', { source: skill.origin })}
                  </Badge>
                )}
              </div>
            </Row>
          ))}
        </Section>
      )}

      {connectors.length > 0 && (
        <Section icon={IconPlug} title={t('sections.connectors', { count: connectors.length })}>
          {connectors.map((connector) => (
            <Row key={connector.name}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{connector.name}</span>
                <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
                  {connector.type}
                </Badge>
              </div>
              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <IconKey className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {connector.secret_keys.length > 0
                  ? t('connector.secrets', { keys: connector.secret_keys.join(', ') })
                  : t('connector.noSecrets')}
              </p>
            </Row>
          ))}
        </Section>
      )}

      {workspaceFiles.length > 0 && (
        <Section icon={IconFolder} title={t('sections.workspace', { count: workspaceFiles.length })}>
          {workspaceFiles.slice(0, MAX_LISTED_WORKSPACE_FILES).map((file) => (
            <Row key={file.path}>
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate font-mono text-xs" title={file.path}>
                  {file.path}
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{formatFileSize(file.size)}</span>
              </div>
            </Row>
          ))}
          {hiddenWorkspaceFiles > 0 && (
            <Row>
              <span className="text-xs text-muted-foreground">
                {t('workspaceMore', { count: hiddenWorkspaceFiles })}
              </span>
            </Row>
          )}
        </Section>
      )}

      {omitted.length > 0 && (
        <Section icon={IconBan} tone="muted" title={t('sections.omitted', { count: omitted.length })}>
          {omitted.map((item) => (
            <OmittedRow key={`${item.kind}:${item.owner ?? ''}:${item.name}:${item.reason}`} item={item} />
          ))}
        </Section>
      )}
    </div>
  );
});

ExpertExportClosure.displayName = 'ExpertExportClosure';

export default ExpertExportClosure;
