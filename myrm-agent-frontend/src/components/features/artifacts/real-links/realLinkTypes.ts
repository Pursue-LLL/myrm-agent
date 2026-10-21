export type LinkCategory =
  | 'recruitment'
  | 'commerce'
  | 'customer_service'
  | 'documentation'
  | 'social_media'
  | 'general';

export type LinkVerificationStatus =
  | 'aligned'
  | 'placeholder_detected'
  | 'broken'
  | 'unverified';

export interface DetectedLinkEntity {
  id: string;
  originalHref: string;
  anchorText: string;
  category: LinkCategory;
  status: LinkVerificationStatus;
  targetEntityName?: string;
  resolvedRealUrl?: string;
  confidenceScore: number;
  reason?: string;
}

export interface RealLinkAlignmentState {
  codeSnippet: string;
  detectedLinks: DetectedLinkEntity[];
  isScanning: boolean;
  alignmentRate: number;
  isApplied: boolean;

  scanCodeSnippet: (code: string) => DetectedLinkEntity[];
  alignLinkToRealEntity: (
    linkId: string,
    resolvedUrl: string,
    entityName: string
  ) => void;
  batchAlignPlaceholders: () => void;
  applyAlignedCode: () => string;
  setCodeSnippet: (code: string) => void;
  resetState: () => void;
}
