import { create } from 'zustand';
import type {
  DetectedLinkEntity,
  RealLinkAlignmentState,
} from './realLinkTypes';
import {
  scanLinksFromHtml,
  replaceLinksInHtml,
} from './realLinkDetector';

const DEFAULT_DEMO_CODE = `<section className="landing-recruitment-hero">
  <div className="container mx-auto py-12">
    <h1 className="text-3xl font-bold">三只松鼠 2027 届全球校园招聘盛典</h1>
    <p className="mt-2 text-slate-600">造食者，让天下主人爽起来！松鼠家招募森林合伙人</p>
    
    <div className="cta-action-group mt-6 flex gap-4">
      {/* 假链接占位符 1: 校招投递 */}
      <a href="#" className="btn-primary">立即投递校招岗位</a>
      {/* 假链接占位符 2: 在线客服咨询 */}
      <a href="javascript:void(0)" className="btn-secondary">联系校招小助手</a>
      {/* 假链接占位符 3: 官方坚果商城特惠 */}
      <a href="https://example.com/shop" className="btn-outline">领新人坚果零食礼包</a>
      {/* 真实有效链接: 开发者开放文档 */}
      <a href="https://docs.myrm.io/developer/api-reference" className="btn-link">查看协同 API 文档</a>
    </div>
  </div>
</section>`;

function calculateAlignmentRate(links: DetectedLinkEntity[]): number {
  if (links.length === 0) {
    return 100;
  }
  const alignedCount = links.filter((l) => l.status === 'aligned').length;
  return Math.round((alignedCount / links.length) * 100);
}

const initialLinks = scanLinksFromHtml(DEFAULT_DEMO_CODE);

export const useRealLinkAlignmentStore = create<RealLinkAlignmentState>(
  (set, get) => ({
    codeSnippet: DEFAULT_DEMO_CODE,
    detectedLinks: initialLinks,
    isScanning: false,
    alignmentRate: calculateAlignmentRate(initialLinks),
    isApplied: false,

    scanCodeSnippet: (code: string) => {
      set({ isScanning: true });
      const links = scanLinksFromHtml(code);
      set({
        codeSnippet: code,
        detectedLinks: links,
        alignmentRate: calculateAlignmentRate(links),
        isScanning: false,
        isApplied: false,
      });
      return links;
    },

    alignLinkToRealEntity: (
      linkId: string,
      resolvedUrl: string,
      entityName: string
    ) => {
      const updated = get().detectedLinks.map((item) => {
        if (item.id === linkId) {
          return {
            ...item,
            resolvedRealUrl: resolvedUrl,
            targetEntityName: entityName,
            status: 'aligned' as const,
            reason: `已精准对齐至官方权威实体 [${entityName}]`,
          };
        }
        return item;
      });

      set({
        detectedLinks: updated,
        alignmentRate: calculateAlignmentRate(updated),
        isApplied: false,
      });
    },

    batchAlignPlaceholders: () => {
      const updated = get().detectedLinks.map((item) => {
        if (item.status === 'placeholder_detected') {
          const targetUrl = item.resolvedRealUrl || 'https://www.3squirrels.com';
          const targetName = item.targetEntityName || '品牌企业官方门户中枢';
          return {
            ...item,
            resolvedRealUrl: targetUrl,
            targetEntityName: targetName,
            status: 'aligned' as const,
            reason: `自动批量对齐官方实体 [${targetName}]`,
          };
        }
        return item;
      });

      set({
        detectedLinks: updated,
        alignmentRate: calculateAlignmentRate(updated),
        isApplied: false,
      });
    },

    applyAlignedCode: (): string => {
      const { codeSnippet, detectedLinks } = get();
      const updatedCode = replaceLinksInHtml(codeSnippet, detectedLinks);
      set({
        codeSnippet: updatedCode,
        isApplied: true,
      });
      return updatedCode;
    },

    setCodeSnippet: (code: string) => {
      get().scanCodeSnippet(code);
    },

    resetState: () => {
      const links = scanLinksFromHtml(DEFAULT_DEMO_CODE);
      set({
        codeSnippet: DEFAULT_DEMO_CODE,
        detectedLinks: links,
        isScanning: false,
        alignmentRate: calculateAlignmentRate(links),
        isApplied: false,
      });
    },
  })
);
