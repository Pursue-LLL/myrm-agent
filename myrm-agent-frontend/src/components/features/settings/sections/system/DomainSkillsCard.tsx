/**
 * [INPUT]
 * GET /api/v1/browser/domain-skills — list domain skills
 * DELETE /api/v1/browser/domain-skills/:id — delete a skill
 *
 * [OUTPUT]
 * DomainSkillsCard: domain executable skill management card for system settings
 *
 * [POS]
 * Displays installed domain skill packs with domains, tool counts,
 * and per-skill delete action. Read-only for builtin skills.
 */

'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconTerminal, IconTrash, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

interface DomainToolInfo {
  name: string;
  description: string;
}

interface DomainSkillInfo {
  id: string;
  name: string;
  domains: string[];
  python_tools: Record<string, DomainToolInfo>;
  is_builtin: boolean;
}

const DomainSkillsCard = memo(() => {
  const t = useTranslations('settings.domainSkills');
  const [skills, setSkills] = useState<DomainSkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    try {
      const resp = await fetch(`${getBackendUrl()}/api/v1/browser/domain-skills`, {
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        setSkills(await resp.json());
      }
    } catch {
      /* server may be offline */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSkills();
  }, [fetchSkills]);

  const handleDelete = useCallback(
    async (skill: DomainSkillInfo) => {
      if (!window.confirm(t('confirmDelete', { name: skill.name }))) {
        return;
      }
      setDeletingId(skill.id);
      try {
        const resp = await fetch(`${getBackendUrl()}/api/v1/browser/domain-skills/${encodeURIComponent(skill.id)}`, {
          method: 'DELETE',
          headers: getAuthHeaders(),
        });
        if (resp.ok) {
          setSkills((prev) => prev.filter((s) => s.id !== skill.id));
          toast.success(t('deleteSuccess', { name: skill.name }));
        } else {
          toast.error(t('deleteFailed'));
        }
      } catch {
        toast.error(t('deleteFailed'));
      } finally {
        setDeletingId(null);
      }
    },
    [t],
  );

  return (
    <div className="rounded-xl border border-border/50 bg-card/60 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <IconTerminal className="w-4 h-4 text-emerald-500" />
          <div>
            <h4 className="text-sm font-medium text-foreground">{t('title')}</h4>
            <p className="text-xs text-muted-foreground">{t('description')}</p>
          </div>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            void fetchSkills();
          }}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        >
          <IconRefresh className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {loading ? (
        <div className="text-xs text-muted-foreground py-4 text-center">{t('loading')}</div>
      ) : skills.length === 0 ? (
        <div className="text-xs text-muted-foreground py-4 text-center">{t('empty')}</div>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {skills.map((skill) => {
            const isBuiltin = skill.is_builtin;
            const toolCount = Object.keys(skill.python_tools).length;
            return (
              <div
                key={skill.id}
                className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-foreground truncate">{skill.name}</span>
                    <span
                      className={cn(
                        'text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                        isBuiltin
                          ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                          : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
                      )}
                    >
                      {isBuiltin ? t('builtinBadge') : t('userBadge')}
                    </span>
                    <span className="text-[10px] text-muted-foreground">{t('tools', { count: toolCount })}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[10px] text-muted-foreground">
                      {t('domains')}: {skill.domains.slice(0, 3).join(', ')}
                      {skill.domains.length > 3 && ` +${skill.domains.length - 3}`}
                    </span>
                  </div>
                </div>
                {!isBuiltin && (
                  <button
                    onClick={() => handleDelete(skill)}
                    disabled={deletingId === skill.id}
                    className={cn(
                      'p-1.5 rounded-md text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors ml-2',
                      deletingId === skill.id && 'opacity-50 cursor-not-allowed',
                    )}
                    title={t('delete')}
                  >
                    <IconTrash className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});

DomainSkillsCard.displayName = 'DomainSkillsCard';

export default DomainSkillsCard;
