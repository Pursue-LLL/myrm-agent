/**
 * 交互式 UI 渲染器
 *
 * 接收 UIArtifact 声明式描述，递归渲染组件树。
 * 支持表单验证规则和国际化。
 */

'use client';

import React, { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { UIArtifact, UIAction } from '@/store/chat/types';
import { UIComponentRegistry, UIComponentProps } from './UIComponentRegistry';
import UIComponentErrorBoundary from './UIComponentErrorBoundary';
import {
  buildComponentMap,
  setValueByPath,
  getValueByPath,
  extractValidationRules,
  validateField,
  ValidationRule,
  ValidationErrorInfo,
} from './utils';

interface InteractiveUIRendererProps {
  artifact: UIArtifact;
  onAction?: (action: UIAction, data: Record<string, unknown>) => void;
}

export const InteractiveUIRenderer: React.FC<InteractiveUIRendererProps> = ({ artifact, onAction }) => {
  const t = useTranslations('interactiveUI.validation');

  // 本地数据状态（可编辑）
  const [localData, setLocalData] = useState<Record<string, unknown>>(artifact.data);
  // 验证错误状态（存储结构化错误信息）
  const [validationErrors, setValidationErrors] = useState<Map<string, ValidationErrorInfo>>(new Map());
  // 已触碰的字段（用于在 blur 时显示错误）
  const [touchedFields, setTouchedFields] = useState<Set<string>>(new Set());

  // 将结构化错误翻译为字符串
  const translateError = useCallback(
    (errorInfo: ValidationErrorInfo): string => {
      if (errorInfo.customMessage) {
        return errorInfo.customMessage;
      }
      // 使用 i18n 翻译
      return t(errorInfo.key, errorInfo.params);
    },
    [t],
  );

  // 构建组件 ID 映射
  const componentMap = useMemo(() => buildComponentMap(artifact.components), [artifact.components]);

  // 构建动作 ID 映射
  const actionMap = useMemo(() => {
    const map = new Map<string, UIAction>();
    for (const action of artifact.actions) {
      map.set(action.id, action);
    }
    return map;
  }, [artifact.actions]);

  // 构建字段路径到验证规则的映射
  const fieldValidationMap = useMemo(() => {
    const map = new Map<string, { rules: ValidationRule[]; label: string }>();
    for (const component of artifact.components) {
      const valuePath = component.bindings.value;
      if (valuePath) {
        const rules = extractValidationRules(component.props);
        if (rules.length > 0) {
          const label = (component.props.label as string) || t('defaultField');
          map.set(valuePath, { rules, label });
        }
      }
    }
    return map;
  }, [artifact.components, t]);

  // 验证单个字段
  const validateSingleField = useCallback(
    (path: string, value: unknown): ValidationErrorInfo | null => {
      const fieldConfig = fieldValidationMap.get(path);
      if (!fieldConfig) return null;
      return validateField(value, fieldConfig.rules, fieldConfig.label);
    },
    [fieldValidationMap],
  );

  // 验证所有字段
  const validateAllFields = useCallback(
    (data: Record<string, unknown>): Map<string, ValidationErrorInfo> => {
      const errors = new Map<string, ValidationErrorInfo>();
      for (const [path, { rules, label }] of fieldValidationMap) {
        const value = getValueByPath(data, path);
        const error = validateField(value, rules, label);
        if (error) {
          errors.set(path, error);
        }
      }
      return errors;
    },
    [fieldValidationMap],
  );

  // 数据更新处理
  const handleDataChange = useCallback(
    (path: string, value: unknown) => {
      setLocalData((prev) => {
        const newData = setValueByPath(prev, path, value);
        // 如果字段已被触碰，实时验证
        if (touchedFields.has(path)) {
          const error = validateSingleField(path, value);
          setValidationErrors((prevErrors) => {
            const newErrors = new Map(prevErrors);
            if (error) {
              newErrors.set(path, error);
            } else {
              newErrors.delete(path);
            }
            return newErrors;
          });
        }
        return newData;
      });
    },
    [touchedFields, validateSingleField],
  );

  // 字段失焦处理（触发验证）
  const handleFieldBlur = useCallback(
    (path: string) => {
      setTouchedFields((prev) => new Set(prev).add(path));
      const value = getValueByPath(localData, path);
      const error = validateSingleField(path, value);
      setValidationErrors((prevErrors) => {
        const newErrors = new Map(prevErrors);
        if (error) {
          newErrors.set(path, error);
        } else {
          newErrors.delete(path);
        }
        return newErrors;
      });
    },
    [localData, validateSingleField],
  );

  // 动作触发处理
  const handleAction = useCallback(
    (actionId: string) => {
      const action = actionMap.get(actionId);
      if (!action) return;

      // 如果是提交动作，先验证所有字段
      if (action.type === 'submit') {
        const errors = validateAllFields(localData);
        if (errors.size > 0) {
          setValidationErrors(errors);
          // 标记所有有验证规则的字段为已触碰
          setTouchedFields(new Set(fieldValidationMap.keys()));
          return; // 验证失败，不提交
        }
      }

      if (onAction) {
        onAction(action, localData);
      }
    },
    [actionMap, localData, onAction, validateAllFields, fieldValidationMap],
  );

  // 评估条件表达式
  const evaluateCondition = useCallback(
    (condition: string | boolean | undefined, data: Record<string, unknown>): boolean => {
      if (condition === undefined || condition === true) return true;
      if (condition === false) return false;

      // 如果是路径表达式（如 "form.showExtra"），从数据中获取值
      if (typeof condition === 'string') {
        // 支持简单的条件表达式
        // 格式: "path" -> 检查路径值是否为真
        // 格式: "path == value" -> 检查路径值是否等于指定值
        // 格式: "path != value" -> 检查路径值是否不等于指定值

        const eqMatch = condition.match(/^(.+?)\s*==\s*(.+)$/);
        if (eqMatch) {
          const [, path, expectedValue] = eqMatch;
          const actualValue = getValueByPath(data, path.trim());
          // 尝试解析 expectedValue
          let parsedExpected: unknown = expectedValue.trim();
          if (parsedExpected === 'true') parsedExpected = true;
          else if (parsedExpected === 'false') parsedExpected = false;
          else if (/^["'].*["']$/.test(parsedExpected as string)) {
            parsedExpected = (parsedExpected as string).slice(1, -1);
          } else if (!isNaN(Number(parsedExpected))) {
            parsedExpected = Number(parsedExpected);
          }
          return actualValue === parsedExpected;
        }

        const neqMatch = condition.match(/^(.+?)\s*!=\s*(.+)$/);
        if (neqMatch) {
          const [, path, expectedValue] = neqMatch;
          const actualValue = getValueByPath(data, path.trim());
          let parsedExpected: unknown = expectedValue.trim();
          if (parsedExpected === 'true') parsedExpected = true;
          else if (parsedExpected === 'false') parsedExpected = false;
          else if (/^["'].*["']$/.test(parsedExpected as string)) {
            parsedExpected = (parsedExpected as string).slice(1, -1);
          } else if (!isNaN(Number(parsedExpected))) {
            parsedExpected = Number(parsedExpected);
          }
          return actualValue !== parsedExpected;
        }

        // 简单路径检查
        const value = getValueByPath(data, condition);
        return Boolean(value);
      }

      return true;
    },
    [],
  );

  // 递归渲染组件
  const renderComponent = useCallback(
    (componentId: string): React.ReactNode => {
      const component = componentMap.get(componentId);
      if (!component) {
        console.warn(`Component not found: ${componentId}`);
        return null;
      }

      // 条件渲染检查
      const visibleBinding = component.bindings.visible;
      const visibleProp = component.props.visible;
      const condition = visibleBinding || visibleProp;
      if (condition !== undefined && !evaluateCondition(condition as string | boolean, localData)) {
        return null; // 条件不满足，不渲染
      }

      // 获取渲染器
      const Renderer = UIComponentRegistry.get(component.type);
      if (!Renderer) {
        console.warn(`Unsupported component type: ${component.type}`);
        return null;
      }

      // 渲染子组件
      const childNodes = component.children.map(renderComponent);

      // 获取验证错误并翻译
      const valuePath = component.bindings.value;
      const errorInfo = valuePath ? validationErrors.get(valuePath) : undefined;
      const validationError = errorInfo ? translateError(errorInfo) : undefined;

      // 构建属性
      const props: UIComponentProps = {
        id: component.id,
        props: component.props,
        bindings: component.bindings,
        events: component.events,
        data: localData,
        onDataChange: handleDataChange,
        onAction: handleAction,
        children: childNodes.length > 0 ? <>{childNodes}</> : undefined,
        // 验证相关
        validationError,
        onBlur: valuePath ? () => handleFieldBlur(valuePath) : undefined,
      };

      return (
        <UIComponentErrorBoundary key={component.id} componentType={component.type} componentId={component.id}>
          <Renderer {...props} />
        </UIComponentErrorBoundary>
      );
    },
    [
      componentMap,
      localData,
      handleDataChange,
      handleAction,
      validationErrors,
      handleFieldBlur,
      translateError,
      evaluateCondition,
    ],
  );

  return <div className="interactive-ui-container">{artifact.root_ids.map(renderComponent)}</div>;
};
