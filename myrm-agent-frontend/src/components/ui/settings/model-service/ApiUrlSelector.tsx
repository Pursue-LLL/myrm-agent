'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Pencil, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { AlternativeApiUrl } from '@/store/config/providerTypes';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

interface ApiUrlSelectorProps {
  providerId: string;
  apiUrl: string;
  defaultApiUrl: string;
  alternativeApiUrls?: AlternativeApiUrl[];
  onChange: (url: string) => void;
  isBuiltIn: boolean;
}

const ApiUrlSelector = memo<ApiUrlSelectorProps>(
  ({ providerId: _providerId, apiUrl, defaultApiUrl, alternativeApiUrls, onChange, isBuiltIn }) => {
    const t = useTranslations('settings.modelService');
    const [useCustomUrl, setUseCustomUrl] = useState(false);
    const [copied, setCopied] = useState(false);
    const [customUrlValue, setCustomUrlValue] = useState(
      apiUrl && !String(apiUrl).startsWith('undefined') ? apiUrl : '',
    );

    // 判断是否有备选地址
    const hasAlternatives = alternativeApiUrls && alternativeApiUrls.length > 0;

    // 根据当前 apiUrl 找到匹配的备选地址索引
    const findMatchingIndex = useCallback(
      (url: string) => {
        if (!hasAlternatives) return 0;
        const idx = alternativeApiUrls.findIndex((alt) => alt.url === url);
        return idx >= 0 ? idx : 0;
      },
      [alternativeApiUrls, hasAlternatives],
    );

    const [selectedIdx, setSelectedIdx] = useState(findMatchingIndex(apiUrl));

    // 初始化：检查当前 URL 是否是预设的备选地址
    useEffect(() => {
      if (hasAlternatives) {
        const matchingIdx = alternativeApiUrls.findIndex((alt) => alt.url === apiUrl);
        if (matchingIdx >= 0) {
          setSelectedIdx(matchingIdx);
          setUseCustomUrl(false);
        } else {
          // 当前 URL 不是预设地址，启用自定义模式
          setUseCustomUrl(true);
          setCustomUrlValue(apiUrl);
        }
      }
    }, [apiUrl, alternativeApiUrls, hasAlternatives]);

    // 处理下拉选择
    const handleSelectChange = useCallback(
      (value: string) => {
        const idx = parseInt(value, 10);
        setSelectedIdx(idx);
        setUseCustomUrl(false);
        if (alternativeApiUrls && alternativeApiUrls[idx]) {
          onChange(alternativeApiUrls[idx].url);
        }
      },
      [alternativeApiUrls, onChange],
    );

    // 处理自定义 URL 输入
    const handleCustomUrlChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
      setCustomUrlValue(e.target.value);
    }, []);

    const handleCustomUrlBlur = useCallback(() => {
      onChange(customUrlValue);
    }, [customUrlValue, onChange]);

    // 切换到自定义模式
    const handleEnableCustom = useCallback(() => {
      setUseCustomUrl(true);
      // 防御性处理：过滤掉非有效 URL 的值
      const safeUrl = apiUrl && !String(apiUrl).startsWith('undefined') ? apiUrl : '';
      setCustomUrlValue(safeUrl);
    }, [apiUrl]);

    // 复制 URL
    const handleCopyUrl = useCallback(async () => {
      await writeToClipboard(apiUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }, [apiUrl]);

    // 无备选地址：使用简单输入框
    if (!hasAlternatives) {
      // 防御性处理：过滤掉非有效 URL 的值（如 store 被序列化污染的 "undefined" 字符串）
      const displayUrl = apiUrl && !String(apiUrl).startsWith('undefined') ? apiUrl : '';
      return (
        <div className="space-y-2">
          <input
            type="text"
            value={displayUrl}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t('apiUrlPlaceholder')}
            className="w-full px-4 py-3 text-sm bg-background/50 border border-border/50 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all"
          />
          {isBuiltIn && <p className="text-xs text-muted-foreground">{t('apiUrlHint')}</p>}
        </div>
      );
    }

    // 有备选地址：显示选择器 + URL 展示 + 自定义选项
    return (
      <div className="space-y-3">
        {/* 下拉选择器 */}
        <Select value={String(selectedIdx)} onValueChange={handleSelectChange}>
          <SelectTrigger
            className="w-full px-4 py-3 text-sm bg-background/50 border border-border/50 rounded-xl focus:ring-2 focus:ring-primary/30"
            disabled={useCustomUrl}
          >
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-muted-foreground" />
              <SelectValue>{alternativeApiUrls[selectedIdx]?.label || t('selectEndpoint')}</SelectValue>
            </div>
          </SelectTrigger>
          <SelectContent className="rounded-xl">
            {alternativeApiUrls.map((alt, idx) => (
              <SelectItem key={idx} value={String(idx)} className="rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>{alt.label}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* URL 展示区域 */}
        <div
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 bg-background/30 border border-border/30 rounded-lg',
            useCustomUrl ? 'border-primary/30 bg-primary/5' : '',
          )}
        >
          {useCustomUrl ? (
            // 自定义 URL 输入框
            <input
              type="text"
              value={customUrlValue}
              onChange={handleCustomUrlChange}
              onBlur={handleCustomUrlBlur}
              placeholder={t('apiUrlPlaceholder')}
              className="flex-1 text-sm bg-transparent focus:outline-none"
              autoFocus
            />
          ) : (
            // 显示当前 URL（只读）
            <div className="flex-1 flex items-center gap-2">
              <code className="text-xs text-muted-foreground font-mono truncate flex-1">{apiUrl}</code>
              <button
                onClick={handleCopyUrl}
                className="p-1.5 hover:bg-primary/10 rounded-full transition-colors"
                title={t('copyUrl')}
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-green-500" />
                ) : (
                  <Copy className="w-3.5 h-3.5 text-muted-foreground" />
                )}
              </button>
            </div>
          )}
        </div>

        {/* 自定义地址开关 */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleEnableCustom}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-all',
              useCustomUrl
                ? 'border-primary/50 text-primary bg-primary/10'
                : 'border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5',
            )}
          >
            <Pencil className="w-3 h-3" />
            {t('useCustomUrl')}
          </button>
          {useCustomUrl && (
            <button
              onClick={() => {
                setUseCustomUrl(false);
                onChange(alternativeApiUrls[selectedIdx]?.url || defaultApiUrl);
              }}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('resetToDefault')}
            </button>
          )}
        </div>

        {/* 提示信息 */}
        {isBuiltIn && !useCustomUrl && (
          <p className="text-xs text-muted-foreground">{t('apiUrlHintWithAlternatives')}</p>
        )}
      </div>
    );
  },
);

ApiUrlSelector.displayName = 'ApiUrlSelector';

export default ApiUrlSelector;
