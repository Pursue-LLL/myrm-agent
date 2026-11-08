/**
 * [INPUT] next/navigation (POS: ?wikiTab= / ?conceptPath= / ?rawPath= / ?focus= 深链与路由替换), ../wiki/wikiSectionUtils::resolveHealthIssueNavigationTarget (POS: 健康问题位置 → 原文 / 概念目标)
 * [OUTPUT] useWikiTabs: 当前标签页与 URL 的双向同步, 跨页签跳转 (概念、健康问题、待审综合、重复审核) 与待审页的初始筛选
 * [POS] Wiki 面板的导航层: 标签页以 URL 为准, URL 带 wikiTab / conceptPath 时进入对应页签, 切换标签页时回写 URL。
 */

import { useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { resolveHealthIssueNavigationTarget } from '../wiki/wikiSectionUtils';

const WIKI_TABS = ['overview', 'concepts', 'pendingEdits', 'duplicateReview', 'queue'] as const;
type WikiTab = (typeof WIKI_TABS)[number];

function isWikiTab(value: string): value is WikiTab {
  return (WIKI_TABS as readonly string[]).includes(value);
}

export function useWikiTabs() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [activeTab, setActiveTab] = useState('overview');
  const [pendingEditsInitialFilter, setPendingEditsInitialFilter] = useState<'all' | 'concepts' | 'synthesis'>('all');

  const replaceQuery = useCallback(
    (params: URLSearchParams) => {
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const syncWikiTabToUrl = useCallback(
    (tab: WikiTab) => {
      const params = new URLSearchParams(searchParams.toString());
      if (tab === 'overview') {
        params.delete('wikiTab');
      } else {
        params.set('wikiTab', tab);
      }
      replaceQuery(params);
    },
    [searchParams, replaceQuery],
  );

  const handleWikiTabChange = useCallback(
    (tab: string) => {
      if (!isWikiTab(tab)) {
        return;
      }
      setActiveTab(tab);
      syncWikiTabToUrl(tab);
    },
    [syncWikiTabToUrl],
  );

  useEffect(() => {
    const tab = searchParams.get('wikiTab');
    if (tab && isWikiTab(tab)) {
      setActiveTab(tab);
      return;
    }
    const conceptPath = searchParams.get('conceptPath');
    if (conceptPath) {
      setActiveTab('concepts');
      return;
    }
    if (!tab) {
      setActiveTab('overview');
    }
  }, [searchParams]);

  const rawPathFromUrl = searchParams.get('rawPath');
  const conceptPathFromUrl = searchParams.get('conceptPath');

  useEffect(() => {
    const focus = searchParams.get('focus');
    if (focus === 'wikiignore') {
      document.getElementById('wiki-wikiignore-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [searchParams]);

  const navigateToHealthIssue = useCallback(
    (location: string) => {
      const target = resolveHealthIssueNavigationTarget(location);
      const params = new URLSearchParams(searchParams.toString());
      params.delete('rawPath');
      params.delete('conceptPath');
      if (target.kind === 'raw') {
        params.delete('wikiTab');
        params.set('rawPath', target.path);
        setActiveTab('overview');
      } else {
        params.set('wikiTab', 'concepts');
        params.set('conceptPath', target.path);
        setActiveTab('concepts');
      }
      replaceQuery(params);
    },
    [replaceQuery, searchParams],
  );

  const openConcept = (relPath: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('wikiTab', 'concepts');
    params.set('conceptPath', relPath);
    setActiveTab('concepts');
    replaceQuery(params);
  };

  const handleOpenSynthesisPending = () => {
    setPendingEditsInitialFilter('synthesis');
    handleWikiTabChange('pendingEdits');
  };

  const handleOpenDuplicateReview = () => {
    handleWikiTabChange('duplicateReview');
  };

  return {
    activeTab,
    pendingEditsInitialFilter,
    rawPathFromUrl,
    conceptPathFromUrl,
    handleWikiTabChange,
    navigateToHealthIssue,
    openConcept,
    handleOpenSynthesisPending,
    handleOpenDuplicateReview,
  };
}

export type WikiTabsController = ReturnType<typeof useWikiTabs>;
