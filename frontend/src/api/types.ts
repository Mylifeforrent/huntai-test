/** Domain enums strictly ⊆ problem_model.md / api_spec.md §1.4 */

export const TEST_RUN_STATUSES = [
  "PENDING",
  "VALIDATING",
  "RUNNING",
  "WAITING_EXTERNAL",
  "WAITING_APPROVAL",
  "STOPPING",
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMEOUT",
] as const;
export type TestRunStatus = (typeof TEST_RUN_STATUSES)[number];

export const TEST_RUN_TERMINALS = ["SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"] as const;

export const TEST_CASE_LIFECYCLES = ["DRAFT", "PENDING_REVIEW", "ACTIVE", "DEPRECATED"] as const;
export type TestCaseLifecycle = (typeof TEST_CASE_LIFECYCLES)[number];

export const TEST_CASE_VALIDITIES = ["valid", "invalid"] as const;
export type TestCaseValidity = (typeof TEST_CASE_VALIDITIES)[number];

export const APPROVAL_STATUSES = [
  "CREATED",
  "PENDING",
  "APPROVED",
  "EXECUTED",
  "REJECTED",
  "EXPIRED",
] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

export const EXECUTION_RESULTS = ["ok", "failed", "unknown"] as const;
export type ExecutionResult = (typeof EXECUTION_RESULTS)[number];

export const ENVIRONMENT_STATUSES = ["PENDING_APPROVAL", "ACTIVE", "DEGRADED", "DISABLED"] as const;
export type EnvironmentStatus = (typeof ENVIRONMENT_STATUSES)[number];

export const RELEASE_STATUSES = [
  "DRAFT",
  "PENDING_CONFIRM",
  "SUBMITTED",
  "READY",
  "FAILED_RETRYABLE",
  "CANCELLED",
] as const;
export type ReleaseStatus = (typeof RELEASE_STATUSES)[number];

export const GATE_RESULTS = ["pass", "fail", "waived"] as const;
export type GateResult = (typeof GATE_RESULTS)[number];

export const CLUSTER_CATEGORIES = [
  "env_down",
  "auth_expired",
  "locator_stale",
  "assertion_real_bug",
  "flaky",
  "data_issue",
  "unknown",
] as const;
export type ClusterCategory = (typeof CLUSTER_CATEGORIES)[number];

export const BLOCKING_JUDGMENTS = ["blocker", "non_blocker", "uncertain"] as const;
export type BlockingJudgment = (typeof BLOCKING_JUDGMENTS)[number];

export const EXECUTION_SOURCES = ["script", "agent", "external_ci"] as const;
export type ExecutionSource = (typeof EXECUTION_SOURCES)[number];

export const PROJECT_ROLES = ["owner", "admin", "tester", "viewer"] as const;
export type ProjectRole = (typeof PROJECT_ROLES)[number];

export const RISK_LEVELS = ["L0", "L1", "L2", "L3", "L4"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export const ERROR_CLASSES = ["network", "permission", "business"] as const;
export type ErrorClass = (typeof ERROR_CLASSES)[number];

export interface ApiErrorBody {
  code: string;
  class: ErrorClass;
  subclass: string;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
  trace_id: string;
  resource_type?: string;
  resource_id?: string;
}

export interface ErrorEnvelope {
  error: ApiErrorBody;
}

export interface PageCursor {
  next_cursor: string | null;
  has_more: boolean;
  limit?: number;
}

export interface ListEnvelope<T> {
  data: { items: T[] };
  page: PageCursor;
}

export interface ResourceEnvelope<T> {
  data: T;
}

export interface CommandReceipt {
  id: string;
  command_type: string;
  status: "accepted" | "running" | "succeeded" | "failed" | "partial";
  accepted_at: string;
  resource_type?: string;
  resource_id?: string;
  idempotency_key?: string;
  poll?: { path?: string; sse_path?: string };
  error?: ApiErrorBody;
}

export interface MeProjection {
  user_id: string;
  display_name: string;
  organization_id: string;
  projects: Array<{
    project_id: string;
    name: string;
    role: ProjectRole;
  }>;
}

export interface WorkbenchProjection {
  pending_approvals: unknown[];
  active_runs: unknown[];
  gate_anomalies: unknown[];
  quota: unknown;
}

export type JsonObject = Record<string, unknown>;
