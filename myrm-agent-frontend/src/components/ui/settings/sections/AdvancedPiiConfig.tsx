/**
 * [INPUT]
 *   useConfigStore (POS: 全局配置状态管理)
 *   lucide-react icons
 *   shadcn UI primitives
 * [OUTPUT]
 *   AdvancedPiiConfig: 高级 PII 自定义规则配置面板（关键词/正则/敏感工具 + 测试匹配）
 * [POS]
 *   PII 隐私策略的高级自定义配置 UI，允许用户自定义 S2/S3 关键词、正则模式和敏感工具列表
 */
'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconFlask, IconPlus, IconChevronDown, IconChevronRight, IconX } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';

const KNOWN_TOOLS = [
  'web_search_tool',
  'net_fetch',
  'shell_exec',
  'file_read',
  'file_write',
  'mcp_invoke',
  'code_interpreter_tool',
  'browser_navigate',
  'browser_fill',
  'browser_upload',
  'browser_download',
  'browser_session',
] as const;

// ─── TagListEditor ───────────────────────────────────────────────────────────

interface TagListEditorProps {
  label: string;
  description: string;
  tags: string[];
  inputValue: string;
  placeholder: string;
  onInputChange: (v: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  levelColor: 'amber' | 'red';
  validate?: (v: string) => boolean;
  errorMessage?: string;
}

const TagListEditor = memo(
  ({
    label,
    description,
    tags,
    inputValue,
    placeholder,
    onInputChange,
    onAdd,
    onRemove,
    levelColor,
    validate,
    errorMessage,
  }: TagListEditorProps) => {
    const [inputError, setInputError] = useState('');
    const colorClass =
      levelColor === 'red'
        ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400 border-red-200 dark:border-red-800/50'
        : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-200 dark:border-amber-800/50';

    return (
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground mb-1.5">{description}</p>
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => {
              onInputChange(e.target.value);
              if (validate && e.target.value && !validate(e.target.value)) {
                setInputError(errorMessage ?? '');
              } else {
                setInputError('');
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                onAdd();
              }
            }}
            placeholder={placeholder}
            className="text-sm flex-1"
          />
          <Button variant="outline" size="sm" onClick={onAdd} disabled={!inputValue.trim()}>
            <IconPlus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {inputError && <p className="text-xs text-destructive mt-0.5">{inputError}</p>}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {tags.map((tag, i) => (
              <span
                key={`${tag}-${i}`}
                className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${colorClass}`}
              >
                {tag}
                <button type="button" onClick={() => onRemove(i)} className="hover:opacity-70 transition-opacity">
                  <IconX className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    );
  },
);
TagListEditor.displayName = 'TagListEditor';

// ─── ToolTagEditor ───────────────────────────────────────────────────────────

interface ToolTagEditorProps {
  label: string;
  description: string;
  tools: string[];
  onToggle: (tool: string) => void;
  levelColor: 'amber' | 'red';
}

const ToolTagEditor = memo(({ label, description, tools, onToggle, levelColor }: ToolTagEditorProps) => {
  const activeClass =
    levelColor === 'red'
      ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400 border-red-300 dark:border-red-700'
      : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-300 dark:border-amber-700';

  return (
    <div>
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="text-xs text-muted-foreground mb-1.5">{description}</p>
      <div className="flex flex-wrap gap-1.5">
        {KNOWN_TOOLS.map((tool) => {
          const active = tools.includes(tool);
          return (
            <button
              key={tool}
              type="button"
              onClick={() => onToggle(tool)}
              className={`px-2 py-0.5 text-xs font-medium rounded-full border transition-colors ${
                active ? activeClass : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
              }`}
            >
              {tool}
            </button>
          );
        })}
      </div>
    </div>
  );
});
ToolTagEditor.displayName = 'ToolTagEditor';

// ─── AdvancedPiiConfig (main) ────────────────────────────────────────────────

const AdvancedPiiConfig = memo(() => {
  const t = useTranslations('settings.securityPolicy');

  const {
    privacyCustomKeywordsS2,
    privacyCustomKeywordsS3,
    privacyCustomPatternsS2,
    privacyCustomPatternsS3,
    privacySensitiveToolsS2,
    privacySensitiveToolsS3,
    setPrivacyCustomKeywordsS2,
    setPrivacyCustomKeywordsS3,
    setPrivacyCustomPatternsS2,
    setPrivacyCustomPatternsS3,
    setPrivacySensitiveToolsS2,
    setPrivacySensitiveToolsS3,
  } = useConfigStore();

  const [open, setOpen] = useState(false);
  const [newKeywordS2, setNewKeywordS2] = useState('');
  const [newKeywordS3, setNewKeywordS3] = useState('');
  const [newPatternS2, setNewPatternS2] = useState('');
  const [newPatternS3, setNewPatternS3] = useState('');
  const [testMatchText, setTestMatchText] = useState('');
  const [testMatchResult, setTestMatchResult] = useState<string | null>(null);

  const isValidRegex = useCallback((pattern: string): boolean => {
    try {
      new RegExp(pattern, 'i');
    } catch {
      return false;
    }
    // ReDoS prevention: reject nested quantifiers like (a+)+, (a*)+, (a+)*, (a{2,})+
    if (/([+*]\)?[+*]|[+*]\)?\{|\}\)?[+*])/.test(pattern)) return false;
    return true;
  }, []);

  const addKeyword = useCallback(
    (level: 's2' | 's3', value: string) => {
      const trimmed = value.trim();
      if (trimmed.length < 2) {
        toast.error(t('privacy.advanced.keywordTooShort'));
        return;
      }
      if (level === 's2') {
        if (!privacyCustomKeywordsS2.includes(trimmed)) {
          setPrivacyCustomKeywordsS2([...privacyCustomKeywordsS2, trimmed]);
        }
        setNewKeywordS2('');
      } else {
        if (!privacyCustomKeywordsS3.includes(trimmed)) {
          setPrivacyCustomKeywordsS3([...privacyCustomKeywordsS3, trimmed]);
        }
        setNewKeywordS3('');
      }
    },
    [privacyCustomKeywordsS2, privacyCustomKeywordsS3, setPrivacyCustomKeywordsS2, setPrivacyCustomKeywordsS3, t],
  );

  const removeKeyword = useCallback(
    (level: 's2' | 's3', index: number) => {
      if (level === 's2') {
        setPrivacyCustomKeywordsS2(privacyCustomKeywordsS2.filter((_, i) => i !== index));
      } else {
        setPrivacyCustomKeywordsS3(privacyCustomKeywordsS3.filter((_, i) => i !== index));
      }
    },
    [privacyCustomKeywordsS2, privacyCustomKeywordsS3, setPrivacyCustomKeywordsS2, setPrivacyCustomKeywordsS3],
  );

  const addPattern = useCallback(
    (level: 's2' | 's3', value: string) => {
      const trimmed = value.trim();
      if (!trimmed || !isValidRegex(trimmed)) {
        toast.error(t('privacy.advanced.invalidRegex'));
        return;
      }
      if (level === 's2') {
        if (!privacyCustomPatternsS2.includes(trimmed)) {
          setPrivacyCustomPatternsS2([...privacyCustomPatternsS2, trimmed]);
        }
        setNewPatternS2('');
      } else {
        if (!privacyCustomPatternsS3.includes(trimmed)) {
          setPrivacyCustomPatternsS3([...privacyCustomPatternsS3, trimmed]);
        }
        setNewPatternS3('');
      }
    },
    [
      privacyCustomPatternsS2,
      privacyCustomPatternsS3,
      setPrivacyCustomPatternsS2,
      setPrivacyCustomPatternsS3,
      isValidRegex,
      t,
    ],
  );

  const removePattern = useCallback(
    (level: 's2' | 's3', index: number) => {
      if (level === 's2') {
        setPrivacyCustomPatternsS2(privacyCustomPatternsS2.filter((_, i) => i !== index));
      } else {
        setPrivacyCustomPatternsS3(privacyCustomPatternsS3.filter((_, i) => i !== index));
      }
    },
    [privacyCustomPatternsS2, privacyCustomPatternsS3, setPrivacyCustomPatternsS2, setPrivacyCustomPatternsS3],
  );

  const toggleTool = useCallback(
    (level: 's2' | 's3', tool: string) => {
      if (level === 's2') {
        const updated = privacySensitiveToolsS2.includes(tool)
          ? privacySensitiveToolsS2.filter((item) => item !== tool)
          : [...privacySensitiveToolsS2, tool];
        setPrivacySensitiveToolsS2(updated);
      } else {
        const updated = privacySensitiveToolsS3.includes(tool)
          ? privacySensitiveToolsS3.filter((item) => item !== tool)
          : [...privacySensitiveToolsS3, tool];
        setPrivacySensitiveToolsS3(updated);
      }
    },
    [privacySensitiveToolsS2, privacySensitiveToolsS3, setPrivacySensitiveToolsS2, setPrivacySensitiveToolsS3],
  );

  const runTestMatch = useCallback(() => {
    if (!testMatchText.trim()) return;
    const text = testMatchText.trim();
    const matches: string[] = [];

    for (const kw of privacyCustomKeywordsS3) {
      if (text.toLowerCase().includes(kw.toLowerCase())) matches.push(`S3:keyword:${kw}`);
    }
    for (const pat of privacyCustomPatternsS3) {
      try {
        if (new RegExp(pat, 'i').test(text)) matches.push(`S3:pattern:${pat}`);
      } catch {
        /* skip invalid */
      }
    }
    for (const kw of privacyCustomKeywordsS2) {
      if (text.toLowerCase().includes(kw.toLowerCase())) matches.push(`S2:keyword:${kw}`);
    }
    for (const pat of privacyCustomPatternsS2) {
      try {
        if (new RegExp(pat, 'i').test(text)) matches.push(`S2:pattern:${pat}`);
      } catch {
        /* skip invalid */
      }
    }

    if (matches.length > 0) {
      const level = matches[0].startsWith('S3') ? 'S3' : 'S2';
      setTestMatchResult(t('privacy.advanced.testMatchResult', { level, patterns: matches.join(', ') }));
    } else {
      setTestMatchResult(t('privacy.advanced.testMatchNoResult'));
    }
  }, [
    testMatchText,
    privacyCustomKeywordsS2,
    privacyCustomKeywordsS3,
    privacyCustomPatternsS2,
    privacyCustomPatternsS3,
    t,
  ]);

  return (
    <div className="border-t border-border/50 pt-3">
      <button
        type="button"
        className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-primary transition-colors w-full"
        onClick={() => setOpen(!open)}
      >
        {open ? <IconChevronDown className="h-4 w-4" /> : <IconChevronRight className="h-4 w-4" />}
        {t('privacy.advanced.title')}
      </button>
      <p className="text-xs text-muted-foreground mt-1 ml-6">{t('privacy.advanced.description')}</p>

      {open && (
        <div className="mt-3 space-y-4">
          <TagListEditor
            label={t('privacy.advanced.keywordsS2Label')}
            description={t('privacy.advanced.keywordsS2Desc')}
            tags={privacyCustomKeywordsS2}
            inputValue={newKeywordS2}
            placeholder={t('privacy.advanced.keywordsS2Placeholder')}
            onInputChange={setNewKeywordS2}
            onAdd={() => addKeyword('s2', newKeywordS2)}
            onRemove={(i) => removeKeyword('s2', i)}
            levelColor="amber"
          />

          <TagListEditor
            label={t('privacy.advanced.keywordsS3Label')}
            description={t('privacy.advanced.keywordsS3Desc')}
            tags={privacyCustomKeywordsS3}
            inputValue={newKeywordS3}
            placeholder={t('privacy.advanced.keywordsS3Placeholder')}
            onInputChange={setNewKeywordS3}
            onAdd={() => addKeyword('s3', newKeywordS3)}
            onRemove={(i) => removeKeyword('s3', i)}
            levelColor="red"
          />

          <TagListEditor
            label={t('privacy.advanced.patternsS2Label')}
            description={t('privacy.advanced.patternsS2Desc')}
            tags={privacyCustomPatternsS2}
            inputValue={newPatternS2}
            placeholder={t('privacy.advanced.patternsS2Placeholder')}
            onInputChange={setNewPatternS2}
            onAdd={() => addPattern('s2', newPatternS2)}
            onRemove={(i) => removePattern('s2', i)}
            levelColor="amber"
            validate={isValidRegex}
            errorMessage={t('privacy.advanced.invalidRegex')}
          />

          <TagListEditor
            label={t('privacy.advanced.patternsS3Label')}
            description={t('privacy.advanced.patternsS3Desc')}
            tags={privacyCustomPatternsS3}
            inputValue={newPatternS3}
            placeholder={t('privacy.advanced.patternsS3Placeholder')}
            onInputChange={setNewPatternS3}
            onAdd={() => addPattern('s3', newPatternS3)}
            onRemove={(i) => removePattern('s3', i)}
            levelColor="red"
            validate={isValidRegex}
            errorMessage={t('privacy.advanced.invalidRegex')}
          />

          <ToolTagEditor
            label={t('privacy.advanced.toolsS2Label')}
            description={t('privacy.advanced.toolsS2Desc')}
            tools={privacySensitiveToolsS2}
            onToggle={(tool) => toggleTool('s2', tool)}
            levelColor="amber"
          />

          <ToolTagEditor
            label={t('privacy.advanced.toolsS3Label')}
            description={t('privacy.advanced.toolsS3Desc')}
            tools={privacySensitiveToolsS3}
            onToggle={(tool) => toggleTool('s3', tool)}
            levelColor="red"
          />

          {/* Test Match */}
          <div className="border-t border-border/30 pt-3">
            <div className="flex items-center gap-2 mb-2">
              <IconFlask className="h-3.5 w-3.5 text-primary" />
              <span className="text-sm font-medium text-foreground">{t('privacy.advanced.testMatch')}</span>
            </div>
            <div className="flex gap-2">
              <Input
                value={testMatchText}
                onChange={(e) => {
                  setTestMatchText(e.target.value);
                  setTestMatchResult(null);
                }}
                placeholder={t('privacy.advanced.testMatchPlaceholder')}
                className="text-sm flex-1"
                onKeyDown={(e) => e.key === 'Enter' && runTestMatch()}
              />
              <Button variant="outline" size="sm" onClick={runTestMatch}>
                {t('privacy.advanced.testMatch')}
              </Button>
            </div>
            {testMatchResult && (
              <p
                className={`text-xs mt-1.5 ${testMatchResult.includes('S3') ? 'text-red-500' : testMatchResult.includes('S2') ? 'text-amber-500' : 'text-muted-foreground'}`}
              >
                {testMatchResult}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
});
AdvancedPiiConfig.displayName = 'AdvancedPiiConfig';

export { AdvancedPiiConfig };
