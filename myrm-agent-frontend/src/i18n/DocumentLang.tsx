'use client';

import { useEffect } from 'react';

interface DocumentLangProps {
  locale: string;
}

/** Syncs `<html lang>` after cookie locale resolves inside Suspense. */
export default function DocumentLang({ locale }: DocumentLangProps) {
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return null;
}
