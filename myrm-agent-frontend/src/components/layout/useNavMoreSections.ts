/**
 * [INPUT]
 * - next-intl messages (nav, settings.menu, growthDashboard and each tool panel's own namespace)
 * - useConfigStore::enableEvalLab (POS: whether the eval lab is offered)
 * - useWorkbenchStore (POS: workbench visibility)
 * - lib/utilityPanelEvents::UTILITY_PANEL_EVENTS (POS: open events of the globally mounted panels)
 *
 * [OUTPUT]
 * - useNavMoreSections: the destinations and tools grouped behind the rail's "More" entry
 * - NavMoreSection, NavMoreItem, NavMoreLinkItem, NavMoreActionItem
 *
 * [POS]
 * Single source of the rail's secondary entries. The rail itself keeps only the primary destinations; everything
 * else lives here, grouped by what it is for, so a new entry never adds another icon to the rail.
 */

import type { ComponentType } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  Brain,
  FlaskConical,
  FolderTree,
  PanelRightOpen,
  Plug,
  Presentation,
  Shield,
  TrendingUp,
  Wand2,
  Wrench,
} from 'lucide-react';
import { InvestigationIcon } from 'hugeicons-react';
import { PuzzlePiece, TreeStructure } from '@phosphor-icons/react';
import useConfigStore from '@/store/useConfigStore';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';

type NavMoreIcon = ComponentType<{ size?: number; className?: string }>;

interface NavMoreItemBase {
  id: string;
  label: string;
  icon: NavMoreIcon;
}

export interface NavMoreLinkItem extends NavMoreItemBase {
  kind: 'link';
  href: string;
  /** Warms the code-editor chunk while the pointer rests on the row, so the page opens without a wait. */
  preloadsEditor?: boolean;
  /** A connection dot at the end of the row. */
  connection?: 'connected' | 'disconnected';
}

export interface NavMoreActionItem extends NavMoreItemBase {
  kind: 'action';
  shortcut: string;
  action: () => void;
  /** Set only for panels that dock beside the page; modal panels cover the menu, so they never show a state. */
  pressed?: boolean;
}

export type NavMoreItem = NavMoreLinkItem | NavMoreActionItem;

export interface NavMoreSection {
  id: 'monitor' | 'extend' | 'tools';
  title: string;
  items: NavMoreItem[];
}

const openPanel = (eventName: string) => {
  window.dispatchEvent(new CustomEvent(eventName));
};

export function useNavMoreSections(extensionConnected: boolean): NavMoreSection[] {
  const t = useTranslations();
  const enableEvalLab = useConfigStore((state) => state.enableEvalLab);
  const toggleWorkbench = useWorkbenchStore((state) => state.toggleOpen);
  const workbenchOpen = useWorkbenchStore((state) => state.isOpen);

  const monitor: NavMoreItem[] = [
    { kind: 'link', id: 'runs', icon: Activity, label: t('nav.runs'), href: '/runs' },
    { kind: 'link', id: 'health', icon: InvestigationIcon, label: t('nav.health'), href: '/health' },
    { kind: 'link', id: 'security-center', icon: Shield, label: t('nav.securityCenter'), href: '/security' },
    { kind: 'link', id: 'journey', icon: TrendingUp, label: t('growthDashboard.title'), href: '/journey' },
  ];
  if (enableEvalLab) {
    monitor.push({
      kind: 'link',
      id: 'eval-lab',
      icon: FlaskConical,
      label: t('nav.evalLab'),
      href: '/eval-lab',
      preloadsEditor: true,
    });
  }

  const extend: NavMoreItem[] = [
    {
      kind: 'link',
      id: 'batch-directories',
      icon: FolderTree,
      label: t('nav.batchDirectories'),
      href: '/batch-directories',
    },
    {
      kind: 'link',
      id: 'skills',
      icon: Wand2,
      label: t('settings.menu.skills'),
      href: '/settings/skills',
      preloadsEditor: true,
    },
    { kind: 'link', id: 'mcp', icon: Plug, label: t('settings.menu.mcp'), href: '/settings/mcp' },
    {
      kind: 'link',
      id: 'extension-bridge',
      icon: PuzzlePiece,
      label: extensionConnected ? t('nav.extensionConnected') : t('nav.extensionDisconnected'),
      href: '/settings/extensionBridge',
      connection: extensionConnected ? 'connected' : 'disconnected',
    },
  ];

  const tools: NavMoreItem[] = [
    {
      kind: 'action',
      id: 'workbench',
      icon: PanelRightOpen,
      label: t('workbench.hudTrigger'),
      shortcut: t('workbench.shortcutHint'),
      action: toggleWorkbench,
      pressed: workbenchOpen,
    },
    {
      kind: 'action',
      id: 'session-map',
      icon: TreeStructure,
      label: t('sessionMap.hudTrigger'),
      shortcut: t('sessionMap.shortcutHint'),
      action: () => openPanel(UTILITY_PANEL_EVENTS.sessionMap),
    },
    {
      kind: 'action',
      id: 'presentation',
      icon: Presentation,
      label: t('presentation.menuLabel'),
      shortcut: t('presentation.shortcutHint'),
      action: () => openPanel(UTILITY_PANEL_EVENTS.presentation),
    },
    {
      kind: 'action',
      id: 'tool-picker',
      icon: Wrench,
      label: t('toolPicker.menuLabel'),
      shortcut: t('toolPicker.shortcutHint'),
      action: () => openPanel(UTILITY_PANEL_EVENTS.toolPicker),
    },
    {
      kind: 'action',
      id: 'assistant',
      icon: Brain,
      label: t('systemAssistant.assistantName'),
      shortcut: t('systemAssistant.shortcutHint'),
      action: () => openPanel(UTILITY_PANEL_EVENTS.assistant),
    },
  ];

  return [
    { id: 'monitor', title: t('nav.moreMonitor'), items: monitor },
    { id: 'extend', title: t('nav.moreExtend'), items: extend },
    { id: 'tools', title: t('nav.tools'), items: tools },
  ];
}
