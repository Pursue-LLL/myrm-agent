import { createContext, useContext, useState, type ReactNode } from 'react';

/**
 * Wiki 面板测试的替身组件。子面板 / 对话框 / 选择器全部换成「记下 props 的标记节点」，
 * 测试通过 `stubProps(name)` 读到最近一次渲染收到的 props（含回调），再用 `stubMounts(name)` 判断是否重新挂载。
 */

const latestProps = new Map<string, Record<string, unknown>>();
const mountCounts = new Map<string, number>();

export const resetStubs = (): void => {
  latestProps.clear();
  mountCounts.clear();
};

/** 最近一次渲染收到的 props；组件从未渲染时抛错，避免对不存在的子面板断言。 */
export function stubProps<T extends Record<string, unknown> = Record<string, unknown>>(name: string): T {
  const props = latestProps.get(name);
  if (!props) {
    throw new Error(`stub ${name} was never rendered`);
  }
  return props as T;
}

/** 该替身累计挂载的次数（key 变化或卸载后重进都会加一）。 */
export const stubMounts = (name: string): number => mountCounts.get(name) ?? 0;

export function propStub(name: string) {
  return function Stub(props: Record<string, unknown>): ReactNode {
    latestProps.set(name, props);
    useState(() => {
      mountCounts.set(name, (mountCounts.get(name) ?? 0) + 1);
      return null;
    });
    return <div data-testid={name} />;
  };
}

export const namedModule = (name: string, exportName: string) => ({ [exportName]: propStub(name) });
export const defaultModule = (name: string) => ({ default: propStub(name) });

interface ChildrenProps {
  children?: ReactNode;
}

const Passthrough = ({ children }: ChildrenProps) => <div>{children}</div>;

const SelectContext = createContext<(value: string) => void>(() => undefined);

interface SelectProps extends ChildrenProps {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
}

/** 选项即可点击的 option: 点选项触发 onValueChange，和真实下拉里选中一项等价。 */
function Select({ value, onValueChange, disabled, children }: SelectProps) {
  return (
    <SelectContext.Provider value={onValueChange}>
      <div data-slot="select" data-value={value} data-disabled={disabled ? '1' : '0'}>
        {children}
      </div>
    </SelectContext.Provider>
  );
}

function SelectItem({ value, children }: ChildrenProps & { value: string }) {
  const select = useContext(SelectContext);
  return <option onClick={() => select(value)}>{children}</option>;
}

export const selectModule = {
  Select,
  SelectContent: Passthrough,
  SelectItem,
  SelectTrigger: Passthrough,
  // 与真实组件一致：给了子节点就显示子节点，否则显示占位文案。
  SelectValue: ({ placeholder, children }: ChildrenProps & { placeholder?: string }) => (
    <span data-slot="select-value">{children ?? placeholder}</span>
  ),
};

const TabsContext = createContext<{ value: string; onValueChange: (value: string) => void }>({
  value: '',
  onValueChange: () => undefined,
});

function Tabs({
  value,
  onValueChange,
  children,
}: ChildrenProps & { value: string; onValueChange: (v: string) => void }) {
  return (
    <TabsContext.Provider value={{ value, onValueChange }}>
      <div data-slot="tabs" data-value={value}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

function TabsTrigger({
  value,
  children,
  'data-testid': testId,
}: ChildrenProps & { value: string; 'data-testid'?: string }) {
  const tabs = useContext(TabsContext);
  return (
    <button
      type="button"
      role="tab"
      aria-selected={tabs.value === value}
      data-testid={testId}
      onClick={() => tabs.onValueChange(value)}
    >
      {children}
    </button>
  );
}

function TabsContent({ value, children }: ChildrenProps & { value: string }) {
  const tabs = useContext(TabsContext);
  return tabs.value === value ? <div role="tabpanel">{children}</div> : null;
}

export const tabsModule = { Tabs, TabsList: Passthrough, TabsTrigger, TabsContent };

/** 记下 provider 收到的范围值并原样渲染子节点，用来断言面板向子面板提供了怎样的范围上下文。 */
export const scopeProviderModule = {
  WikiAgentScopeProvider: function WikiAgentScopeProviderStub({
    children,
    ...value
  }: ChildrenProps & Record<string, unknown>) {
    latestProps.set('WikiAgentScopeProvider', value);
    return <>{children}</>;
  },
};
