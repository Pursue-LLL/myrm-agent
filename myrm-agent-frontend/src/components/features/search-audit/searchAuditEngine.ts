import {
  AuditCitationItem,
  SearchAuditSession,
  SourceQualityMatrix,
  SourceTier,
  SubQueryTrace,
} from './searchAuditTypes';

/**
 * 提取 URL 的主域名
 */
export function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.toLowerCase();
  } catch {
    return 'unknown.source';
  }
}

/**
 * 根据域名与正文特征量化计算 100 分数据源质量矩阵
 */
export function calculateSourceQualityMatrix(
  url: string,
  isFullText: boolean = true,
  hasAiRewrite: boolean = false
): SourceQualityMatrix {
  const domain = extractDomain(url);

  let tier: SourceTier = 'unverified';
  let tierLabel = '未验证第三方网页';
  let verificationBadge = '普通第三方网络信息';
  let authorityScore = 50;
  let freshnessScore = 70;
  let firstHandScore = 60;

  // 1. 学术期刊与顶会官方源
  if (
    domain.includes('arxiv.org') ||
    domain.includes('nature.com') ||
    domain.includes('acm.org') ||
    domain.includes('ieee.org') ||
    domain.includes('sciencedirect.com') ||
    domain.includes('biorxiv.org')
  ) {
    tier = 'academic';
    tierLabel = '顶会/期刊一手学术认证';
    verificationBadge = 'CCF/SCI 权威学术源 98分';
    authorityScore = 98;
    freshnessScore = 85;
    firstHandScore = 95;
  }
  // 2. 官方主干代码仓库与开发者标准文档
  else if (
    domain.includes('github.com') ||
    domain.includes('githubusercontent.com') ||
    domain.includes('docs.') ||
    domain.includes('developer.') ||
    domain.includes('nodejs.org') ||
    domain.includes('python.org') ||
    domain.includes('rust-lang.org')
  ) {
    tier = 'official_code';
    tierLabel = '官方主干代码与标准文档';
    verificationBadge = '官方主分支/标准规范 94分';
    authorityScore = 94;
    freshnessScore = 92;
    firstHandScore = 92;
  }
  // 3. 监管备案与权威金融财报一手源
  else if (
    domain.includes('sec.gov') ||
    domain.includes('bloomberg.com') ||
    domain.includes('reuters.com') ||
    domain.includes('wsj.com') ||
    domain.includes('hkex.com.hk') ||
    domain.includes('sse.com.cn')
  ) {
    tier = 'sec_finance';
    tierLabel = '监管备案与权威一手财报';
    verificationBadge = '官方财报/监管备案 96分';
    authorityScore = 96;
    freshnessScore = 90;
    firstHandScore = 95;
  }
  // 4. 主流一手科技官方媒体
  else if (
    domain.includes('techcrunch.com') ||
    domain.includes('theverge.com') ||
    domain.includes('wired.com') ||
    domain.includes('arstechnica.com')
  ) {
    tier = 'tech_media';
    tierLabel = '主流科技一手报道';
    verificationBadge = '主流科技原创新闻 82分';
    authorityScore = 82;
    freshnessScore = 88;
    firstHandScore = 80;
  }
  // 5. 社区交流与个人博客衍生解读
  else if (
    domain.includes('zhihu.com') ||
    domain.includes('reddit.com') ||
    domain.includes('medium.com') ||
    domain.includes('dev.to') ||
    domain.includes('stackoverflow.com')
  ) {
    tier = 'community';
    tierLabel = '社区讨论与衍生解读';
    verificationBadge = '社区衍生讨论 68分';
    authorityScore = 65;
    freshnessScore = 75;
    firstHandScore = 62;
  }

  // 评估信噪比：全文正文高信噪比 vs 截断摘要
  const signalToNoiseScore = isFullText ? 92 : 45;

  // 评估一手性：若存在 AI 二次改写/营销号包装，大幅扣减一手真实性
  if (hasAiRewrite) {
    firstHandScore = Math.max(30, firstHandScore - 35);
  }

  // 加权综合计算 100 分综合得分
  const compositeScore = Math.round(
    authorityScore * 0.4 +
      freshnessScore * 0.2 +
      signalToNoiseScore * 0.2 +
      firstHandScore * 0.2
  );

  return {
    authorityScore,
    freshnessScore,
    signalToNoiseScore,
    firstHandScore,
    compositeScore,
    tier,
    tierLabel,
    verificationBadge,
  };
}

/**
 * 格式化网络载荷大小
 */
export function formatPayloadBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * 格式化网络链路耗时
 */
export function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${ms} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * 获取 100 分等级色彩与视觉标签
 */
export function getScoreTierBadgeColor(score: number): {
  bg: string;
  text: string;
  border: string;
  dotColor: string;
} {
  if (score >= 90) {
    return {
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-300',
      border: 'border-emerald-500/30',
      dotColor: 'bg-emerald-400',
    };
  }
  if (score >= 75) {
    return {
      bg: 'bg-indigo-500/10',
      text: 'text-indigo-300',
      border: 'border-indigo-500/30',
      dotColor: 'bg-indigo-400',
    };
  }
  if (score >= 60) {
    return {
      bg: 'bg-amber-500/10',
      text: 'text-amber-300',
      border: 'border-amber-500/30',
      dotColor: 'bg-amber-400',
    };
  }
  return {
    bg: 'bg-rose-500/10',
    text: 'text-rose-300',
    border: 'border-rose-500/30',
    dotColor: 'bg-rose-400',
  };
}

/**
 * 汇总多条链路请求与证据项，构建全透明检索审计会话
 */
export function summarizeSearchAuditSession(
  parentMessageId: string,
  traces: SubQueryTrace[],
  citations: AuditCitationItem[]
): SearchAuditSession {
  const totalLatencyMs = traces.reduce((acc, curr) => acc + curr.latencyMs, 0);
  const totalPayloadBytes = traces.reduce((acc, curr) => acc + curr.payloadBytes, 0);

  const averageQualityScore =
    citations.length > 0
      ? Math.round(
          citations.reduce(
            (acc, curr) => acc + curr.qualityMatrix.compositeScore,
            0
          ) / citations.length
        )
      : 80;

  return {
    auditSessionId: `audit-${parentMessageId.slice(-6)}-${Date.now().toString(36)}`,
    parentMessageId,
    totalLatencyMs,
    totalPayloadBytes,
    averageQualityScore,
    traces,
    citations,
    createdAt: Date.now(),
  };
}
