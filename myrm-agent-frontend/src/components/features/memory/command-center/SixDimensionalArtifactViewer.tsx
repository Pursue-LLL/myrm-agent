/**
 * [INPUT]
 * @/services/memory/autoMemoryConsolidation::SixDimensionalMemoryArtifactDTO
 * lucide-react::FolderGit2, Tag, UserCheck, BookOpen, AlertTriangle, Wrench, CheckCircle2
 *
 * [OUTPUT]
 * SixDimensionalArtifactViewer: Structured visual inspector for 6D memory artifact.
 *
 * [POS]
 * Visual inspector component for Item 123 auto-consolidation studio.
 * Strict typing: No `any`. Single file < 300 lines.
 */

import React from 'react';
import {
  FolderGit2,
  Tag,
  UserCheck,
  BookOpen,
  AlertTriangle,
  Wrench,
  CheckCircle2,
} from 'lucide-react';
import type { SixDimensionalMemoryArtifactDTO } from '@/services/memory/autoMemoryConsolidation';

interface SixDimensionalArtifactViewerProps {
  artifact: SixDimensionalMemoryArtifactDTO | null;
}

export const SixDimensionalArtifactViewer: React.FC<SixDimensionalArtifactViewerProps> = ({
  artifact,
}) => {
  if (!artifact) {
    return (
      <section
        aria-label="六维结构化记忆切片状态"
        className="p-8 text-center border border-dashed border-border/60 rounded-lg bg-secondary/10"
      >
        <p className="text-sm font-medium text-muted-foreground">
          暂无已沉淀的六维结构化记忆切片
        </p>
        <p className="text-xs text-muted-foreground/80 mt-1">
          当会话通过闲置检测、轮数增益与预算保护三道门禁后，后台将自适应归纳六维切片。
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="六维结构化记忆切片全景看板"
      className="space-y-4 bg-background/50 border border-border/40 p-4 rounded-lg"
    >
      {/* 头部元数据 */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-border/30">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          <span className="font-semibold text-sm text-foreground">
            六维结构化记忆切片 ({artifact.artifact_id})
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>会话: {artifact.session_id}</span>
          <span>·</span>
          <span>提炼消耗: {artifact.token_cost} Tokens</span>
        </div>
      </div>

      {/* 综合摘要 */}
      <div className="p-2.5 rounded bg-secondary/30 border border-border/30 text-xs text-foreground/90 leading-relaxed">
        <span className="font-semibold text-primary mr-1.5">[综合摘要]</span>
        {artifact.summary_digest}
      </div>

      {/* 六维切片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-xs">
        {/* 1. 工作目录环境 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <FolderGit2 className="w-3.5 h-3.5 text-blue-500" />
            ① 工作目录上下文 (Working Directory)
          </div>
          <code className="block p-1.5 rounded bg-muted/60 text-[11px] text-muted-foreground font-mono break-all">
            {artifact.working_directory}
          </code>
        </div>

        {/* 2. 关键技术主题词 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <Tag className="w-3.5 h-3.5 text-purple-500" />
            ② 核心技术主题词 (Key Topics)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {artifact.key_topics.length > 0 ? (
              artifact.key_topics.map((topic, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 text-[11px]"
                >
                  #{topic}
                </span>
              ))
            ) : (
              <span className="text-muted-foreground text-[11px]">无提取主题词</span>
            )}
          </div>
        </div>

        {/* 3. 用户个性偏好 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <UserCheck className="w-3.5 h-3.5 text-emerald-500" />
            ③ 用户个性偏好与规范 (User Preferences)
          </div>
          {artifact.user_preferences.length > 0 ? (
            <ul className="space-y-1 list-disc list-inside text-muted-foreground text-[11px]">
              {artifact.user_preferences.map((pref, idx) => (
                <li key={idx} className="leading-snug">
                  {pref}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-[11px]">未检测到显著个性习惯</p>
          )}
        </div>

        {/* 4. 可复用领域经验 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
            ④ 可复用工程经验 (Reusable Knowledge)
          </div>
          {artifact.reusable_domain_knowledge.length > 0 ? (
            <ul className="space-y-1 list-disc list-inside text-muted-foreground text-[11px]">
              {artifact.reusable_domain_knowledge.map((k, idx) => (
                <li key={idx} className="leading-snug">
                  {k}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-[11px]">未提取到通用领域方案</p>
          )}
        </div>

        {/* 5. 失败教训与排错反思 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            ⑤ 踩坑教训与自愈反思 (Failure Lessons)
          </div>
          {artifact.failure_lessons.length > 0 ? (
            <ul className="space-y-1 list-disc list-inside text-amber-600/90 dark:text-amber-400/90 text-[11px]">
              {artifact.failure_lessons.map((lesson, idx) => (
                <li key={idx} className="leading-snug">
                  {lesson}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-[11px]">本次会话未遭遇故障陷阱</p>
          )}
        </div>

        {/* 6. 工具调用习惯 */}
        <div className="p-3 rounded-lg border border-border/30 bg-card/60 space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <Wrench className="w-3.5 h-3.5 text-cyan-500" />
            ⑥ 工具调用特征与行为习惯 (Tool Habits)
          </div>
          {artifact.tool_calling_patterns.length > 0 ? (
            <div className="space-y-1 text-muted-foreground text-[11px]">
              {artifact.tool_calling_patterns.map((pat, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 shrink-0" />
                  <span>{pat}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-[11px]">未记录到工具交互轨迹</p>
          )}
        </div>
      </div>
    </section>
  );
};
