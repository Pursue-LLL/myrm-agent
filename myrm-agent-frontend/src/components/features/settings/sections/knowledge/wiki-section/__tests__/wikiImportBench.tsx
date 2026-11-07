import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { expect, vi } from 'vitest';

import { settle } from '@/test-utils/fakeClock';
import { useWikiImport, type WikiImportController } from '../useWikiImport';

type InputName = 'zip' | 'web-folder' | 'obsidian-zip';

interface BenchProps {
  agentScopeId: string | null;
  overview: Parameters<typeof useWikiImport>[0]['overview'];
  handleWikiTabChange: (tab: string) => void;
  goToKnowledgeGraph: () => void;
  onController: (controller: WikiImportController) => void;
}

/** 按导入卡片的方式把三个隐藏文件框接到 hook 上，ref 与 change 事件都是真实的。 */
function Bench({ onController, ...params }: BenchProps) {
  const imports = useWikiImport(params);
  useEffect(() => onController(imports));
  const {
    zipInputRef,
    webFolderInputRef,
    obsidianZipRef,
    handleImportZip,
    handleWebFolderSelect,
    handleImportObsidianZip,
  } = imports;
  return (
    <>
      <input data-testid="zip" type="file" ref={zipInputRef} onChange={handleImportZip} />
      <input data-testid="web-folder" type="file" ref={webFolderInputRef} onChange={handleWebFolderSelect} />
      <input data-testid="obsidian-zip" type="file" ref={obsidianZipRef} onChange={handleImportObsidianZip} />
    </>
  );
}

/** 渲染导入层，返回最新的控制器与可观察的页面回调；须在 wikiSectionTestKit 之后 import。 */
export function renderImport(agentScopeId: string | null = null) {
  const overview = { loadStats: vi.fn().mockResolvedValue(undefined), bumpTreeSync: vi.fn() };
  const handleWikiTabChange = vi.fn();
  const goToKnowledgeGraph = vi.fn();
  let latest: WikiImportController | null = null;
  const propsFor = (scope: string | null): BenchProps => ({
    agentScopeId: scope,
    overview,
    handleWikiTabChange,
    goToKnowledgeGraph,
    onController: (controller) => {
      latest = controller;
    },
  });
  const { rerender } = render(<Bench {...propsFor(agentScopeId)} />);
  const current = (): WikiImportController => {
    if (!latest) {
      throw new Error('The import layer has not rendered yet');
    }
    return latest;
  };
  return {
    overview,
    handleWikiTabChange,
    goToKnowledgeGraph,
    current,
    /** 等到两类导入都结束；浏览器目录导入要先压缩，不止一个宏任务。 */
    idle: () =>
      waitFor(() => {
        expect(current().isImporting).toBe(false);
        expect(current().isImportingObsidian).toBe(false);
      }),
    rerenderWithScope: (scope: string | null) => rerender(<Bench {...propsFor(scope)} />),
    input: (name: InputName) => screen.getByTestId<HTMLInputElement>(name),
    choose: async (name: InputName, files: File[] | null) => {
      fireEvent.change(screen.getByTestId(name), { target: { files } });
      await settle();
    },
  };
}

export type ImportBench = ReturnType<typeof renderImport>;
