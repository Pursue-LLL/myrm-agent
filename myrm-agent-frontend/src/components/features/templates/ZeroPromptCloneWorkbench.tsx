/**
 * [INPUT]
 * - ./templateTypes::AgentTemplateItem
 * - ./useTemplateMarketplaceStore::useTemplateMarketplaceStore
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - ZeroPromptCloneWorkbench: Native dialog modal for instant agent provisioning
 *
 * [POS]
 * Zero-prompt instantiation workbench modal in Prebuilt Agent App Marketplace.
 * Strictly adheres to 0-any rule, native <dialog> a11y, < 400 lines limit, and zero native emoji.
 */

'use client';

import React, { useState, useEffect, memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  X,
  Zap,
  Users,
  Bot,
  FolderTree,
  Wrench,
  BookOpen,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { useTemplateMarketplaceStore } from './useTemplateMarketplaceStore';

interface ZeroPromptCloneWorkbenchProps {
  onSuccess?: (createdAgent: { id: string; name: string }) => void;
}

export const ZeroPromptCloneWorkbench = memo<ZeroPromptCloneWorkbenchProps>(({ onSuccess }) => {
  const t = useTranslations('templateMarketplace');
  const template = useTemplateMarketplaceStore((s) => s.activeTemplateForClone);
  const isOpen = useTemplateMarketplaceStore((s) => s.isCloneWorkbenchOpen);
  const isCloning = useTemplateMarketplaceStore((s) => s.isCloning);
  const cloneError = useTemplateMarketplaceStore((s) => s.cloneError);
  const closeCloneWorkbench = useTemplateMarketplaceStore((s) => s.closeCloneWorkbench);
  const instantiateTemplate = useTemplateMarketplaceStore((s) => s.instantiateTemplate);

  const [customName, setCustomName] = useState('');
  const [initWiki, setInitWiki] = useState(true);
  const [successInfo, setSuccessInfo] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    if (template) {
      setCustomName('');
      setInitWiki(true);
      setSuccessInfo(null);
    }
  }, [template]);

  if (!isOpen || !template) {
    return null;
  }

  const isTeam = template.agent_type === 'team';
  const toolsCount = template.settings_preview?.enabled_builtin_tools.length ?? 0;
  const skillsCount =
    (template.settings_preview?.skill_ids.length ?? 0) +
    (template.settings_preview?.prebuilt_skill_ids.length ?? 0);

  const handleClone = async () => {
    const res = await instantiateTemplate({
      templateId: template.id,
      customName: customName.trim() || undefined,
      initWikiBlueprint: initWiki,
    });
    if (res) {
      setSuccessInfo(res);
      if (onSuccess) {
        onSuccess(res);
      }
    }
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="workbench-modal-title"
      data-testid="zero-prompt-clone-workbench"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs w-full h-full border-0"
    >
      <div className="relative w-full max-w-lg rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-zinc-100 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-500 dark:bg-amber-400/10 dark:text-amber-400">
              <Zap className="h-5 w-5 fill-current" />
            </div>
            <div>
              <h2 id="workbench-modal-title" className="text-lg font-bold leading-tight">
                {t('workbench.title')}
              </h2>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                {template.name} · {t('workbench.description')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeCloneWorkbench}
            disabled={isCloning}
            aria-label={t('workbench.cancel')}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content body */}
        <div className="py-4 space-y-4 text-xs">
          {/* Custom Name Input */}
          <div>
            <label htmlFor="custom-agent-name" className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
              {t('workbench.nameLabel')}
            </label>
            <input
              id="custom-agent-name"
              type="text"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              placeholder={template.name}
              disabled={isCloning}
              className="w-full rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-900 focus:border-zinc-500 focus:bg-white focus:outline-none dark:border-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-100 dark:focus:border-zinc-400"
            />
          </div>

          {/* Capabilities Preview */}
          <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3.5 dark:border-zinc-800 dark:bg-zinc-800/40">
            <div className="flex items-center gap-2 font-medium text-zinc-700 dark:text-zinc-300 mb-2">
              <Wrench className="h-3.5 w-3.5 text-sky-500" />
              <span>{t('workbench.presetCapabilities')}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] text-zinc-600 dark:text-zinc-400">
              <div className="flex items-center gap-1.5">
                <Wrench className="h-3 w-3 text-zinc-400" />
                <span>{toolsCount} {t('card.builtinTools')}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <BookOpen className="h-3 w-3 text-zinc-400" />
                <span>{skillsCount} {t('card.skills')}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {isTeam ? <Users className="h-3 w-3 text-indigo-400" /> : <Bot className="h-3 w-3 text-sky-400" />}
                <span>{isTeam ? t('card.team') : t('card.individual')}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Zap className="h-3 w-3 text-amber-400" />
                <span>Sandbox Ready</span>
              </div>
            </div>
          </div>

          {/* Recommended Wiki Blueprint */}
          {template.wiki_blueprint && template.wiki_blueprint.length > 0 && (
            <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3.5 dark:border-zinc-800 dark:bg-zinc-800/40">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 font-medium text-zinc-700 dark:text-zinc-300">
                  <FolderTree className="h-3.5 w-3.5 text-indigo-500" />
                  <span>{t('workbench.wikiBlueprint')}</span>
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-zinc-500 dark:text-zinc-400">
                  <input
                    type="checkbox"
                    checked={initWiki}
                    onChange={(e) => setInitWiki(e.target.checked)}
                    disabled={isCloning}
                    className="rounded border-zinc-300 text-zinc-900 focus:ring-zinc-400 dark:border-zinc-700"
                  />
                  <span>Init</span>
                </label>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {template.wiki_blueprint.map((dir, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 rounded bg-white px-2 py-0.5 text-[11px] font-mono border border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    <FolderTree className="h-2.5 w-2.5 text-zinc-400" />
                    {dir}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Team Members List */}
          {isTeam && template.members && template.members.length > 0 && (
            <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3.5 dark:border-zinc-800 dark:bg-zinc-800/40">
              <div className="flex items-center gap-2 font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                <Users className="h-3.5 w-3.5 text-indigo-500" />
                <span>{t('workbench.teamMembers')} ({template.members.length})</span>
              </div>
              <div className="space-y-1.5 max-h-28 overflow-y-auto pr-1">
                {template.members.map((m, idx) => (
                  <div key={idx} className="flex items-center justify-between text-[11px]">
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">{m.name}</span>
                    <span className="text-zinc-400 uppercase font-mono text-[10px]">{m.role}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Feedback message */}
          {cloneError && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{cloneError}</span>
            </div>
          )}

          {successInfo && (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{t('workbench.success')} ({successInfo.name})</span>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-zinc-100 dark:border-zinc-800">
          <button
            type="button"
            onClick={closeCloneWorkbench}
            disabled={isCloning}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800 transition-colors"
          >
            {t('workbench.cancel')}
          </button>
          <button
            type="button"
            onClick={handleClone}
            disabled={isCloning || !!successInfo}
            data-testid="confirm-clone-btn"
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-1.5 text-xs font-medium text-white shadow-xs transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {isCloning ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{t('workbench.cloning')}</span>
              </>
            ) : (
              <>
                <Zap className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />
                <span>{t('workbench.cloneConfirm')}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </dialog>
  );
});

ZeroPromptCloneWorkbench.displayName = 'ZeroPromptCloneWorkbench';
