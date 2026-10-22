'use client';

/**
 * Extension Widgets Host Container and Built-in Nano-Context / Todo Widgets.
 *
 * [INPUT] lucide-react, next-intl, ./ansiRendererTypes, ./AnsiRenderer
 * [OUTPUT] ExtensionWidgetHost: Modular host container for sidebar & dashboard extension widgets.
 * [POS] src/components/features/extension-widgets/ExtensionWidgetHost.tsx
 */

import { memo, useState, useCallback } from 'react';
import {
  Cpu,
  CheckSquare,
  ChevronDown,
  Plus,
  Trash2,
  Check,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { NanoContextData, TodoItem } from './ansiRendererTypes';
import { AnsiRenderer } from './AnsiRenderer';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export interface ExtensionWidgetHostProps {
  className?: string;
  nanoContext?: NanoContextData;
  initialTodos?: TodoItem[];
}

export const ExtensionWidgetHost = memo(function ExtensionWidgetHost({
  className,
  nanoContext,
  initialTodos = [
    { id: '1', text: 'Review PR & unit tests', done: false },
    { id: '2', text: 'Check token budget limits', done: true },
  ],
}: ExtensionWidgetHostProps) {
  const t = useTranslations('extensionWidgets');
  const [nanoCollapsed, setNanoCollapsed] = useState(false);
  const [todoCollapsed, setTodoCollapsed] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>(initialTodos);
  const [newTodoText, setNewTodoText] = useState('');

  const currentNano: NanoContextData = nanoContext || {
    usedTokens: 18420,
    maxTokens: 128000,
    percentage: 14.4,
    turnCount: 8,
    modelName: 'claude-3-7-sonnet',
  };

  const handleToggleTodo = useCallback((id: string) => {
    setTodos((prev) =>
      prev.map((item) => {
        if (item.id === id) {
          return { ...item, done: !item.done };
        }
        return item;
      }),
    );
  }, []);

  const handleAddTodo = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const text = newTodoText.trim();
      if (!text) {
        return;
      }
      setTodos((prev) => [...prev, { id: String(Date.now()), text, done: false }]);
      setNewTodoText('');
    },
    [newTodoText],
  );

  const handleDeleteTodo = useCallback((id: string) => {
    setTodos((prev) => prev.filter((item) => item.id !== id));
  }, []);

  // Format ANSI sample bar for context usage
  const ansiPreview = `\u001b[32m[CONTEXT]\u001b[0m ${currentNano.usedTokens} / ${currentNano.maxTokens} tok (\u001b[33m${currentNano.percentage}%\u001b[0m)`;

  return (
    <div
      className={cn('flex flex-col gap-2 w-full text-xs', className)}
      data-testid="extension-widget-host"
    >
      {/* 1. Nano-Context Widget */}
      <div className="rounded-lg border border-border/60 bg-muted/30 overflow-hidden">
        <button
          type="button"
          onClick={() => {
            setNanoCollapsed((prev) => !prev);
          }}
          className="w-full flex items-center justify-between px-2.5 py-1.5 hover:bg-muted/50 text-left transition-colors"
        >
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <Cpu className="h-3.5 w-3.5 text-primary" />
            <span>{t('nanoContextTitle') || 'Nano-Context'}</span>
            <span className="text-[10px] text-muted-foreground font-mono">
              {currentNano.percentage}%
            </span>
          </div>
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground transition-transform duration-150',
              nanoCollapsed && '-rotate-90',
            )}
          />
        </button>

        {!nanoCollapsed && (
          <div className="p-2.5 pt-0 flex flex-col gap-1.5">
            {/* Progress Bar */}
            <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all duration-300',
                  currentNano.percentage > 80
                    ? 'bg-rose-500'
                    : currentNano.percentage > 50
                      ? 'bg-amber-500'
                      : 'bg-emerald-500',
                )}
                style={{ width: `${Math.min(currentNano.percentage, 100)}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
              <span className="font-mono">{currentNano.modelName}</span>
              <span>{currentNano.turnCount} {t('turns') || 'turns'}</span>
            </div>

            {/* ANSI Rendered Output Demo */}
            <AnsiRenderer raw={ansiPreview} className="p-1.5 bg-black/60 text-[10px] mt-1" />
          </div>
        )}
      </div>

      {/* 2. Todo Tasks Widget */}
      <div className="rounded-lg border border-border/60 bg-muted/30 overflow-hidden">
        <button
          type="button"
          onClick={() => {
            setTodoCollapsed((prev) => !prev);
          }}
          className="w-full flex items-center justify-between px-2.5 py-1.5 hover:bg-muted/50 text-left transition-colors"
        >
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <CheckSquare className="h-3.5 w-3.5 text-primary" />
            <span>{t('todoTitle') || 'Task Checklist'}</span>
            <span className="text-[10px] text-muted-foreground font-mono">
              {todos.filter((x) => x.done).length}/{todos.length}
            </span>
          </div>
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground transition-transform duration-150',
              todoCollapsed && '-rotate-90',
            )}
          />
        </button>

        {!todoCollapsed && (
          <div className="p-2.5 pt-0 flex flex-col gap-1.5">
            <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
              {todos.map((todo) => (
                <div
                  key={todo.id}
                  className="flex items-center justify-between gap-1.5 group p-1 rounded hover:bg-muted/40"
                >
                  <button
                    type="button"
                    onClick={() => {
                      handleToggleTodo(todo.id);
                    }}
                    className="flex items-center gap-1.5 min-w-0 text-left"
                  >
                    <span
                      className={cn(
                        'h-3.5 w-3.5 rounded border flex items-center justify-center flex-shrink-0 transition-colors',
                        todo.done
                          ? 'bg-primary border-primary text-primary-foreground'
                          : 'border-muted-foreground/40',
                      )}
                    >
                      {todo.done && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span
                      className={cn(
                        'truncate text-xs',
                        todo.done ? 'line-through text-muted-foreground' : 'text-foreground',
                      )}
                    >
                      {todo.text}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      handleDeleteTodo(todo.id);
                    }}
                    className={cn('text-muted-foreground hover:text-destructive p-0.5 transition-opacity', REVEAL_ON_HOVER)}
                    aria-label="Delete todo"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>

            <form onSubmit={handleAddTodo} className="flex items-center gap-1 mt-1">
              <input
                type="text"
                placeholder={t('newTodoPlaceholder') || 'Add task...'}
                value={newTodoText}
                onChange={(e) => {
                  setNewTodoText(e.target.value);
                }}
                className="flex-1 px-2 py-1 text-xs rounded border border-border bg-background/50 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="submit"
                disabled={!newTodoText.trim()}
                className="p-1 rounded bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40"
                aria-label="Add"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
});
