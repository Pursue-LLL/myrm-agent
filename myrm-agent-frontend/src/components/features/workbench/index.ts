/**
 * [INPUT]
 * - ./MultiTabWorkbench
 * - ./WorkbenchToggleTrigger
 * - ./tabs/*
 *
 * [OUTPUT]
 * - Unified exports for Independent Multi-Tab Auxiliary Workbench (Item 25)
 *
 * [POS]
 * Facade entry for workbench module.
 */

export { MultiTabWorkbench } from './MultiTabWorkbench';
export { WorkbenchToggleTrigger } from './WorkbenchToggleTrigger';
export { WorkbenchFileExplorer } from './tabs/WorkbenchFileExplorer';
export { WorkbenchDiffViewer } from './tabs/WorkbenchDiffViewer';
export { WorkbenchTerminal } from './tabs/WorkbenchTerminal';
export { WorkbenchPluginCenter } from './tabs/WorkbenchPluginCenter';
