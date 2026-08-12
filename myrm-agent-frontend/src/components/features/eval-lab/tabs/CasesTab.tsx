import { useTranslations } from 'next-intl';

import CaseFormatReference from '../components/CaseFormatReference';
import { LazyMonacoEditor as Editor } from '@/components/features/app-shell/lazy-monaco-editor';

interface CasesTabProps {
  casesDraft: string;
  onDraftChange: (value: string) => void;
}

export default function CasesTab({ casesDraft, onDraftChange }: CasesTabProps) {
  const t = useTranslations('evalLab');

  return (
    <>
      <CaseFormatReference t={t} />
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          defaultLanguage="json"
          theme="vs-dark"
          value={casesDraft}
          onChange={(value) => onDraftChange(value || '')}
          options={{ minimap: { enabled: false }, wordWrap: 'on' }}
        />
      </div>
    </>
  );
}
