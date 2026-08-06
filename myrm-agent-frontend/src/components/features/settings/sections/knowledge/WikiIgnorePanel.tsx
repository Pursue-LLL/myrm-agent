'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Textarea } from '@/components/primitives/textarea';
import { wikiService } from '@/services/wikiService';
import { useWikiAgentScope } from './WikiAgentScopeContext';

export function WikiIgnorePanel() {
  const t = useTranslations('settings.wiki.wikiignore');
  const { agentScopeId } = useWikiAgentScope();
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await wikiService.getWikiIgnore(agentScopeId);
      setContent(result.content);
    } catch {
      toast.error(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [agentScopeId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await wikiService.putWikiIgnore(content, agentScopeId);
      toast.success(t('saved'));
    } catch {
      toast.error(t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card id="wiki-wikiignore-panel">
      <CardHeader>
        <CardTitle>{t('title')}</CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t('placeholder')}
          className="min-h-[120px] font-mono text-sm"
          disabled={loading}
        />
        <Button onClick={handleSave} disabled={loading || saving}>
          {saving ? t('saving') : t('save')}
        </Button>
      </CardContent>
    </Card>
  );
}
