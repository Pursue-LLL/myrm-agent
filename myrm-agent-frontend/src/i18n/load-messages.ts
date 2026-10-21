/**
 * [INPUT]
 * - locale-manifest.ts (POS: SSR/deferred namespace manifest)
 * - locales/namespaces/{locale}/*.json (POS: split locale files from split-locale-namespaces.mjs)
 *
 * [OUTPUT]
 * loadShellMessages, loadDeferredMessages, loadFullMessages
 *
 * [POS]
 * Server-only locale file loader. SSR ships shell namespaces; deferred chunks via /api/i18n/deferred.
 */
import 'server-only';

import { readFile } from 'node:fs/promises';
import path from 'node:path';

import type { Locale } from './config';
import {
  DEFERRED_NAMESPACES,
  DEFERRED_SETTINGS_SECTIONS,
  SSR_SHELL_NAMESPACES,
  SSR_SHELL_SETTINGS_SECTIONS,
  SETTINGS_SECTIONS,
  type Messages,
  type SettingsSection,
} from './locale-manifest';
import { mergeMessages } from './merge-messages';

const localesRoot = path.join(process.cwd(), 'locales/namespaces');

/** macOS/Windows: agent.json and Agent.json collide — encode mixed-case namespaces. */
function namespaceFilename(namespace: string): string {
  if (namespace !== namespace.toLowerCase()) {
    return `@${namespace}.json`;
  }
  return `${namespace}.json`;
}

async function readNamespaceJson<T>(segments: string[]): Promise<T> {
  const filePath = path.join(localesRoot, ...segments);
  const raw = await readFile(filePath, 'utf-8');
  return JSON.parse(raw) as T;
}

async function loadNamespace(locale: Locale, namespace: string): Promise<Messages[keyof Messages]> {
  return readNamespaceJson<Messages[keyof Messages]>([locale, namespaceFilename(namespace)]);
}

async function loadSettingsSection(
  locale: Locale,
  section: SettingsSection,
): Promise<Messages['settings'][SettingsSection]> {
  return readNamespaceJson<Messages['settings'][SettingsSection]>([locale, 'settings', `${section}.json`]);
}

async function loadShellSettingsSections(locale: Locale): Promise<Partial<Messages['settings']>> {
  return loadSettingsSections(locale, SSR_SHELL_SETTINGS_SECTIONS);
}

async function loadSettingsSections(
  locale: Locale,
  sections: readonly SettingsSection[],
): Promise<Partial<Messages['settings']>> {
  const entries = await Promise.all(
    sections.map(async (section) => [section, await loadSettingsSection(locale, section)] as const),
  );

  return Object.fromEntries(entries) as Partial<Messages['settings']>;
}

export async function loadShellMessages(locale: Locale): Promise<Messages> {
  const entries = await Promise.all(
    SSR_SHELL_NAMESPACES.map(async (namespace) => [namespace, await loadNamespace(locale, namespace)] as const),
  );

  const settingsSections = await loadShellSettingsSections(locale);
  const messages = Object.fromEntries(entries) as Record<string, unknown>;
  messages.settings = settingsSections;

  return messages as Messages;
}

export async function loadDeferredMessages(locale: Locale): Promise<Partial<Messages>> {
  const deferredEntries = await Promise.all(
    DEFERRED_NAMESPACES.map(async (namespace) => [namespace, await loadNamespace(locale, namespace)] as const),
  );

  const settingsSections = await loadSettingsSections(locale, DEFERRED_SETTINGS_SECTIONS);

  const partial: Partial<Messages> = Object.fromEntries(deferredEntries) as Partial<Messages>;
  partial.settings = settingsSections as Messages['settings'];

  return partial;
}

export async function loadFullMessages(locale: Locale): Promise<Messages> {
  const [shell, deferred] = await Promise.all([loadShellMessages(locale), loadDeferredMessages(locale)]);

  return mergeMessages(shell, deferred);
}

export { SETTINGS_SECTIONS };
