import React, { useState } from 'react';
import { ChevronDown, ChevronRight, BookOpen } from 'lucide-react';

const ASSERTION_KEYS = [
  'expected_tools',
  'contains',
  'not_contains',
  'regex',
  'json_valid',
  'json_schema',
  'custom_python',
  'llm_judge',
  'llm_judge_threshold',
  'llm_judge_prompt',
  'sandbox',
  'test_suite',
] as const;

const ASSERTION_EXAMPLES: Record<string, string> = {
  expected_tools: '"expected_tools": ["web_search"]',
  contains: '"state_assertions": [{"type": "contains", "expected": "hello"}]',
  not_contains: '"state_assertions": [{"type": "not_contains", "expected": "error"}]',
  regex: '"state_assertions": [{"type": "regex", "expected": "\\\\d{4}-\\\\d{2}-\\\\d{2}"}]',
  json_valid: '"state_assertions": [{"type": "json_valid", "expected": ""}]',
  json_schema: '"state_assertions": [{"type": "json_schema", "expected": "{\\"required\\": [\\"name\\", \\"age\\"]}"}]',
  custom_python: '"state_assertions": [{"type": "custom_python", "expected": "len(output) < 2000"}]',
  llm_judge: '"semantic_assertions": [{"type": "llm_judge", "expected": "polite and professional"}]',
  llm_judge_threshold:
    '"semantic_assertions": [{"type": "llm_judge", "expected": "covers safety tips", "threshold": 0.7}]',
  llm_judge_prompt:
    '"semantic_assertions": [{"type": "llm_judge", "expected": "accuracy", "judge_prompt": "Judge if {output} meets {criteria}, reply PASS or FAIL: reason"}]',
  sandbox: '"sandbox_assertions": [{"type": "file_exists", "target": "output.txt"}]',
  test_suite:
    '"sandbox_assertions": [{"type": "test_suite", "target": "python -m pytest --junitxml=results.xml", "result_file": "results.xml"}]',
};

export default function CaseFormatReference({ t }: { t: (key: string) => string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b bg-muted/10 text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-4 py-2 w-full text-left text-muted-foreground hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <BookOpen className="w-3.5 h-3.5" />
        <span>{t('caseFormatRef')}</span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1.5 max-h-[200px] overflow-y-auto">
          <p className="text-muted-foreground mb-2">
            {t('caseFormatDesc')} <code className="bg-muted px-1 rounded">{`{"message": "your question"}`}</code>
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b">
                <th className="text-left py-1 pr-3 font-medium w-[140px]">{t('assertionType')}</th>
                <th className="text-left py-1 pr-3 font-medium w-[160px]">{t('assertionDesc')}</th>
                <th className="text-left py-1 font-medium">{t('assertionExample')}</th>
              </tr>
            </thead>
            <tbody>
              {ASSERTION_KEYS.map((key) => (
                <tr key={key} className="border-b border-border/30">
                  <td className="py-1 pr-3 text-primary font-mono">{key}</td>
                  <td className="py-1 pr-3 text-muted-foreground">{t(`assertions.${key}`)}</td>
                  <td className="py-1 font-mono text-foreground/80 break-all">{ASSERTION_EXAMPLES[key]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
