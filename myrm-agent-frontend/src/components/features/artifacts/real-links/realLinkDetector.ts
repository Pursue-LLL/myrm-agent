import type {
  DetectedLinkEntity,
  LinkCategory,
  LinkVerificationStatus,
} from './realLinkTypes';

interface EntityKnowledgeRule {
  keywords: string[];
  category: LinkCategory;
  entityName: string;
  realUrl: string;
}

const AUTHORITATIVE_ENTITY_RULES: EntityKnowledgeRule[] = [
  {
    keywords: ['投递', '校招', '招聘', '加入我们', '简历', '岗位', '职位'],
    category: 'recruitment',
    entityName: '三只松鼠官方校园招聘门户',
    realUrl: 'https://careers.3squirrels.com/campus',
  },
  {
    keywords: ['购买', '下单', '特惠', '天猫', '京东', '官方商城', '选购', '礼包', '零食', '坚果', '商城'],
    category: 'commerce',
    entityName: '三只松鼠天猫官方旗舰店',
    realUrl: 'https://sanzhisongshu.tmall.com',
  },
  {
    keywords: ['客服', '在线咨询', '人工服务', '投诉', '售后', '帮助'],
    category: 'customer_service',
    entityName: '品牌官方 7×24h 智能客服中心',
    realUrl: 'https://help.3squirrels.com/service/chat',
  },
  {
    keywords: ['文档', '开发者', 'API', 'SDK', '白皮书', '开发指南'],
    category: 'documentation',
    entityName: 'Myrmidon 开发者开放平台文档',
    realUrl: 'https://docs.myrm.io/developer/api-reference',
  },
  {
    keywords: ['微博', '公众号', '关注我们', 'B站', '抖音'],
    category: 'social_media',
    entityName: '企业官方认证社交矩阵通道',
    realUrl: 'https://weibo.com/3squirrels',
  },
];

export function isPlaceholderLink(href: string): boolean {
  const normalized = href.trim().toLowerCase();
  if (
    normalized === '#' ||
    normalized === '' ||
    normalized.startsWith('javascript:void') ||
    normalized.includes('example.com') ||
    normalized.includes('placeholder') ||
    normalized.includes('your-domain') ||
    normalized === 'about:blank'
  ) {
    return true;
  }
  return false;
}

export function inferCategoryAndEntity(anchorText: string): {
  category: LinkCategory;
  targetEntityName?: string;
  resolvedRealUrl?: string;
} {
  const lower = anchorText.toLowerCase();

  for (const rule of AUTHORITATIVE_ENTITY_RULES) {
    for (const kw of rule.keywords) {
      if (lower.includes(kw.toLowerCase())) {
        return {
          category: rule.category,
          targetEntityName: rule.entityName,
          resolvedRealUrl: rule.realUrl,
        };
      }
    }
  }

  return { category: 'general' };
}

export function scanLinksFromHtml(html: string): DetectedLinkEntity[] {
  const linkRegex = /<a\s+(?:[^>]*?\s+)?href=["']([^"']*)["'][^>]*>([\s\S]*?)<\/a>/gi;
  const results: DetectedLinkEntity[] = [];
  let match: RegExpExecArray | null = linkRegex.exec(html);
  let index = 1;

  while (match !== null) {
    const rawHref = match[1] ?? '';
    const rawAnchorText = (match[2] ?? '').replace(/<[^>]+>/g, '').trim();
    const isFake = isPlaceholderLink(rawHref);
    const { category, targetEntityName, resolvedRealUrl } = inferCategoryAndEntity(rawAnchorText);

    let status: LinkVerificationStatus = 'unverified';
    let reason = '真实公网外部链接，待连通性自检';

    if (isFake) {
      status = 'placeholder_detected';
      reason = '检测到 Demo 占位假链 (href="#" 或 example.com)，无法商用跳转';
    } else if (rawHref.startsWith('https://') || rawHref.startsWith('http://')) {
      status = 'aligned';
      reason = '已对齐有效公网链接';
    }

    results.push({
      id: `link_ent_${index}_${Math.random().toString(36).substring(2, 6)}`,
      originalHref: rawHref,
      anchorText: rawAnchorText || '未命名的超链接',
      category,
      status,
      targetEntityName,
      resolvedRealUrl,
      confidenceScore: isFake ? 0.95 : 0.8,
      reason,
    });

    index += 1;
    match = linkRegex.exec(html);
  }

  return results;
}

export function replaceLinksInHtml(html: string, links: DetectedLinkEntity[]): string {
  let updatedHtml = html;

  for (const link of links) {
    if (link.status === 'aligned' && link.resolvedRealUrl) {
      // 匹配原 href 对应的链接并安全替换
      const escapedOld = link.originalHref.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const escapedAnchor = link.anchorText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const pattern = new RegExp(
        `(<a\\s+(?:[^>]*?\\s+)?href=["'])${escapedOld}(["'][^>]*>[\\s\\S]*?${escapedAnchor}[\\s\\S]*?<\\/a>)`,
        'gi'
      );
      updatedHtml = updatedHtml.replace(pattern, `$1${link.resolvedRealUrl}$2`);
    }
  }

  return updatedHtml;
}
