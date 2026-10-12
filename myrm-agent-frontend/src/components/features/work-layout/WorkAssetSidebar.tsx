'use client';

/**
 * [INPUT]
 * - useWorkLayoutStore from @/store/useWorkLayoutStore
 * - useTranslations from next-intl (namespace: 'workLayout')
 *
 * [OUTPUT]
 * - WorkAssetSidebar: Four-dimension work assets sidebar (Tasks, Skills, Connectors, Partners)
 *
 * [POS]
 * Work Mode dedicated assets navigation and status board (Item 26).
 * Single file < 380 lines. Zero `any` types. Zero native emoji.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  ListTodo,
  Wrench,
  Link2,
  Users,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  CheckSquare,
  Square,
  Activity,
  ShieldCheck,
  Play,
  Search,
} from 'lucide-react';
import {
  useWorkLayoutStore,
  type WorkSidebarTab,
  type WorkTaskItem,
} from '@/store/useWorkLayoutStore';

interface SkillItem {
  id: string;
  name: string;
  description: string;
  category: string;
}

interface ConnectorItem {
  id: string;
  name: string;
  protocol: string;
  status: 'running' | 'standby';
}

interface PartnerItem {
  id: string;
  name: string;
  role: string;
  sandbox: string;
}

const DEFAULT_SKILLS: SkillItem[] = [
  { id: 'sk-1', name: 'Code Interpreter', description: 'Sandboxed Python & shell runtime', category: 'Runtime' },
  { id: 'sk-2', name: 'Web Navigator', description: 'Real browser search & crawl engine', category: 'Web' },
  { id: 'sk-3', name: 'Git Workflow', description: 'Local branch, diff and commit assistant', category: 'DevOps' },
];

const DEFAULT_CONNECTORS: ConnectorItem[] = [
  { id: 'conn-1', name: 'GitHub Integration', protocol: 'REST / GraphQL', status: 'running' },
  { id: 'conn-2', name: 'PostgreSQL Bridge', protocol: 'MCP Postgres', status: 'running' },
  { id: 'conn-3', name: 'Local PTY Host', protocol: 'Tauri Shell', status: 'standby' },
];

const DEFAULT_PARTNERS: PartnerItem[] = [
  { id: 'part-1', name: 'Architect Agent', role: 'System design & ADR review', sandbox: 'sbx-arch-01' },
  { id: 'part-2', name: 'Code Reviewer', role: 'Static lint & security scanning', sandbox: 'sbx-rev-02' },
  { id: 'part-3', name: 'QA Verifier', role: 'Test suite & contract check', sandbox: 'sbx-qa-03' },
];

export function WorkAssetSidebar() {
  const t = useTranslations('workLayout');
  const activeTab = useWorkLayoutStore((s) => s.workSidebarTab);
  const setActiveTab = useWorkLayoutStore((s) => s.setWorkSidebarTab);
  const isCollapsed = useWorkLayoutStore((s) => s.isSidebarCollapsed);
  const toggleCollapsed = useWorkLayoutStore((s) => s.toggleSidebarCollapsed);
  const tasks = useWorkLayoutStore((s) => s.tasks);
  const activeTaskId = useWorkLayoutStore((s) => s.activeTaskId);
  const setActiveTaskId = useWorkLayoutStore((s) => s.setActiveTaskId);
  const toggleSubtask = useWorkLayoutStore((s) => s.toggleSubtask);

  const [skillSearch, setSkillSearch] = useState<string>('');

  const activeTask = tasks.find((t) => t.id === activeTaskId) || tasks[0];

  const filteredSkills = DEFAULT_SKILLS.filter(
    (s) =>
      s.name.toLowerCase().includes(skillSearch.toLowerCase()) ||
      s.category.toLowerCase().includes(skillSearch.toLowerCase()),
  );

  const handleInvokeSkill = (skill: SkillItem) => {
    window.dispatchEvent(
      new CustomEvent('myrm:insert-to-chat', {
        detail: { text: `/skill run ${skill.name}` },
      }),
    );
  };

  if (isCollapsed) {
    return (
      <aside
        aria-label={t('sidebarExpand')}
        className="w-12 h-full border-r border-border/60 bg-card/60 flex flex-col items-center py-3 select-none transition-all"
      >
        <button
          type="button"
          onClick={toggleCollapsed}
          title={t('sidebarExpand')}
          className="p-1.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors mb-4"
        >
          <ChevronRight className="w-4 h-4" />
        </button>

        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={() => {
              setActiveTab('tasks');
              toggleCollapsed();
            }}
            title={t('tabTasks')}
            className={`p-2 rounded-xl transition-colors ${
              activeTab === 'tasks' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            <ListTodo className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('skills');
              toggleCollapsed();
            }}
            title={t('tabSkills')}
            className={`p-2 rounded-xl transition-colors ${
              activeTab === 'skills' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            <Wrench className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('connectors');
              toggleCollapsed();
            }}
            title={t('tabConnectors')}
            className={`p-2 rounded-xl transition-colors ${
              activeTab === 'connectors' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            <Link2 className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('partners');
              toggleCollapsed();
            }}
            title={t('tabPartners')}
            className={`p-2 rounded-xl transition-colors ${
              activeTab === 'partners' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            <Users className="w-4 h-4" />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside
      aria-label="Work Assets Sidebar"
      className="w-72 md:w-80 h-full border-r border-border/60 bg-card/60 flex flex-col select-none transition-all overflow-hidden"
    >
      {/* Header Tabs */}
      <div className="p-2 border-b border-border/60 flex items-center justify-between gap-1 bg-muted/30">
        <div className="flex items-center gap-1 overflow-x-auto text-xs font-medium">
          <button
            type="button"
            onClick={() => setActiveTab('tasks')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              activeTab === 'tasks' ? 'bg-background text-primary shadow-xs font-semibold' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <ListTodo className="w-3.5 h-3.5" />
            <span>{t('tabTasks')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('skills')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              activeTab === 'skills' ? 'bg-background text-primary shadow-xs font-semibold' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Wrench className="w-3.5 h-3.5" />
            <span>{t('tabSkills')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('connectors')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              activeTab === 'connectors' ? 'bg-background text-primary shadow-xs font-semibold' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Link2 className="w-3.5 h-3.5" />
            <span>{t('tabConnectors')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('partners')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
              activeTab === 'partners' ? 'bg-background text-primary shadow-xs font-semibold' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>{t('tabPartners')}</span>
          </button>
        </div>

        <button
          type="button"
          onClick={toggleCollapsed}
          title={t('sidebarCollapse')}
          className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Body Area according to Tab */}
      <div className="flex-1 overflow-y-auto p-3 text-xs flex flex-col gap-3">
        {/* Tab 1: Tasks */}
        {activeTab === 'tasks' && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                {t('tasks.headerTitle')}
              </span>
              {tasks.map((task: WorkTaskItem) => {
                const isSelected = task.id === activeTask?.id;
                return (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => setActiveTaskId(task.id)}
                    className={`p-2.5 rounded-xl border text-left transition-all flex flex-col gap-1.5 ${
                      isSelected
                        ? 'border-primary/50 bg-primary/5 shadow-xs'
                        : 'border-border/60 bg-background/50 hover:bg-muted/40'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-semibold text-foreground truncate">{task.title}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-md font-mono ${
                          task.status === 'completed'
                            ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                            : task.status === 'in_progress'
                            ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                            : 'bg-muted text-muted-foreground'
                        }`}
                      >
                        {task.progressPercentage}%
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          task.status === 'completed' ? 'bg-emerald-500' : 'bg-primary'
                        }`}
                        style={{ width: `${task.progressPercentage}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Active Task Subtasks Checklist */}
            {activeTask && activeTask.subtasks.length > 0 && (
              <div className="p-3 rounded-xl bg-background/80 border border-border/70 flex flex-col gap-2 mt-1">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-primary" />
                  <span>{t('tasks.subtaskTitle')}</span>
                </span>
                <div className="flex flex-col gap-1.5">
                  {activeTask.subtasks.map((sub) => (
                    <button
                      key={sub.id}
                      type="button"
                      onClick={() => toggleSubtask(activeTask.id, sub.id)}
                      className="flex items-center gap-2 text-left hover:bg-muted/40 p-1 rounded-md transition-colors"
                    >
                      {sub.completed ? (
                        <CheckSquare className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      ) : (
                        <Square className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                      )}
                      <span
                        className={`truncate ${
                          sub.completed ? 'line-through text-muted-foreground' : 'text-foreground'
                        }`}
                      >
                        {sub.title}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Skills */}
        {activeTab === 'skills' && (
          <div className="flex flex-col gap-2.5">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <input
                type="search"
                value={skillSearch}
                onChange={(e) => setSkillSearch(e.target.value)}
                placeholder={t('skills.searchPlaceholder')}
                className="w-full pl-8 pr-2.5 py-1 text-xs rounded-lg bg-background border border-border/70 focus:outline-hidden focus:ring-1 focus:ring-primary"
              />
            </div>
            {filteredSkills.map((sk) => (
              <div
                key={sk.id}
                className="p-2.5 rounded-xl border border-border/60 bg-background/50 flex flex-col gap-1.5 hover:border-border transition-all"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">{sk.name}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground font-mono">
                    {sk.category}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground">{sk.description}</p>
                <button
                  type="button"
                  onClick={() => handleInvokeSkill(sk)}
                  className="flex items-center justify-center gap-1 mt-1 py-1 px-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-medium text-[11px]"
                >
                  <Play className="w-3 h-3" />
                  <span>{t('skills.triggerAction')}</span>
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Tab 3: Connectors */}
        {activeTab === 'connectors' && (
          <div className="flex flex-col gap-2.5">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              {t('connectors.headerTitle')}
            </span>
            {DEFAULT_CONNECTORS.map((c) => (
              <div
                key={c.id}
                className="p-2.5 rounded-xl border border-border/60 bg-background/50 flex items-center justify-between gap-2"
              >
                <div className="flex flex-col">
                  <span className="font-semibold text-foreground">{c.name}</span>
                  <span className="text-[10px] text-muted-foreground font-mono">{c.protocol}</span>
                </div>
                <span
                  className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium font-mono ${
                    c.status === 'running'
                      ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  <Activity className="w-2.5 h-2.5" />
                  <span>{c.status === 'running' ? t('connectors.statusConnected') : t('connectors.statusStandby')}</span>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Tab 4: Partners */}
        {activeTab === 'partners' && (
          <div className="flex flex-col gap-2.5">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              {t('partners.headerTitle')}
            </span>
            {DEFAULT_PARTNERS.map((p) => (
              <div
                key={p.id}
                className="p-2.5 rounded-xl border border-border/60 bg-background/50 flex flex-col gap-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">{p.name}</span>
                  <span className="text-[10px] text-primary font-mono flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-emerald-500" />
                    <span>{p.sandbox}</span>
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground">{p.role}</p>
                <span className="text-[10px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md inline-block self-start font-medium">
                  {t('partners.sandboxRunning')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
