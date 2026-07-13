import manifest from '../../locales/namespaces/manifest.json';

import type { Locale } from './config';

export type LocaleNamespace = (typeof manifest.namespaces)[number];
export type SettingsSection = (typeof manifest.settingsSections)[number];

/** Full locale messages shape (monolith-equivalent). */
export type Messages = typeof import('#locales/zh.json').default;

/** Namespaces omitted from SSR — loaded client-side after mount. */
export const DEFERRED_NAMESPACES = ['channels', 'memory'] as const satisfies readonly LocaleNamespace[];

export const LOCALE_NAMESPACES = manifest.namespaces.filter(
  (namespace): namespace is LocaleNamespace => namespace !== 'settings',
);

export const SETTINGS_SECTIONS = manifest.settingsSections as readonly SettingsSection[];

/** settings/* sections deferred except menu (NavBar quick links). */
export const DEFERRED_SETTINGS_SECTIONS = SETTINGS_SECTIONS.filter(
  (section): section is SettingsSection => section !== 'menu',
);

/** Top-level namespaces inlined in SSR shell (everything except deferred). */
export const SSR_SHELL_NAMESPACES = LOCALE_NAMESPACES.filter(
  (namespace): namespace is LocaleNamespace => !(DEFERRED_NAMESPACES as readonly string[]).includes(namespace),
);

export const SUPPORTED_LOCALES = manifest.languages as readonly Locale[];

export function isDeferredNamespace(namespace: string): boolean {
  return (DEFERRED_NAMESPACES as readonly string[]).includes(namespace);
}
