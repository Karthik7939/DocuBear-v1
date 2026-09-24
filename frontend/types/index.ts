export type DocStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "changes_requested"
  | "published";

export interface Repo {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  connectedAt: string;
  webhookActive: boolean;
  lastWebhookAt?: string;
  gitbookSpaceId?: string;
}

export interface DocVersion {
  id: string;
  repoId: string;
  title: string;
  content: string;
  previousContent?: string;
  hasChanges?: boolean;
  status: DocStatus;
  createdAt: string;
  reviewComment?: string;
}

/** DocVersion for a single-file, on-demand generated document (see /file-docs). */
export interface FileDocVersion extends DocVersion {
  sourcePath: string;
  warnings: string[];
  imports: string[];
  exports: string[];
}

/** Lightweight summary of a previously generated file doc (see /file-docs). */
export interface FileDocSummary {
  id: string;
  repoId: string;
  title: string;
  sourcePath: string;
  createdAt: string;
  hasChanges: boolean;
}

export type RequirementType = "functional" | "non_functional";
export type RequirementStatus = "completed" | "partial" | "missing";

export interface RequirementItem {
  id: string;
  type: RequirementType;
  category: string;
  title: string;
  description: string;
  status: RequirementStatus;
  confidence: number;
  evidence_files: string[];
  evidence_snippet: string;
  remediation: string;
}

export interface RequirementsCountBreakdown {
  total: number;
  completed: number;
  partial: number;
  missing: number;
}

export interface RequirementsAnalysisResult {
  repository: string;
  fileName: string;
  analyzedAt: string;
  overallScore: number;
  functionalScore: number;
  functionalCount: RequirementsCountBreakdown;
  nonFunctionalScore: number;
  nonFunctionalCount: RequirementsCountBreakdown;
  items: RequirementItem[];
  summary: string;
}

export interface RequirementsSummary {
  repository: string;
  repoSlug: string;
  fileName: string;
  analyzedAt: string;
  overallScore: number;
  functionalScore: number;
  functionalCount: RequirementsCountBreakdown;
  nonFunctionalScore: number;
  nonFunctionalCount: RequirementsCountBreakdown;
  passedCount: number;
  partialCount: number;
  missingCount: number;
  totalCount: number;
  summary: string;
}

