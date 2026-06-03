import React, { useState, useEffect, useRef } from 'react';
import { IconHelpCircle, IconAlertCircle, IconCode } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import Tooltip from './Tooltip';

interface JsonEditorProps {
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  onBlur?: () => void;
  onError?: (hasError: boolean) => void;
  label?: string;
  tooltip?: string;
  helpText?: string;
  error?: string;
  placeholder?: string;
}

const JsonEditor: React.FC<JsonEditorProps> = ({
  value,
  onChange,
  onBlur,
  onError,
  label,
  tooltip,
  helpText,
  error,
  placeholder = '{\n  "key": "value"\n}',
}) => {
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 通知父组件错误状态变化
  useEffect(() => {
    if (onError) {
      onError(!!jsonError);
    }
  }, [jsonError, onError]);

  // 将对象转换为格式化的JSON文本
  useEffect(() => {
    try {
      // 如果对象为空，不设置默认值，使placeholder可见
      if (!value || Object.keys(value).length === 0) {
        setJsonText('');
        return;
      }

      const formatted = JSON.stringify(value, null, 2);
      setJsonText(formatted);
      setJsonError(null);
    } catch (err) {
      console.error('JSON格式化错误:', err);
      setJsonError('无法格式化JSON');
    }
  }, [value]);

  // 处理文本变化（实时解析并通知父组件）
  const handleTextChange = (text: string) => {
    setJsonText(text);

    // 尝试实时解析 JSON，成功则通知父组件
    try {
      if (!text.trim()) {
        onChange({});
        setJsonError(null);
        return;
      }
      const parsed = JSON.parse(text);
      onChange(parsed);
      setJsonError(null);
    } catch {
      // 解析失败时只清除之前的错误提示，不显示新错误（用户可能还在输入中）
      // 最终验证在 onBlur 时进行
    }
  };

  // 尝试解析JSON并更新值
  const parseAndUpdateJson = () => {
    try {
      if (!jsonText.trim()) {
        onChange({});
        setJsonError(null);
        return;
      }

      const parsed = JSON.parse(jsonText);
      onChange(parsed);
      setJsonError(null);
    } catch (err) {
      console.error('JSON解析错误:', err);
      setJsonError('JSON格式无效');
    }
  };

  // 格式化JSON
  const formatJson = () => {
    try {
      if (!jsonText.trim()) {
        // 空文本时不做任何处理，保持为空
        onChange({});
        setJsonError(null);
        return;
      }

      const parsed = JSON.parse(jsonText);
      const formatted = JSON.stringify(parsed, null, 2);
      setJsonText(formatted);
      onChange(parsed);
      setJsonError(null);
    } catch (err) {
      console.error('JSON格式化错误:', err);
      setJsonError('JSON格式无效，无法格式化');
    }
  };

  return (
    <div className="flex flex-col space-y-1">
      {label && (
        <div className="flex items-center space-x-1">
          <p className="text-black/70 dark:text-white/70 text-sm">{label}</p>
          {tooltip && (
            <Tooltip content={tooltip}>
              <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
            </Tooltip>
          )}
        </div>
      )}

      <div
        className={cn(
          'relative border border-border rounded-lg bg-secondary',
          (error || jsonError) && 'border-red-500',
        )}
      >
        {/* 格式化按钮 - 右上角 */}
        <button
          type="button"
          onClick={formatJson}
          className="absolute top-2 right-2 p-1 rounded text-xs text-black/60 dark:text-white/60 hover:bg-accent hover:text-black/90 dark:hover:text-white/90 transition-colors"
        >
          <IconCode className="w-4 h-4" />
        </button>

        {/* 文本编辑区 */}
        <textarea
          ref={textareaRef}
          value={jsonText}
          onChange={(e) => handleTextChange(e.target.value)}
          onBlur={() => {
            parseAndUpdateJson();
            if (onBlur) onBlur();
          }}
          placeholder={placeholder}
          className="w-full h-40 p-3 bg-transparent font-mono text-sm resize-y outline-none dark:text-white/90 rounded-lg"
          style={{ tabSize: 2 }}
          spellCheck="false"
        />
      </div>

      {(error || jsonError) && (
        <div className="flex items-start space-x-1">
          <IconAlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
          <p className="text-xs text-red-500 font-medium">{error || jsonError}</p>
        </div>
      )}

      {helpText && !error && !jsonError && (
        <p className="text-xs text-black/60 dark:text-white/60 whitespace-pre-line">{helpText}</p>
      )}
    </div>
  );
};

export default JsonEditor;
