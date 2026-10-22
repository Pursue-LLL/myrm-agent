import React from 'react';
import {
  X,
  Bot,
  Sparkles,
  FileText,
  UserCheck,
  CheckCircle,
} from 'lucide-react';
import { useBotCreatorStudioStore } from './useBotCreatorStudioStore';
import { MasterInheritanceToggleCard } from './MasterInheritanceToggleCard';
import { CognitiveTieringSelector } from './CognitiveTieringSelector';
import { PixelMascotPicker } from './PixelMascotPicker';

export const VisualBotCreatorStudioModal: React.FC = () => {
  const {
    isOpen,
    form,
    masterAssets,
    availableMascots,
    closeStudio,
    updateFormField,
    toggleInheritance,
    toggleInheritanceOption,
    selectCognitiveTier,
    selectPixelMascot,
    generateAiAvatar,
    submitCreateBot,
  } = useBotCreatorStudioStore();

  if (!isOpen) {
    return null;
  }

  const handleCreate = async () => {
    await submitCreateBot();
  };

  return (
    <dialog
      open
      aria-label="智能体可视化极速新建工坊"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm border-none w-full h-full max-w-none max-h-none m-0"
    >
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl border border-slate-700/80 bg-slate-900/95 shadow-2xl overflow-hidden">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 px-6 bg-slate-950/60">
          <div className="flex items-center space-x-2.5">
            <div className="rounded-lg bg-blue-500/10 p-2 text-blue-400">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-100 flex items-center space-x-2">
                <span>智能体可视化极速新建工坊</span>
                <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                  New Agent Studio
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">
                支持一键继承主配置、大脑认知分级推荐与专属像素宠物装配
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeStudio}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label="关闭新建工坊"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {/* Scrollable Form Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Section 1: 基础人设与定位 */}
          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3.5">
            <div className="flex items-center space-x-1.5 border-b border-slate-800 pb-2">
              <UserCheck className="h-4 w-4 text-sky-400" />
              <span className="text-xs font-semibold text-slate-100">基本信息与人设定位</span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="bot-name" className="block text-[11px] font-medium text-slate-300 mb-1">
                  智能体名称 <span className="text-rose-400">*</span>
                </label>
                <input
                  id="bot-name"
                  type="text"
                  placeholder="例如: 售前咨询专家 / 安全代码审计师"
                  value={form.botName}
                  onChange={(e) => {
                    updateFormField('botName', e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label htmlFor="role-desc" className="block text-[11px] font-medium text-slate-300 mb-1">
                  角色职责定位
                </label>
                <input
                  id="role-desc"
                  type="text"
                  placeholder="例如: 负责全流程意向商机识别与线索沉淀"
                  value={form.roleDescription}
                  onChange={(e) => {
                    updateFormField('roleDescription', e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label htmlFor="soul-prompt" className="flex items-center justify-between text-[11px] font-medium text-slate-300 mb-1">
                <span className="flex items-center space-x-1">
                  <FileText className="h-3 w-3 text-slate-400" />
                  <span>灵魂提示词 (SOUL.md / 核心行为准则)</span>
                </span>
                <span className="text-[10px] text-slate-400">支持 Markdown 语法</span>
              </label>
              <textarea
                id="soul-prompt"
                rows={3}
                value={form.soulPrompt}
                onChange={(e) => {
                  updateFormField('soulPrompt', e.target.value);
                }}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Section 2: 一键继承主 Agent 资产 */}
          <MasterInheritanceToggleCard
            isInheriting={form.isInheritingMaster}
            options={form.inheritanceOptions}
            masterAssets={masterAssets}
            onToggleInheritance={toggleInheritance}
            onToggleOption={toggleInheritanceOption}
          />

          {/* Section 3: 多层认知大脑分级推荐 */}
          <CognitiveTieringSelector
            selectedTier={form.selectedTier}
            onSelectTier={selectCognitiveTier}
          />

          {/* Section 4: 视觉标识与像素吉祥物 */}
          <PixelMascotPicker
            availableMascots={availableMascots}
            selectedMascotId={form.selectedMascotId}
            avatarType={form.avatarType}
            isGeneratingAvatar={form.isGeneratingAvatar}
            generatedAvatarUrl={form.generatedAvatarUrl}
            onSelectMascot={selectPixelMascot}
            onGenerateAvatar={() => {
              void generateAiAvatar();
            }}
          />
        </div>

        {/* Footer */}
        <footer className="flex h-14 shrink-0 items-center justify-between border-t border-slate-800 px-6 bg-slate-950/60">
          <div className="text-[11px] text-slate-400 flex items-center space-x-1">
            <Sparkles className="h-3.5 w-3.5 text-blue-400" />
            <span>就绪配置：{form.selectedModel} · {form.selectedTier}</span>
          </div>

          <div className="flex items-center space-x-2.5">
            <button
              type="button"
              onClick={closeStudio}
              className="rounded-lg px-4 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => {
                void handleCreate();
              }}
              className="inline-flex items-center space-x-1.5 rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500"
            >
              <CheckCircle className="h-4 w-4" />
              <span>立即创建并激活智能体</span>
            </button>
          </div>
        </footer>
      </div>
    </dialog>
  );
};
