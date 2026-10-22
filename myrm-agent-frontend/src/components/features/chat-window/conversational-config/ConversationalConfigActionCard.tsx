import React, { useState } from 'react';
import {
  Check,
  CheckCircle2,
  Copy,
  Eye,
  EyeOff,
  Globe,
  Radio,
  Settings2,
  ShieldCheck,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { maskSecretKey } from './conversationalConfigEngine';
import {
  ConfigIntentCategory,
  ConversationalConfigIntent,
} from './conversationalConfigTypes';
import { useConversationalConfigStore } from './useConversationalConfigStore';

interface ConversationalConfigActionCardProps {
  card: ConversationalConfigIntent;
  onApplied?: (card: ConversationalConfigIntent) => void;
  className?: string;
}

function renderCategoryIcon(category: ConfigIntentCategory) {
  if (category === 'model_switch') {
    return <Zap className="h-3.5 w-3.5 text-purple-500" />;
  }
  if (category === 'api_key_entry') {
    return <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />;
  }
  if (category === 'search_engine') {
    return <Globe className="h-3.5 w-3.5 text-blue-500" />;
  }
  return <Radio className="h-3.5 w-3.5 text-amber-500" />;
}

export const ConversationalConfigActionCard: React.FC<
  ConversationalConfigActionCardProps
> = ({ card, onApplied, className = '' }) => {
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({});
  const updateCardParamValue = useConversationalConfigStore(
    (state) => state.updateCardParamValue,
  );
  const applyConfiguration = useConversationalConfigStore(
    (state) => state.applyConfiguration,
  );
  const dismissConfigCard = useConversationalConfigStore(
    (state) => state.dismissConfigCard,
  );

  const toggleSecretVisibility = (key: string) => {
    setShowSecret((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleApply = () => {
    const success = applyConfiguration(card.id);
    if (success && onApplied) {
      onApplied(card);
    }
  };

  return (
    <div
      data-testid={`config-action-card-${card.id}`}
      className={`my-2 w-full max-w-lg rounded-xl border border-primary/25 bg-background/95 p-3.5 text-xs shadow-sm backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与类别微标 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
            {renderCategoryIcon(card.category)}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground">
                {card.title}
              </span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                自然语言识别
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground leading-tight">
              {card.description}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            dismissConfigCard(card.id);
          }}
          aria-label="关闭配置卡片"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* 参数表单 */}
      <div className="mt-3 space-y-2">
        {card.params.map((param) => {
          const isSecretField = Boolean(param.isSecret);
          const isRevealed = Boolean(showSecret[param.key]);

          return (
            <div key={param.key} className="space-y-1">
              <label
                htmlFor={`input-${card.id}-${param.key}`}
                className="block text-[11px] font-medium text-muted-foreground"
              >
                {param.label}
              </label>

              {param.type === 'select' && param.options ? (
                <select
                  id={`input-${card.id}-${param.key}`}
                  disabled={card.isApplied}
                  value={param.value}
                  onChange={(e) => {
                    updateCardParamValue(card.id, param.key, e.target.value);
                  }}
                  className="w-full rounded-lg border border-border/60 bg-background px-2.5 py-1 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-60"
                >
                  {param.options.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="relative flex items-center">
                  <input
                    id={`input-${card.id}-${param.key}`}
                    type={isSecretField && !isRevealed ? 'password' : 'text'}
                    disabled={card.isApplied}
                    value={param.value}
                    placeholder={param.placeholder}
                    onChange={(e) => {
                      updateCardParamValue(card.id, param.key, e.target.value);
                    }}
                    className="w-full rounded-lg border border-border/60 bg-background px-2.5 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-60"
                  />

                  {isSecretField && (
                    <button
                      type="button"
                      onClick={() => {
                        toggleSecretVisibility(param.key);
                      }}
                      aria-label={isRevealed ? '隐藏秘钥明文' : '显示秘钥明文'}
                      className="absolute right-2 text-muted-foreground hover:text-foreground"
                    >
                      {isRevealed ? (
                        <EyeOff className="h-3.5 w-3.5" />
                      ) : (
                        <Eye className="h-3.5 w-3.5" />
                      )}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 底部确认与授权应用按钮 */}
      <div className="mt-3.5 flex items-center justify-between border-t border-border/30 pt-2.5 text-[11px]">
        <span className="text-muted-foreground">
          {card.isApplied ? '已持久化写入沙箱配置' : '仅在显式确认后持久化生效'}
        </span>

        {card.isApplied ? (
          <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>已成功应用配置</span>
          </span>
        ) : (
          <button
            type="button"
            onClick={handleApply}
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-1 font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
          >
            <Check className="h-3 w-3" />
            <span>确认应用 (Apply)</span>
          </button>
        )}
      </div>
    </div>
  );
};
