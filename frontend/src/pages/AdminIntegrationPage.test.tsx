import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConnectorListItem, ListEnvelope, WebhookDeliveryItem } from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-owner", display_name: "Owner", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 2,
        is_active: true,
        capability_controls: {},
        siem_export_enabled: false,
      },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { AdminIntegrationPage } from "./AdminIntegrationPage";

const connectorItem: ConnectorListItem = {
  id: "conn-1",
  type: "github",
  name: "GitHub Org",
  credential_present: true,
  webhook_secret_present: true,
  outbound_write_enabled: false,
  version: 1,
};

const deliveryItem: WebhookDeliveryItem = {
  id: "del-1",
  connector_id: "conn-1",
  source: "webhook",
  observation_key: "delivery-abc",
  signature_ok: true,
  observed_at: "2026-09-01T12:00:00.000Z",
  payload_ref: "sha256:abc123",
  accepted: true,
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function mount(node: ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(node));
  });
  mounts.push({ root, container });
  return container;
}

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0);
      });
    });
  }
}

beforeEach(() => {
  apiGet.mockReset();
  apiGet.mockImplementation((apiId: string, path: string) => {
    if (apiId === "API-160") {
      return Promise.resolve({
        data: { items: [connectorItem] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<ConnectorListItem>);
    }
    if (apiId === "API-170") {
      return Promise.resolve({
        data: { items: [] },
        page: { has_more: false, next_cursor: null },
      });
    }
    if (apiId === "API-164") {
      return Promise.resolve({
        data: { items: [deliveryItem] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<WebhookDeliveryItem>);
    }
    return Promise.reject(new Error(`unexpected ${apiId} ${path}`));
  });
});

afterEach(() => {
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("AdminIntegrationPage", () => {
  it("renders connector list without secret fields", async () => {
    const container = mount(<AdminIntegrationPage />);
    await flush();
    expect(container.textContent).toContain("GitHub Org");
    expect(container.textContent).not.toContain("credential_ref");
    expect(container.textContent).not.toContain("webhook_secret");
    const listCall = apiGet.mock.calls.find((call) => call[0] === "API-160");
    expect(listCall).toBeDefined();
  });

  it("queries webhook deliveries via API-164", async () => {
    mount(<AdminIntegrationPage />);
    await flush();
    const deliveryCall = apiGet.mock.calls.find((call) => call[0] === "API-164");
    expect(deliveryCall).toBeDefined();
    expect(deliveryCall?.[1]).toBe("/api/v1/connectors/conn-1/webhook-deliveries");
  });
});
