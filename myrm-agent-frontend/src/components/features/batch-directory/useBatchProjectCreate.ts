/**
 * [INPUT] @/services/batch-directory::createBatchProject (POS: 创建批量项目), @/services/kanban::listBoards (POS: 目标看板选项), @/services/riskHeldToast::isRiskHeldError (POS: 风控拦截判定), ./useDirectoryBrowser (POS: 目录选择状态)
 * [OUTPUT] useBatchProjectCreate: 创建向导的表单状态、看板选项、目录选择、校验与提交（成功后清空并回调 onCreated）
 * [POS] 列表页创建向导的状态层；表单与目录选择在向导收起后保留，仅创建成功时清空；提示词被风控拦下时只显示统一风控提示。
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { createBatchProject, type BatchProjectDetail, type CreateBatchProjectInput } from '@/services/batch-directory';
import { listBoards, type KanbanBoard } from '@/services/kanban';
import { isRiskHeldError } from '@/services/riskHeldToast';
import { useDirectoryBrowser } from './useDirectoryBrowser';

export interface CreateFormState {
  name: string;
  prompt: string;
  board_id: string;
  concurrency: string;
  notify_enabled: boolean;
  require_approval: boolean;
  artifact_patterns: string;
}

const EMPTY_FORM: CreateFormState = {
  name: '',
  prompt: '',
  board_id: '',
  concurrency: '3',
  notify_enabled: true,
  require_approval: false,
  artifact_patterns: '',
};

interface UseBatchProjectCreateParams {
  /** 向导展开时自动从家目录开始浏览。 */
  active: boolean;
  onCreated: (created: BatchProjectDetail) => Promise<void>;
}

export function useBatchProjectCreate({ active, onCreated }: UseBatchProjectCreateParams) {
  const t = useTranslations('batchDirectory');
  const [form, setForm] = useState<CreateFormState>(EMPTY_FORM);
  const [boards, setBoards] = useState<KanbanBoard[]>([]);
  const [creating, setCreating] = useState(false);
  const dirs = useDirectoryBrowser();
  const { browse, selected, reset: resetDirs } = dirs;

  const fetchBoards = useCallback(async () => {
    try {
      const res = await listBoards();
      setBoards(res.items);
    } catch {
      // 看板列表失败不阻断创建流程（可自动创建 board）
    }
  }, []);

  useEffect(() => {
    void fetchBoards();
  }, [fetchBoards]);

  useEffect(() => {
    if (active) {
      void browse('~');
    }
  }, [active, browse]);

  const updateForm = useCallback((patch: Partial<CreateFormState>) => {
    setForm((prev) => ({ ...prev, ...patch }));
  }, []);

  const submit = useCallback(async () => {
    if (!form.name.trim()) {
      toast.error(t('nameRequired'));
      return;
    }
    if (!form.prompt.trim()) {
      toast.error(t('promptRequired'));
      return;
    }
    if (selected.length === 0) {
      toast.error(t('dirsRequired'));
      return;
    }

    const input: CreateBatchProjectInput = {
      name: form.name.trim(),
      prompt: form.prompt.trim(),
      directories: [...selected],
      board_id: form.board_id || null,
      concurrency: Number(form.concurrency) || 3,
      notify_enabled: form.notify_enabled,
      require_approval: form.require_approval,
      artifact_patterns: form.artifact_patterns
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };

    setCreating(true);
    try {
      const created = await createBatchProject(input);
      toast.success(t('createSuccess', { name: created.name }));
      setForm(EMPTY_FORM);
      resetDirs();
      await onCreated(created);
    } catch (err) {
      // `apiRequest` has already shown the notice for a held prompt, in the user's language.
      if (!isRiskHeldError(err)) {
        toast.error(err instanceof Error ? err.message : t('createError'));
      }
    } finally {
      setCreating(false);
    }
  }, [form, selected, onCreated, resetDirs, t]);

  return { form, updateForm, boards, creating, dirs, submit };
}

export type BatchProjectCreate = ReturnType<typeof useBatchProjectCreate>;
