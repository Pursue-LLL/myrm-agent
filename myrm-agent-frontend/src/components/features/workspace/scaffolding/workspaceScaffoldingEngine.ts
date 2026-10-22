import {
  FourZoneCategory,
  GeneratedScaffoldDoc,
  ProposedFileMove,
  ScaffoldingProposal,
} from './workspaceScaffoldingTypes';

/**
 * 识别用户自然语言中的工作区四区初始化意图
 */
export function parseScaffoldingIntent(utterance: string): boolean {
  const text = utterance.trim().toLowerCase();
  if (!text) {
    return false;
  }

  const hasScaffoldKeyword =
    text.includes('四区') ||
    text.includes('初始化') ||
    text.includes('整理项目') ||
    text.includes('整理文件夹') ||
    text.includes('规范目录') ||
    text.includes('规整');

  return hasScaffoldKeyword;
}

/**
 * 依据文件名后缀与命名语义，智能推导所属四区分区及只读保护属性
 */
export function inferFileZoneClassification(fileName: string): {
  zone: FourZoneCategory;
  isReadOnly: boolean;
  rationale: string;
} {
  const lower = fileName.toLowerCase();

  // 1. 01_raw_materials: 原始输入原件（只读不可改写）
  if (
    lower.endsWith('.pdf') ||
    lower.endsWith('.docx') ||
    lower.endsWith('.pptx') ||
    lower.endsWith('.xlsx') ||
    lower.endsWith('.jpg') ||
    lower.endsWith('.png') ||
    lower.includes('contract') ||
    lower.includes('invoice') ||
    lower.includes('合同') ||
    lower.includes('发票') ||
    lower.includes('原件')
  ) {
    return {
      zone: '01_raw_materials',
      isReadOnly: true,
      rationale: '作为客户输入或原始凭证依据，归入原件区并锁定只读保护',
    };
  }

  // 2. 02_process_drafts: 临时记录与过程草稿
  if (
    lower.endsWith('.tmp') ||
    lower.endsWith('.log') ||
    lower.includes('draft') ||
    lower.includes('note') ||
    lower.includes('memo') ||
    lower.includes('草稿') ||
    lower.includes('临时')
  ) {
    return {
      zone: '02_process_drafts',
      isReadOnly: false,
      rationale: '作为中间过程草稿与调试记录，归入过程区便于随时迭代',
    };
  }

  // 3. 04_deliverables: 导出交付物
  if (
    lower.includes('final') ||
    lower.includes('export') ||
    lower.includes('release') ||
    lower.includes('report') ||
    lower.includes('交付') ||
    lower.includes('最终版')
  ) {
    return {
      zone: '04_deliverables',
      isReadOnly: false,
      rationale: '作为交付成果物归档，方便客户查阅与验收',
    };
  }

  // 4. 03_content_bases: 默认归入内容底稿区
  return {
    zone: '03_content_bases',
    isReadOnly: false,
    rationale: '作为长期复用的核心内容底稿与工程规约',
  };
}

let proposalSeq = 0;

/**
 * 纯内存虚拟推演四区分区迁移方案，同时草拟 AGENTS.md 与 00_项目总览.md
 */
export function generateDefaultScaffoldingProposal(
  workspacePath: string,
  fileList: string[],
  utterance: string = '标准四区初始化',
): ScaffoldingProposal {
  proposalSeq += 1;
  const id = `scaffold-prop-${Date.now()}-${proposalSeq}`;

  const moves: ProposedFileMove[] = fileList.map((file) => {
    const classification = inferFileZoneClassification(file);
    const targetDir = classification.zone;
    return {
      sourcePath: `${workspacePath}/${file}`,
      fileName: file,
      targetZone: classification.zone,
      targetPath: `${workspacePath}/${targetDir}/${file}`,
      isReadOnly: classification.isReadOnly,
      rationale: classification.rationale,
    };
  });

  const generatedDocs: GeneratedScaffoldDoc[] = [
    {
      path: `${workspacePath}/AGENTS.md`,
      title: 'AGENTS.md（智能体行为规约与红线手册）',
      purpose: '明确禁止大模型擅自改动 01 原件，定义各分区协作边界',
      draftContent: `# AGENTS.md - 项目协同规约\n\n## 核心红线\n1. 严禁改动 01_raw_materials/ 目录下的任何原件。\n2. 中间过程与临时草稿集中写入 02_process_drafts/。\n3. 所有最终对外成果统一导出至 04_deliverables/。\n`,
    },
    {
      path: `${workspacePath}/00_项目总览.md`,
      title: '00_项目总览.md（动态目标与材料总览）',
      purpose: '集中展示项目初始化背景、原始输入清单与当前执行进展',
      draftContent: `# 00_项目总览\n\n- 工作区路径: ${workspacePath}\n- 初始化时间: ${new Date().toISOString()}\n- 原始文件总计: ${fileList.length} 项\n- 状态: 四区分区初始化待落盘\n`,
    },
  ];

  return {
    id,
    workspacePath,
    matchedUtterance: utterance,
    moves,
    generatedDocs,
    status: 'pending_review',
    createdAt: Date.now(),
  };
}

/**
 * 统计四区分区文件数量汇总
 */
export function summarizeScaffoldingProposal(
  proposal: ScaffoldingProposal,
): Record<FourZoneCategory, number> {
  const summary: Record<FourZoneCategory, number> = {
    '01_raw_materials': 0,
    '02_process_drafts': 0,
    '03_content_bases': 0,
    '04_deliverables': 0,
  };

  for (const move of proposal.moves) {
    if (summary[move.targetZone] !== undefined) {
      summary[move.targetZone] += 1;
    }
  }

  return summary;
}
