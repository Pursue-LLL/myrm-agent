import {
  AuthoritativeFactRecord,
  EnrichedPresentationResult,
  EnrichedUiCardItem,
  EnrichmentAuditLog,
  ModelJudgmentInput,
} from './uiEnrichmentTypes';

/**
 * 校验并脱敏清洗模型文本中的货币符号与星期/时间冲突
 */
export function sanitizeNoteCurrencyAndTemporalConflict(
  note: string,
  fact: AuthoritativeFactRecord,
): {
  sanitizedNote: string;
  currencyModified: boolean;
  temporalModified: boolean;
} {
  let text = note;
  let currencyModified = false;
  let temporalModified = false;

  // 1. 币种冲突自适应校准 (如真实为 CNY，模型说 $xx 或 USD)
  if (fact.officialCurrency === 'CNY') {
    if (text.includes('$') || text.includes('USD') || text.includes('美元')) {
      currencyModified = true;
      text = text
        .replace(/\$\s*(\d+(?:\.\d+)?)/g, '¥$1')
        .replace(/(\d+(?:\.\d+)?)\s*USD/gi, '¥$1')
        .replace(/(\d+(?:\.\d+)?)\s*美元/g, '¥$1');
    }
  } else if (fact.officialCurrency === 'USD') {
    if (text.includes('¥') || text.includes('CNY') || text.includes('元')) {
      currencyModified = true;
      text = text
        .replace(/¥\s*(\d+(?:\.\d+)?)/g, '$$$1')
        .replace(/(\d+(?:\.\d+)?)\s*CNY/gi, '$$$1')
        .replace(/(\d+(?:\.\d+)?)\s*元/g, '$$$1');
    }
  }

  // 2. 星期与生效日期冲突校准
  if (fact.verifiedWeekday) {
    const wrongWeekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'].filter(
      (w) => !w.includes(fact.verifiedWeekday ?? ''),
    );

    for (const wrong of wrongWeekdays) {
      if (text.includes(wrong)) {
        temporalModified = true;
        text = text.replaceAll(wrong, fact.verifiedWeekday);
      }
    }
  }

  return {
    sanitizedNote: text,
    currencyModified,
    temporalModified,
  };
}

let enrichSeq = 0;

/**
 * 服务端/门禁层事实全量 Join 引擎 (Zero-Model-Authored Data & Drop-and-Note)
 */
export function enrichModelJudgmentsWithAuthoritativeFacts(
  judgments: ModelJudgmentInput[],
  factStore: Record<string, AuthoritativeFactRecord>,
  presentationId?: string,
): EnrichedPresentationResult {
  enrichSeq += 1;
  const pId = presentationId ?? `enriched-pres-${Date.now()}-${enrichSeq}`;

  const enrichedItems: EnrichedUiCardItem[] = [];
  const droppedUnknownIds: string[] = [];
  const auditNotes: string[] = [];
  let currencyFixedCount = 0;
  let temporalFixedCount = 0;

  let currentRank = 1;

  for (const judgment of judgments) {
    const fact = factStore[judgment.id];

    // 无溯源 ID 自动降级与静默移除 (Drop-and-Note Degradation)
    if (!fact) {
      droppedUnknownIds.push(judgment.id);
      auditNotes.push(
        `[溯源拦截] 模型推荐的 ID 「${judgment.id}」在权威事实库中无有效记录，已自动移出卡片`,
      );
      continue;
    }

    // 跨模态币种与时间冲突清洗
    const rawNote = judgment.userNote?.trim() ?? '';
    const { sanitizedNote, currencyModified, temporalModified } =
      sanitizeNoteCurrencyAndTemporalConflict(rawNote, fact);

    if (currencyModified) {
      currencyFixedCount += 1;
      auditNotes.push(
        `[币种对齐] ID 「${judgment.id}」模型文本币种与系统权威定价币种 (${fact.officialCurrency}) 冲突，已自动校准`,
      );
    }
    if (temporalModified) {
      temporalFixedCount += 1;
      auditNotes.push(
        `[时间对齐] ID 「${judgment.id}」模型文本生效时间与系统真实核实星期 (${fact.verifiedWeekday}) 冲突，已自动自洽校准`,
      );
    }

    enrichedItems.push({
      id: fact.id,
      officialTitle: fact.officialTitle,
      officialPrice: fact.officialPrice,
      officialCurrency: fact.officialCurrency,
      stockStatus: fact.stockStatus,
      sanitizedNote,
      comparisonHighlight: judgment.comparisonHighlight,
      rank: currentRank,
      isEnriched: true,
    });

    currentRank += 1;
  }

  const auditLog: EnrichmentAuditLog = {
    totalRequested: judgments.length,
    enrichedCount: enrichedItems.length,
    droppedUnknownIds,
    currencyFixedCount,
    temporalFixedCount,
    auditNotes,
  };

  return {
    presentationId: pId,
    items: enrichedItems,
    auditLog,
    createdAt: Date.now(),
  };
}
