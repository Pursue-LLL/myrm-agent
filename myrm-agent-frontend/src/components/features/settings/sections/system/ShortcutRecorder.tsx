'use client';

/**
 * 全局快捷键录制输入框：聚焦即录制，Esc 取消，Backspace/Delete 清空。
 */

import { memo, useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

const ShortcutRecorder = memo<{
  value: string;
  onChange: (value: string) => void;
}>(({ value, onChange }) => {
  const [isRecording, setIsRecording] = useState(false);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isRecording) {
        return;
      }
      e.preventDefault();
      e.stopPropagation();

      // Don't record if only modifiers are pressed
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        return;
      }

      // Escape to cancel recording
      if (e.key === 'Escape') {
        setIsRecording(false);
        return;
      }

      // Backspace to clear shortcut
      if (e.key === 'Backspace' || e.key === 'Delete') {
        onChange('');
        setIsRecording(false);
        return;
      }

      const keys: string[] = [];

      if (e.metaKey) {
        keys.push('Super');
      }
      if (e.ctrlKey) {
        keys.push('Control');
      }
      if (e.altKey) {
        keys.push('Alt');
      }
      if (e.shiftKey) {
        keys.push('Shift');
      }

      let mainKey = e.key.toUpperCase();
      if (e.code === 'Space') {
        mainKey = 'Space';
      }
      if (mainKey.length === 1 && mainKey >= 'A' && mainKey <= 'Z') {
        // ok
      } else if (mainKey >= '0' && mainKey <= '9') {
        // ok
      } else if (mainKey !== 'SPACE') {
        mainKey = e.code.replace('Key', '').replace('Digit', '');
      }

      keys.push(mainKey === 'SPACE' ? 'Space' : mainKey);

      onChange(keys.join('+'));
      setIsRecording(false);
    },
    [isRecording, onChange],
  );

  return (
    <input
      type="text"
      value={isRecording ? '录制中...' : value}
      onFocus={() => setIsRecording(true)}
      onBlur={() => setIsRecording(false)}
      onKeyDown={handleKeyDown}
      placeholder="e.g. Alt+Space"
      readOnly
      className={cn(
        'w-40 px-4 py-2.5 bg-black/20 border border-white/10 rounded-xl text-sm text-center text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50 cursor-pointer transition-colors',
        isRecording && 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400',
      )}
    />
  );
});
ShortcutRecorder.displayName = 'ShortcutRecorder';

export default ShortcutRecorder;
