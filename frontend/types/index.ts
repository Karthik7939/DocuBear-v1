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