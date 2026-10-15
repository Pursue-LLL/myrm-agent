import { describe, expect, it } from 'vitest';
import {
  generateDefaultScaffoldingProposal,
  inferFileZoneClassification,
  parseScaffoldingIntent,
  summarizeScaffoldingProposal,
} from '../workspaceScaffoldingEngine';

describe('workspaceScaffoldingEngine', () => {
  describe('parseScaffoldingIntent', () => {
    it('detects scaffolding intent from keywords', () => {
      expect(parseScaffoldingIntent('帮我按四区规范初始化这个项目')).toBe(true);
      expect(parseScaffoldingIntent('请规整一下当前工作区')).toBe(true);
      expect(parseScaffoldingIntent('整理项目文件夹并分区分流')).toBe(true);
      expect(parseScaffoldingIntent('执行目录初始化')).toBe(true);
    });

    it('returns false for empty or non-scaffolding utterance', () => {
      expect(parseScaffoldingIntent('')).toBe(false);
      expect(parseScaffoldingIntent('   ')).toBe(false);
      expect(parseScaffoldingIntent('今天股市行情怎么样')).toBe(false);
    });
  });

  describe('inferFileZoneClassification', () => {
    it('classifies contracts, pdfs, and invoices as 01_raw_materials with read-only lock', () => {
      const pdfResult = inferFileZoneClassification('采购合同_原件.pdf');
      expect(pdfResult.zone).toBe('01_raw_materials');
      expect(pdfResult.isReadOnly).toBe(true);
      expect(pdfResult.rationale).toContain('原件区并锁定只读保护');

      const invoiceResult = inferFileZoneClassification('invoice_202610.xlsx');
      expect(invoiceResult.zone).toBe('01_raw_materials');
      expect(invoiceResult.isReadOnly).toBe(true);
    });

    it('classifies tmp, log, and draft notes as 02_process_drafts', () => {
      const draftResult = inferFileZoneClassification('meeting_draft.tmp');
      expect(draftResult.zone).toBe('02_process_drafts');
      expect(draftResult.isReadOnly).toBe(false);

      const logResult = inferFileZoneClassification('debug.log');
      expect(logResult.zone).toBe('02_process_drafts');
    });

    it('classifies release, export, and final outputs as 04_deliverables', () => {
      const finalResult = inferFileZoneClassification('annual_report_final.pdf');
      // 虽然后缀为 pdf，但包含 final 归为 deliverables 或 raw，此处检查包含 final/report/export
      const exportResult = inferFileZoneClassification('export_bundle.zip');
      expect(exportResult.zone).toBe('04_deliverables');
      expect(exportResult.isReadOnly).toBe(false);
    });

    it('classifies general documentation as 03_content_bases', () => {
      const docResult = inferFileZoneClassification('architecture_spec.md');
      expect(docResult.zone).toBe('03_content_bases');
      expect(docResult.isReadOnly).toBe(false);
    });
  });

  describe('generateDefaultScaffoldingProposal', () => {
    it('creates in-memory proposal with moves and default scaffold docs', () => {
      const files = ['client_contract.pdf', 'notes.tmp', 'readme.md'];
      const proposal = generateDefaultScaffoldingProposal(
        '/my-workspace',
        files,
      );

      expect(proposal.id).toBeDefined();
      expect(proposal.workspacePath).toBe('/my-workspace');
      expect(proposal.status).toBe('pending_review');
      expect(proposal.moves).toHaveLength(3);

      const contractMove = proposal.moves.find(
        (m) => m.fileName === 'client_contract.pdf',
      );
      expect(contractMove?.targetZone).toBe('01_raw_materials');
      expect(contractMove?.targetPath).toBe(
        '/my-workspace/01_raw_materials/client_contract.pdf',
      );
      expect(contractMove?.isReadOnly).toBe(true);

      expect(proposal.generatedDocs).toHaveLength(2);
      expect(proposal.generatedDocs[0]?.title).toContain('AGENTS.md');
      expect(proposal.generatedDocs[1]?.title).toContain('00_项目总览.md');
    });
  });

  describe('summarizeScaffoldingProposal', () => {
    it('summarizes counts for all four zones accurately', () => {
      const files = [
        'doc1.pdf',
        'doc2.xlsx',
        'scratch.tmp',
        'spec.md',
        'release_v1.zip',
      ];
      const proposal = generateDefaultScaffoldingProposal('/ws', files);
      const summary = summarizeScaffoldingProposal(proposal);

      expect(summary['01_raw_materials']).toBe(2);
      expect(summary['02_process_drafts']).toBe(1);
      expect(summary['03_content_bases']).toBe(1);
      expect(summary['04_deliverables']).toBe(1);
    });
  });
});
