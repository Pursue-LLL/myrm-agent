/**
 * [INPUT] @/lib/api::apiRequest (POS: 前端统一请求入口), @/services/wikiService::buildWikiApiPath (POS: 按智能体范围拼接 Wiki 接口路径)
 * [OUTPUT] useWikiPurpose: Wiki 的“目的 / 方向”文本: 已保存值、草稿、加载与保存状态, 以及保存动作
 * [POS] 总览页“目的”卡的数据层: 范围变化时重新读取; 草稿与已保存值分开, 差异决定“重置 / 保存”是否可用。
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { apiRequest } from '@/lib/api';
import { buildWikiApiPath } from '@/services/wikiService';

export function useWikiPurpose(agentScopeId: string | null) {
  const t = useTranslations('settings.wiki');
  const [purpose, setPurpose] = useState('');
  const [purposeDraft, setPurposeDraft] = useState('');
  const [isLoadingPurpose, setIsLoadingPurpose] = useState(false);
  const [isSavingPurpose, setIsSavingPurpose] = useState(false);

  const loadPurpose = useCallback(async () => {
    setIsLoadingPurpose(true);
    try {
      const data = await apiRequest<{ purpose: string }>(buildWikiApiPath('/wiki/purpose', agentScopeId));
      setPurpose(data.purpose);
      setPurposeDraft(data.purpose);
    } catch (error) {
      console.error('Failed to load purpose:', error);
    } finally {
      setIsLoadingPurpose(false);
    }
  }, [agentScopeId]);

  useEffect(() => {
    void loadPurpose();
  }, [loadPurpose]);

  const handleSavePurpose = async () => {
    setIsSavingPurpose(true);
    try {
      await apiRequest(buildWikiApiPath('/wiki/purpose', agentScopeId), {
        method: 'PUT',
        body: JSON.stringify({ purpose: purposeDraft }),
      });
      setPurpose(purposeDraft);
      toast.success(t('success.purposeSaved'));
    } catch (error) {
      console.error('Failed to save purpose:', error);
      toast.error(t('errors.purposeSaveFailed'));
    } finally {
      setIsSavingPurpose(false);
    }
  };

  return { purpose, purposeDraft, setPurposeDraft, isLoadingPurpose, isSavingPurpose, handleSavePurpose };
}

export type WikiPurposeController = ReturnType<typeof useWikiPurpose>;
