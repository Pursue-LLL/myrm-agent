export type FourZoneCategory =
  | '01_raw_materials'
  | '02_process_drafts'
  | '03_content_bases'
  | '04_deliverables';

export interface ProposedFileMove {
  sourcePath: string;
  fileName: string;
  targetZone: FourZoneCategory;
  targetPath: string;
  isReadOnly: boolean;
  rationale: string;
}

export interface GeneratedScaffoldDoc {
  path: string;
  title: string;
  draftContent: string;
  purpose: string;
}

export type ScaffoldingStatus = 'pending_review' | 'confirmed' | 'cancelled';

export interface ScaffoldingProposal {
  id: string;
  workspacePath: string;
  matchedUtterance: string;
  moves: ProposedFileMove[];
  generatedDocs: GeneratedScaffoldDoc[];
  status: ScaffoldingStatus;
  createdAt: number;
}
