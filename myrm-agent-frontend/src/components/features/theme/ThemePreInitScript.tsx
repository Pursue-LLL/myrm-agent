'use client';

import { useServerInsertedHTML } from 'next/navigation';
import { THEME_PRE_INIT_SCRIPT } from './theme-pre-init-script';

export function ThemePreInitScript() {
  useServerInsertedHTML(() => (
    <script
      id="theme-pre-init"
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: THEME_PRE_INIT_SCRIPT }}
    />
  ));

  return null;
}
