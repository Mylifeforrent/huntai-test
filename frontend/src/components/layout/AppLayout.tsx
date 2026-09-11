import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Box,
  ClipboardCheck,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  PlayCircle,
  Search,
  Settings,
  Shield,
} from "lucide-react";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { ApiError, isUndeveloped } from "@/api/errors";
import { logoutSession } from "@/api/session";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SessionReauthNotice } from "@/components/layout/SessionReauthNotice";
import { useReauthRequired } from "@/hooks/useSession";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/uiStore";

/** 10-item IA (05 §4.1). P18 / P19 stay hidden until their milestones. */
const PRIMARY_NAV = [
  { to: "/", label: "工作台", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "项目", icon: FolderKanban },
  { to: "/test-center/runs", label: "测试中心", icon: PlayCircle },
  { to: "/gates/policies", label: "门禁", icon: Shield },
  { to: "/releases", label: "发布", icon: Box },
  { to: "/approvals", label: "审批中心", icon: ClipboardCheck, badgeKey: "approvals" as const },
  { to: "/evidence", label: "证据", icon: Search },
  { to: "/admin/ai-cost", label: "管理", icon: Settings },
] as const;

function projectLinks(projectId: string | undefined) {
  const base = projectId ? `/projects/${projectId}` : "/projects";
  return [
    { to: projectId ? `${base}/overview` : "/projects", label: "Overview", end: true },
    { to: `${base}/cases`, label: "用例" },
    { to: `${base}/plans`, label: "计划" },
    { to: `${base}/runs`, label: "执行" },
    { to: `${base}/environments`, label: "环境" },
    { to: `${base}/integrations`, label: "集成" },
    { to: `${base}/settings`, label: "设置" },
  ];
}

const TEST_CENTER_LINKS = [
  { to: "/test-center/kickoff", label: "发起执行" },
  { to: "/test-center/runs", label: "TestRun" },
  { to: "/test-center/performance", label: "性能压测" },
];

const GATE_LINKS = [
  { to: "/gates/policies", label: "策略" },
  { to: "/gates/evaluations", label: "评估历史" },
];

const ADMIN_LINKS = [
  { to: "/admin/environments", label: "环境管理" },
  { to: "/admin/ai-cost", label: "AI 成本" },
  { to: "/admin/model-routes", label: "模型路由" },
  { to: "/admin/ai-switches", label: "能力开关" },
  { to: "/admin/audit", label: "审计检索" },
  { to: "/admin/integrations", label: "集成中心" },
];

export function AppLayout() {
  const { projectId } = useParams();
  const location = useLocation();
  const queryClient = useQueryClient();
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggle = useUiStore((state) => state.toggleSidebar);
  const inProject = location.pathname.startsWith("/projects");
  const inTestCenter = location.pathname.startsWith("/test-center");
  const inGates = location.pathname.startsWith("/gates");
  const inAdmin = location.pathname.startsWith("/admin");

  const badgeQuery = useQuery({
    queryKey: queryKeys.notificationsBadge,
    queryFn: () =>
      api.get<ResourceEnvelope<{ unread_count?: number }>>("API-022", "/api/v1/notifications/badge"),
  });
  const orgQuery = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-010", "/api/v1/organizations/current"),
  });

  const unread = badgeQuery.data?.data.unread_count;
  const showCount = typeof unread === "number" && unread > 0;
  const badgeUndeveloped = isUndeveloped(badgeQuery.error);
  const banner = aiBanner(orgQuery.data?.data, orgQuery.error, orgQuery.isPending);
  const reauthRequired = useReauthRequired();

  return (
    <TooltipProvider>
      <div className="flex h-full bg-background">
        <aside
          className={cn(
            "flex h-full flex-col border-r border-sidebar-accent bg-sidebar text-sidebar-foreground transition-[width] duration-200",
            collapsed ? "w-16" : "w-56",
          )}
        >
          <div className="flex items-center gap-2 border-b border-sidebar-accent px-3 py-4">
            <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sm font-bold text-primary-foreground">
              H
            </div>
            {collapsed ? null : <span className="text-sm font-semibold text-white">HuntAI Test</span>}
          </div>
          <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
            {PRIMARY_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={"end" in item ? item.end : false}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                    collapsed && "justify-center px-0",
                    isActive
                      ? "bg-sidebar-accent font-medium text-white shadow-[inset_2px_0_0_0_var(--color-sidebar-primary)]"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-white",
                  )
                }
              >
                <item.icon className="size-4 shrink-0" />
                {collapsed ? null : <span className="flex-1">{item.label}</span>}
                {!collapsed && "badgeKey" in item ? (
                  showCount ? (
                    <Badge variant="destructive" className="border-transparent px-1.5 py-0 text-[10px]">
                      {unread}
                    </Badge>
                  ) : badgeUndeveloped ? (
                    <span className="text-[9px] text-sidebar-foreground/50">未开发</span>
                  ) : null
                ) : null}
              </NavLink>
            ))}
          </nav>
          {collapsed ? null : (
            <p className="px-3 py-3 text-[10px] leading-relaxed text-sidebar-foreground/40">
              助手 / 技能入口按里程碑隐藏
            </p>
          )}
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 items-center gap-3 border-b bg-card px-4">
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="折叠侧栏">
              <Menu className="size-4" />
            </Button>
            <div className="flex-1" />
            <div
              className={cn(
                "hidden items-center gap-2 rounded-md border px-2.5 py-1 text-xs sm:flex",
                banner.tone === "ok" && "border-success/30 bg-success-foreground text-success",
                banner.tone === "warn" && "border-warning/30 bg-warning-foreground text-warning",
                banner.tone === "pending" && "border-warning/30 bg-warning-foreground text-warning",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  banner.tone === "ok" ? "bg-success" : "bg-warning",
                )}
              />
              {banner.text}
            </div>
            <Button variant="ghost" size="icon" aria-label="通知">
              <Bell className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="退出登录"
              onClick={() => {
                void logoutSession(queryClient);
              }}
            >
              <LogOut className="size-4" />
            </Button>
          </header>
          {reauthRequired ? (
            <div className="border-b bg-card px-4 py-2">
              <SessionReauthNotice active />
            </div>
          ) : null}
          {inProject ? <Subnav links={projectLinks(projectId)} /> : null}
          {inTestCenter ? <Subnav links={TEST_CENTER_LINKS} /> : null}
          {inGates ? <Subnav links={GATE_LINKS} /> : null}
          {inAdmin ? <Subnav links={ADMIN_LINKS} /> : null}
          <main className="flex-1 overflow-y-auto p-6">
            <div className="mx-auto flex max-w-7xl flex-col gap-6">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}

function Subnav({ links }: { links: Array<{ to: string; label: string; end?: boolean }> }) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto border-b bg-card px-4">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          className={({ isActive }) =>
            cn(
              "border-b-2 px-3 py-2.5 text-xs font-medium whitespace-nowrap transition-colors",
              isActive
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )
          }
        >
          {link.label}
        </NavLink>
      ))}
    </div>
  );
}

function aiBanner(
  data: Record<string, unknown> | undefined,
  error: unknown,
  pending: boolean,
): { tone: "ok" | "warn" | "pending"; text: string } {
  if (pending) {
    return { tone: "pending", text: "加载组织信息…" };
  }
  if (error instanceof ApiError && error.kind === "permission") {
    return { tone: "warn", text: "无组织访问权限" };
  }
  if (error || !data) {
    if (isUndeveloped(error)) {
      return { tone: "pending", text: "待 API-010" };
    }
    return { tone: "pending", text: "组织信息不可用" };
  }
  const controls = asRecord(data.capability_controls);
  if (controls.ai_global_tightened === true) {
    return { tone: "warn", text: "全局 AI 已关停" };
  }
  const caps = Array.isArray(controls.tightened_capabilities) ? controls.tightened_capabilities : [];
  const mods = Array.isArray(controls.tightened_modules) ? controls.tightened_modules : [];
  if (caps.length > 0 || mods.length > 0) {
    const scope = typeof controls.banner_scope === "string" ? controls.banner_scope : "AI 降级中";
    return { tone: "warn", text: scope };
  }
  return { tone: "ok", text: "AI 正常运行中" };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
