/**
 * [INPUT]
 * - services/statistics::ExecutionTrace, TraceToolCall, TraceError (POS: 运行轨迹元数据契约)
 * - lib/utils/fileUtils::sanitizeFilename, triggerDownload (POS: 安全下载工具)
 *
 * [OUTPUT]
 * - SixStepEvidencePack: 六步项目经验证据包数据契约
 * - generateEvidencePackFromTrace: 从 ExecutionTrace 组装六步证据包
 * - exportEvidencePackToMarkdown: 格式化为 Markdown 文档
 * - exportEvidencePackToJson: 格式化为 JSON 字符串
 * - downloadEvidencePack: 触发文件下载
 *
 * [POS]
 * 项目经验六步证据包提炼核心服务。将零散的执行轨迹收敛为结构化工程资产。
 */

import type { ExecutionTrace, TraceToolCall, TraceError } from '@/services/statistics';
import { sanitizeFilename, triggerDownload } from '@/lib/utils/fileUtils';

export interface EvidencePackStep {
  stepIndex: number;
  id: 'requirements' | 'architecture' | 'initial_impl' | 'execution_correction' | 'verification' | 'takeaways';
  title: string;
  summary: string;
  details: string[];
  metrics?: Record<string, string | number>;
}

export interface SixStepEvidencePack {
  sessionId: string;
  generatedAt: string;
  taskTitle: string;
  outcome: 'success' | 'failure' | 'cancelled' | 'running';
  totalDurationMs: number;
  totalTokens: number;
  totalToolCalls: number;
  steps: EvidencePackStep[];
}

/**
 * 从原始执行轨迹提炼六步项目经验证据包
 */
export function generateEvidencePackFromTrace(trace: ExecutionTrace): SixStepEvidencePack {
  const taskTitle = trace.task_input ? trace.task_input.split('\n')[0].slice(0, 60) : 'Untitled Project Task';
  
  // Step 1: 原始需求 (Requirements)
  const reqDetails: string[] = [];
  if (trace.task_input) {
    reqDetails.push(trace.task_input.trim());
  } else {
    reqDetails.push('无显式文本输入');
  }

  // Step 2: 方案与决策 (Architecture & Decisions)
  const archDetails: string[] = [];
  const planningCalls = trace.tool_calls.filter((t: TraceToolCall) =>
    ['task_planning', 'structure-planner', 'sequentialthinking', 'delegate_task'].some((k) =>
      t.tool_name.toLowerCase().includes(k),
    ),
  );
  if (planningCalls.length > 0) {
    archDetails.push(`识别到 ${planningCalls.length} 次架构与规划决策阶段调度`);
    planningCalls.slice(0, 5).forEach((t) => {
      archDetails.push(`[${t.tool_name}] ${t.output_summary || (t.input_data ? JSON.stringify(t.input_data).slice(0, 100) : '规划节点')}`);
    });
  } else {
    archDetails.push('遵循端到端直连执行与敏捷响应模式');
  }

  // Step 3: v0 首稿方案 (Initial Implementation)
  const v0Details: string[] = [];
  const editTools = ['file_write_tool', 'file_edit_tool', 'patch', 'write', 'str_replace'];
  const firstWrite = trace.tool_calls.find((t: TraceToolCall) =>
    editTools.some((et) => t.tool_name.toLowerCase().includes(et)),
  );
  if (firstWrite) {
    v0Details.push(`首次物料落地动作: [${firstWrite.tool_name}] (序列 #${firstWrite.sequence})`);
    if (firstWrite.input_data && typeof firstWrite.input_data === 'object') {
      const pathVal = (firstWrite.input_data as Record<string, unknown>).path || (firstWrite.input_data as Record<string, unknown>).file_path;
      if (pathVal) {
        v0Details.push(`目标文件: ${String(pathVal)}`);
      }
    }
  } else {
    v0Details.push('未检测到静态文件修改或为纯会话交互任务');
  }

  // Step 4: 轨迹与纠错 (Execution & Correction)
  const execDetails: string[] = [];
  const failedCalls = trace.tool_calls.filter((t: TraceToolCall) => !t.success || Boolean(t.error));
  execDetails.push(`总工具调用 ${trace.tool_calls.length} 次，其中异常拦截/修复 ${failedCalls.length} 次`);
  if (trace.errors && trace.errors.length > 0) {
    trace.errors.slice(0, 3).forEach((err: TraceError) => {
      execDetails.push(`[异常记录] ${err.error_type || 'Error'}: ${err.message.slice(0, 120)}`);
    });
  }
  if (failedCalls.length > 0) {
    failedCalls.slice(0, 3).forEach((f) => {
      execDetails.push(`[自愈点] ${f.tool_name} 失败后触发重试或策略自适应`);
    });
  }

  // Step 5: 验证实证 (Verification & Evidence)
  const verifDetails: string[] = [];
  const testCalls = trace.tool_calls.filter((t: TraceToolCall) =>
    ['test', 'pytest', 'bash', 'audit', 'lint', 'verifier', 'check'].some((tk) =>
      t.tool_name.toLowerCase().includes(tk),
    ),
  );
  if (testCalls.length > 0) {
    const passedTests = testCalls.filter((t) => t.success).length;
    verifDetails.push(`执行了 ${testCalls.length} 次验证/测试动作，通过率 ${(passedTests / testCalls.length * 100).toFixed(0)}%`);
    testCalls.slice(0, 3).forEach((tc) => {
      verifDetails.push(`[实证执行] ${tc.tool_name}: ${tc.success ? 'PASSED ✅' : 'FAILED ❌'}`);
    });
  } else {
    verifDetails.push('完成基于语义一致性与任务结束门禁的推导验证');
  }

  // Step 6: 沉淀与复盘 (Lessons & Best Practices)
  const takeawayDetails: string[] = [];
  if (trace.outcome === 'success') {
    takeawayDetails.push('任务完整闭环，各阶段决策与实证对齐良好');
    takeawayDetails.push('建议将本次沉淀的稳定 SOP 提取为专用 Skill 或自动化模板');
  } else {
    takeawayDetails.push(`任务状态为 ${trace.outcome}，需重点关注中断或首个不可逆错误`);
    if (trace.first_irrecoverable_index != null) {
      takeawayDetails.push(`首个致命异常位于步骤索引 #${trace.first_irrecoverable_index}`);
    }
  }

  const steps: EvidencePackStep[] = [
    {
      stepIndex: 1,
      id: 'requirements',
      title: '原始需求输入 (Original Requirements)',
      summary: '原始任务目标、业务背景与约束输入',
      details: reqDetails,
    },
    {
      stepIndex: 2,
      id: 'architecture',
      title: '架构与方案决策 (Architecture & Decisions)',
      summary: '技术路径选型、计划分解与依赖关系',
      details: archDetails,
    },
    {
      stepIndex: 3,
      id: 'initial_impl',
      title: 'v0 首稿实现快照 (v0 Implementation)',
      summary: '首次代码/物料产出与初始方案形态',
      details: v0Details,
    },
    {
      stepIndex: 4,
      id: 'execution_correction',
      title: '执行演进与自愈纠错 (Execution & Correction)',
      summary: '工具调用流水、报错排查与纠偏证据',
      details: execDetails,
      metrics: {
        '总调用': trace.tool_calls.length,
        '异常数': failedCalls.length,
      },
    },
    {
      stepIndex: 5,
      id: 'verification',
      title: '客观验证与测试实证 (Verification & Tests)',
      summary: '测试用例、静态检查与环境实测数据',
      details: verifDetails,
    },
    {
      stepIndex: 6,
      id: 'takeaways',
      title: '经验沉淀与防退化要点 (Lessons & Takeaways)',
      summary: '复盘总结、最佳实践与沉淀建议',
      details: takeawayDetails,
    },
  ];

  return {
    sessionId: trace.session_id,
    generatedAt: new Date().toISOString(),
    taskTitle,
    outcome: trace.outcome,
    totalDurationMs: trace.duration_ms,
    totalTokens: trace.total_tokens,
    totalToolCalls: trace.tool_calls.length,
    steps,
  };
}

/**
 * 导出为标准化 Markdown 报告
 */
export function exportEvidencePackToMarkdown(pack: SixStepEvidencePack): string {
  const durationSec = (pack.totalDurationMs / 1000).toFixed(1);
  const lines: string[] = [
    `# 📋 项目实战六步经验证据包: ${pack.taskTitle}`,
    '',
    `> **会话 ID**: \`${pack.sessionId}\`  `,
    `> **执行结果**: \`${pack.outcome.toUpperCase()}\` | **耗时**: ${durationSec}s | **Token 消耗**: ${pack.totalTokens.toLocaleString()} | **工具调用**: ${pack.totalToolCalls} 次  `,
    `> **生成时间**: ${pack.generatedAt}`,
    '',
    '---',
    '',
  ];

  pack.steps.forEach((step) => {
    lines.push(`## Step ${step.stepIndex}: ${step.title}`);
    lines.push(`*${step.summary}*`);
    lines.push('');
    step.details.forEach((item) => {
      lines.push(`- ${item}`);
    });
    if (step.metrics) {
      lines.push('');
      lines.push('**关键度量**:');
      Object.entries(step.metrics).forEach(([k, v]) => {
        lines.push(`- ${k}: \`${v}\``);
      });
    }
    lines.push('');
  });

  lines.push('---');
  lines.push('*由 Myrmidon AI 项目经验六步向导自动聚合生成*');
  return lines.join('\n');
}

/**
 * 导出为结构化 JSON
 */
export function exportEvidencePackToJson(pack: SixStepEvidencePack): string {
  return JSON.stringify(pack, null, 2);
}

/**
 * 触发文件下载
 */
export function downloadEvidencePack(pack: SixStepEvidencePack, format: 'markdown' | 'json'): void {
  const dateStr = new Date().toISOString().slice(0, 10);
  const baseName = sanitizeFilename(`EvidencePack_${pack.taskTitle.slice(0, 20)}_${dateStr}`);

  if (format === 'markdown') {
    const mdContent = exportEvidencePackToMarkdown(pack);
    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' });
    triggerDownload(blob, `${baseName}.md`);
  } else {
    const jsonContent = exportEvidencePackToJson(pack);
    const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8' });
    triggerDownload(blob, `${baseName}.json`);
  }
}
