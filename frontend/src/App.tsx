import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { SessionGate } from "@/components/layout/SessionGate";
import { ApiError } from "@/api/errors";
import { WorkbenchPage } from "@/pages/WorkbenchPage";
import { ProjectOverviewPage } from "@/pages/ProjectOverviewPage";
import { IntegrationPage } from "@/pages/IntegrationPage";
import { ProjectSettingsPage } from "@/pages/ProjectSettingsPage";
import { TestCaseListPage } from "@/pages/TestCaseListPage";
import { TestPlanPage } from "@/pages/TestPlanPage";
import { GenerationReviewPage } from "@/pages/GenerationReviewPage";
import { ExecutionLaunchPage } from "@/pages/ExecutionLaunchPage";
import { TestRunListPage } from "@/pages/TestRunListPage";
import { TestRunDetailPage } from "@/pages/TestRunDetailPage";
import { ApprovalCenterPage } from "@/pages/ApprovalCenterPage";
import { QualityGatePolicyPage } from "@/pages/QualityGatePolicyPage";
import { GateEvalHistoryPage } from "@/pages/GateEvalHistoryPage";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { AgentTaskDetailPage } from "@/pages/AgentTaskDetailPage";
import { EnvironmentPage } from "@/pages/EnvironmentPage";
import { PerformancePage } from "@/pages/PerformancePage";
import { ReleaseTaskPage } from "@/pages/ReleaseTaskPage";
import { AssistantPage } from "@/pages/AssistantPage";
import { SkillsPage } from "@/pages/SkillsPage";
import { EvidenceCenterPage } from "@/pages/EvidenceCenterPage";
import { AiCostPage } from "@/pages/AiCostPage";
import { ModelRoutePage } from "@/pages/ModelRoutePage";
import { AiSwitchPage } from "@/pages/AiSwitchPage";
import { AuditSearchPage } from "@/pages/AuditSearchPage";
import { AdminIntegrationPage } from "@/pages/AdminIntegrationPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      retry: (count, error) => {
        if (error instanceof ApiError && (error.kind === "undeveloped" || error.kind === "permission")) {
          return false;
        }
        return error instanceof ApiError && error.retryable && count < 2;
      },
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<SessionGate />}>
            <Route element={<AppLayout />}>
            <Route index element={<WorkbenchPage />} />
            <Route path="projects" element={<ProjectOverviewPage />} />
            <Route path="projects/:projectId" element={<Navigate to="overview" replace />} />
            <Route path="projects/:projectId/overview" element={<ProjectOverviewPage />} />
            <Route path="projects/:projectId/cases" element={<TestCaseListPage />} />
            <Route path="projects/:projectId/cases/generation-review" element={<GenerationReviewPage />} />
            <Route path="projects/:projectId/cases/:caseId" element={<CaseDetailPage />} />
            <Route path="projects/:projectId/plans" element={<TestPlanPage />} />
            <Route path="projects/:projectId/runs" element={<TestRunListPage />} />
            <Route path="projects/:projectId/environments" element={<EnvironmentPage />} />
            <Route path="projects/:projectId/integrations" element={<IntegrationPage />} />
            <Route path="projects/:projectId/settings" element={<ProjectSettingsPage />} />
            <Route path="test-center/kickoff" element={<ExecutionLaunchPage />} />
            <Route path="test-center/runs" element={<TestRunListPage />} />
            <Route path="test-center/runs/:runId" element={<TestRunDetailPage />} />
            <Route path="test-center/runs/:runId/agent" element={<AgentTaskDetailPage />} />
            <Route path="test-center/performance" element={<PerformancePage />} />
            <Route path="gates" element={<Navigate to="/gates/policies" replace />} />
            <Route path="gates/policies" element={<QualityGatePolicyPage />} />
            <Route path="gates/evaluations" element={<GateEvalHistoryPage />} />
            <Route path="releases" element={<ReleaseTaskPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="approvals" element={<ApprovalCenterPage />} />
            <Route path="evidence" element={<EvidenceCenterPage />} />
            <Route path="admin/environments" element={<EnvironmentPage />} />
            <Route path="admin/ai-cost" element={<AiCostPage />} />
            <Route path="admin/model-routes" element={<ModelRoutePage />} />
            <Route path="admin/ai-switches" element={<AiSwitchPage />} />
            <Route path="admin/audit" element={<AuditSearchPage />} />
            <Route path="admin/integrations" element={<AdminIntegrationPage />} />
            <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
