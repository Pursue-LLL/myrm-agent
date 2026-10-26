/**
 * [INPUT]
 * - ./MultiTabWorkbench
 * - ./WorkbenchToggleTrigger
 * - ./tabs/*
 *
 * [OUTPUT]
 * - Unified exports for the auxiliary workbench
 *
 * [POS]
 * Facade entry for workbench module.
 */

export { MultiTabWorkbench } from './MultiTabWorkbench';
export { WorkbenchToggleTrigger } from './WorkbenchToggleTrigger';
export { WorkbenchFileExplorer } from './tabs/WorkbenchFileExplorer';
export { WorkbenchTerminal } from './tabs/WorkbenchTerminal';
