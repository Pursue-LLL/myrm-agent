/**
 * UI 组件注册表
 *
 * 维护组件类型到 React 组件的映射（安全白名单）。
 * Agent 只能渲染注册表中的组件类型。
 */

import React from 'react';
import { UIComponentType } from '@/store/chat/types';

// 基础组件导入
import { UIText } from './components/UIText';
import { UIButton } from './components/UIButton';
import { UITextField } from './components/UITextField';
import { UITextarea } from './components/UITextarea';
import { UISelect } from './components/UISelect';
import { UIDatePicker } from './components/UIDatePicker';
import { UISlider } from './components/UISlider';
import { UICheckbox } from './components/UICheckbox';
import { UISwitch } from './components/UISwitch';
import { UICard } from './components/UICard';
import { UIContainer } from './components/UIContainer';
import { UIDivider } from './components/UIDivider';
import { UITable } from './components/UITable';
import { UIButtonGroup } from './components/UIButtonGroup';
import { UIBadge } from './components/UIBadge';
import { UIProgress } from './components/UIProgress';
import { UIChart } from './components/UIChart';
import { UIImage } from './components/UIImage';
import { UITimePicker } from './components/UITimePicker';
import { UIRadio } from './components/UIRadio';
import { UIGrid } from './components/UIGrid';
import { UITabs } from './components/UITabs';

// 组件属性类型
export interface UIComponentProps {
  id: string;
  props: Record<string, unknown>;
  bindings: Record<string, string>;
  events: Record<string, string>;
  children?: React.ReactNode;
  className?: string;
  // 数据上下文
  data: Record<string, unknown>;
  // 数据更新回调
  onDataChange: (path: string, value: unknown) => void;
  // 动作触发回调
  onAction: (actionId: string) => void;
  // 验证错误消息（已翻译，可选）
  validationError?: string;
  // 触发字段验证回调（可选）
  onBlur?: (path: string) => void;
}

// 组件类型定义
type UIComponentRenderer = React.FC<UIComponentProps>;

// 组件注册表
const componentRegistry: Record<UIComponentType, UIComponentRenderer> = {
  // 基础组件
  text: UIText,
  button: UIButton,
  button_group: UIButtonGroup,

  // 表单组件
  text_field: UITextField,
  textarea: UITextarea,
  select: UISelect,
  date_picker: UIDatePicker,
  time_picker: UITimePicker,
  slider: UISlider,
  checkbox: UICheckbox,
  radio: UIRadio,
  switch: UISwitch,

  // 布局组件
  container: UIContainer,
  card: UICard,
  divider: UIDivider,
  grid: UIGrid,
  tabs: UITabs,

  // 数据展示组件
  table: UITable,
  list: UIContainer,
  image: UIImage,
  chart: UIChart,
  progress: UIProgress,
  badge: UIBadge,
};

/**
 * 获取组件渲染器
 */
export function getComponentRenderer(type: UIComponentType): UIComponentRenderer | null {
  return componentRegistry[type] || null;
}

/**
 * 检查组件类型是否支持
 */
export function isComponentSupported(type: string): type is UIComponentType {
  return type in componentRegistry;
}

/**
 * 组件注册表
 */
export const UIComponentRegistry = {
  get: getComponentRenderer,
  isSupported: isComponentSupported,
  types: Object.keys(componentRegistry) as UIComponentType[],
};
