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

export interface ProjectListItem {
  id: string;
  name: string;
  version: number;
  my_role: ProjectRole;
  jira_project_key?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectActivityItem {
  occurred_at: string;
  summary: string;
  resource_type?: string | null;
  resource_id?: string | null;
  audit_event_id?: string | null;
}

export interface ProjectOverview {
  id: string;
  name: string;
  version: number;
  my_role: ProjectRole;
  jira: { project_key: string | null };
  connector_health: Array<{
    connector_id: string;
    type: string;
    healthy: boolean;
    name?: string;
    last_checked_at?: string | null;
    latency_ms?: number | null;
  }>;
  recent_activity: ProjectActivityItem[];
  bind_env_ids?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface ProjectMemberItem {
  user_id: string;
  role: ProjectRole;
  display_name?: string;
  email?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectMember {
  project_id: string;
  user_id: string;
  role: ProjectRole;
  display_name?: string;
}

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

export interface MeUser {
  id: string;
  display_name: string;
  email?: string;
  is_disabled: boolean;
}

export interface MeOrganization {
  id: string;
  name: string;
  slug: string;
  version: number;
  is_active: boolean;
  capability_controls: Record<string, unknown>;
  siem_export_enabled?: boolean;
}

export interface MeMembership {
  project_id: string;
  project_name?: string | null;
  role: ProjectRole;
}

/** API-005 `GET /api/v1/me` data payload. */
export interface MeProjection {
  user: MeUser;
  organization: MeOrganization;
  memberships: MeMembership[];
  reauth_required: boolean;
}

export interface OidcStartResponse {
  authorization_url: string;
}

export interface ReauthResponse {
  reauth_satisfied: boolean;
  authorization_url?: string;
}

export interface SessionMetadata {
  expires_at: string;
  reauth_required: boolean;
}

export interface WorkbenchProjection {
  pending_approvals: unknown[];
  active_runs: unknown[];
  gate_anomalies: unknown[];
  quota: unknown;
}

export type JsonObject = Record<string, unknown>;

export const POLICY_GATES = ["ALLOW", "DENY", "REQUIRE_APPROVAL", "REQUIRE_REAUTH"] as const;
export type PolicyGate = (typeof POLICY_GATES)[number];

export const PREVIEW_ACTION_TYPES = [
  "jira_write",
  "heal_apply",
  "perf_high_risk",
  "release_push",
  "env_register",
  "agent_tool_action",
  "gate_waiver",
  "kill_switch_restore",
] as const;
export type PreviewActionType = (typeof PREVIEW_ACTION_TYPES)[number];

export interface ActionPreviewRequest {
  action_type: PreviewActionType;
  target_object_type: string;
  target_object_id: string;
  payload: JsonObject;
  project_id?: string;
  expected_target_version?: number;
}

export interface ActionPreview {
  preview_id: string;
  action_type: PreviewActionType | "copilot_write";
  gate: PolicyGate;
  param_hash: string;
  card_payload: JsonObject;
  side_effect_level: RiskLevel;
  created_at: string;
  approval_request_id?: string;
  bound_hash?: string;
  target: {
    object_type: string;
    object_id: string;
    version?: number;
  };
}

export const APPROVAL_PERSPECTIVES = ["inbox", "initiated", "all"] as const;
export type ApprovalPerspective = (typeof APPROVAL_PERSPECTIVES)[number];

export interface ApprovalRequestListItem {
  id: string;
  action_type: PreviewActionType;
  target_object_type: string;
  target_object_id: string;
  param_hash: string;
  card_payload: JsonObject;
  status: ApprovalStatus | string;
  execution_result?: "ok" | "failed" | "unknown" | null;
  initiator_id: string;
  approver_id?: string;
  expires_at: string;
  escalate_to?: string;
  expired_reason?: "ttl" | "withdrawn" | "invalidated" | null;
  origin_request_id?: string;
  side_effect_level: RiskLevel;
  four_eyes_self?: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRequestDetail extends ApprovalRequestListItem {
  action_payload_redacted?: JsonObject;
  snapshot_ref?: string | null;
  original_initiator_id?: string;
  execution_reconciliation?: {
    needed: boolean;
    external_request_id?: string | null;
  } | null;
}

export const DATA_CLASSIFICATIONS = ["Public", "Internal", "Confidential", "Restricted"] as const;
export type DataClassification = (typeof DATA_CLASSIFICATIONS)[number];

export const AI_INVOCATION_RESULTS = ["ok", "degraded", "refused"] as const;
export type AiInvocationResult = (typeof AI_INVOCATION_RESULTS)[number];

export interface ModelRouteListItem {
  id: string;
  task_type: string;
  data_classification: DataClassification;
  provider_allowlist: string[];
  max_cost: number;
  fallback?: Record<string, unknown> | null;
  require_prompt_version: boolean;
  require_structured_output: boolean;
  credential_present: boolean;
  version: number;
  created_at?: string;
  updated_at?: string;
}

export interface ConnectionTestResult {
  reachable: boolean;
  latency_ms: number;
  error_class?: string;
}

export interface AIInvocationLogListItem {
  id: string;
  created_at: string;
  created_by: string;
  user_id?: string;
  model: string;
  prompt_version: string;
  usage: Record<string, unknown>;
  cost: number;
  latency_ms: number;
  data_classification: DataClassification;
  result: AiInvocationResult;
  skill_version_id?: string;
  model_route_id?: string;
  copilot_session_id?: string;
}

export interface ApprovalResubmissionResult {
  origin_request_id: string;
  origin_final_status: "EXPIRED" | "REJECTED" | "EXECUTED";
  new_approval_request: ApprovalRequestListItem;
}

export interface OrgQuotaCurrent {
  version: number;
  token_budget: number;
  token_reserved: number;
  token_consumed: number;
  token_remaining: number;
  executor_slot_quota: number;
  executor_slots_in_use?: number;
  perf_concurrency_quota: number;
  perf_concurrency_in_use?: number;
  updated_at?: string;
}

export interface ProjectQuotaView {
  project_id: string;
  org_quota_version: number;
  view: {
    token_consumed_in_project?: number;
    org_remaining: OrgQuotaCurrent;
  };
}

export interface AiCostDashboardTotals {
  token_usage: Record<string, number>;
  cost: number;
  invocation_count: number;
  adoption_rate?: number;
  degrade_rate?: number;
  cost_per_workflow?: Record<string, number>;
}

export interface AiCostDashboard {
  window: { from: string; to: string };
  totals: AiCostDashboardTotals;
  series?: Array<Record<string, unknown>>;
}

export interface OrganizationCapabilityControls {
  version: number;
  tightened: boolean;
  effective_scope: Record<string, unknown>;
  banner: Record<string, unknown>;
  capability_controls?: Record<string, unknown>;
}

/** API-024/025 AuditEventListItem (no Prompt field). */
export interface AuditEventListItem {
  id: string;
  created_at: string;
  data_classification: string;
  project_id?: string | null;
  actor_user_id?: string | null;
  delegated_agent?: string | null;
  workflow?: string | null;
  step?: string | null;
  skill_id?: string | null;
  skill_version_id?: string | null;
  model?: string | null;
  provider?: string | null;
  prompt_version?: string | null;
  tool?: string | null;
  action?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  request_hash?: string | null;
  response_hash?: string | null;
  approval_id?: string | null;
  approval_decision?: string | null;
  approval_bound_hash?: string | null;
  external_request_id?: string | null;
  result?: string | null;
  evidence_refs?: string[] | null;
  cost?: number | null;
  latency_ms?: number | null;
  payload_ref?: string | null;
}

/** API-010 organization projection fields used on P24. */
export interface OrganizationCurrentProjection {
  id: string;
  name: string;
  slug: string;
  version: number;
  is_active: boolean;
  capability_controls: Record<string, unknown>;
  siem_export_enabled?: boolean;
  created_at: string;
  updated_at: string;
}

/** API-040 SiemExportConfig response. */
export interface SiemExportConfig {
  enabled: boolean;
  version: number;
  destination_connector_id?: string | null;
  credential_present: boolean;
}

/** API-100/101 ExecutionEnvironment list/detail (no credential_ref). */
export interface ExecutionEnvironmentListItem {
  id: string;
  env_type: string;
  name: string;
  endpoint?: string | null;
  status: EnvironmentStatus;
  scope_level: string;
  credential_present: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ExecutionEnvironmentDetail extends ExecutionEnvironmentListItem {
  health_status?: Record<string, unknown> | null;
  capacity?: Record<string, unknown> | null;
  config_version: number;
}

/** API-104 JobContractListItem. */
export interface JobContractListItem {
  job_id: string;
  params_schema_ref?: string | null;
  report_adapter?: string | null;
  supports_cancel: boolean;
  contract_version: number;
  artifact_manifest?: Record<string, unknown> | null;
}

/** API-070 JobParamsSchema. */
export interface JobParamsSchema {
  environment_id: string;
  job_id: string;
  contract_version: number;
  params_schema_ref?: string | null;
  schema: Record<string, unknown>;
  supports_cancel: boolean;
}

/** API-105 EnvironmentHealthProjection. */
export interface EnvironmentHealthProjection {
  environment_id: string;
  status: EnvironmentStatus;
  health_status?: Record<string, unknown> | null;
  environment_version: number;
}

/** API-102 register response (subset). */
export interface ExecutionEnvironmentRegisterResult {
  id: string;
  env_type: string;
  name: string;
  status: EnvironmentStatus;
  version: number;
  has_credential: boolean;
  credential_present?: boolean;
  approval_request_id?: string;
}

/** API-060 TestRunListItem. */
export interface TestRunListItem {
  id: string;
  project_id: string;
  env_id: string;
  execution_source: ExecutionSource;
  trigger_type: string;
  status: TestRunStatus;
  version: number;
  plan_id?: string | null;
  gate_evaluation_id?: string | null;
  dwell_seconds?: number;
  created_at: string;
  updated_at: string;
}

/** API-061 TestRunDetail. */
export interface TestRunDetail extends TestRunListItem {
  snapshot_summary: {
    case_ids: string[];
    case_version_ids?: string[];
    env_id: string;
    env_config_version: number;
    params_redacted: Record<string, unknown>;
  };
  last_heartbeat_at?: string | null;
  stop_signal_at?: string | null;
  result_summary?: Record<string, unknown> | null;
  execution_source_badge?: {
    skips_quality_gate?: boolean;
    normalized_from_external_ci?: boolean;
  };
}

/** API-062 start response (subset). */
export interface TestRunStartResult extends TestRunDetail {
  receipt?: CommandReceipt;
}

/** API-063 cancel response. */
export interface TestRunCancelResult {
  receipt: CommandReceipt;
  test_run: TestRunDetail;
}

export const CONNECTOR_TYPES = ["jira", "github", "ci", "release"] as const;
export type ConnectorType = (typeof CONNECTOR_TYPES)[number];

/** API-160 ConnectorListItem. */
export interface ConnectorListItem {
  id: string;
  type: ConnectorType;
  name: string;
  auth_method?: string;
  credential_present: boolean;
  webhook_secret_present?: boolean;
  outbound_write_enabled: boolean;
  action_contract?: Record<string, unknown>;
  config_version?: number;
  version: number;
  created_at?: string;
  updated_at?: string;
}

/** API-161 ConnectorDetail. */
export interface ConnectorDetail extends ConnectorListItem {
  health_status?: {
    last_checked_at?: string;
    ok?: boolean;
    latency_ms?: number;
  } | null;
}

/** API-164 WebhookDeliveryItem. */
export interface WebhookDeliveryItem {
  id: string;
  connector_id: string;
  source?: string;
  observation_key?: string;
  signature_ok: boolean;
  observed_at: string;
  data_classification?: string;
  payload_ref?: string | null;
  accepted?: boolean;
}
