import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConnectorListItem,
  ListEnvelope,
  OutboundChannelsListEnvelope,
  WebhookDeliveryItem,
} from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPut = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    put: (...args: unknown[]) => apiPut(...args),
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

const outboundEmpty: OutboundChannelsListEnvelope = {
  data: { items: [], connector_version: 1 },
  page: { has_more: false, next_cursor: null },
};

const outboundWithChannel: OutboundChannelsListEnvelope = {
  data: {
    items: [
      {
        id: "ch-1",
        enabled: true,
        is_primary: true,
        channel_type: "wecom",
        endpoint_present: true,
      },
    ],
    connector_version: 2,
  },
  page: { has_more: false, next_cursor: null },
};

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiPut.mockReset();
  apiPost.mockResolvedValue({ data: { token: "ht_live_test" } });
  apiPut.mockResolvedValue(outboundWithChannel);
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
    if (apiId === "API-165") {
      return Promise.resolve(outboundEmpty);
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

  it("issue payload never has empty project_ids", async () => {
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const tokensTab = container.querySelector("[data-testid='integration-tab-tokens']");
    act(() => {
      (tokensTab as HTMLButtonElement)?.click();
    });
    await flush();
    const issueButton = container.querySelector("[data-testid='issue-api-token']");
    expect(issueButton).toBeDefined();
    const expiresInput = document.querySelector("#token-expires") as HTMLInputElement;
    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    act(() => {
      valueSetter?.call(expiresInput, "2030-01-01T12:00");
      expiresInput.dispatchEvent(new Event("input", { bubbles: true }));
      expiresInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    act(() => {
      (issueButton as HTMLButtonElement)?.click();
    });
    await flush();
    const issueCall = apiPost.mock.calls.find((call) => call[0] === "API-171");
    expect(issueCall).toBeDefined();
    const body = issueCall?.[2] as { project_ids?: string[] };
    expect(body.project_ids).toEqual(["proj-1"]);
    expect(body.project_ids?.length).toBeGreaterThan(0);
  });

  it("renders outbound endpoint_present from API-165", async () => {
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
      if (apiId === "API-165") {
        return Promise.resolve(outboundWithChannel);
      }
      return Promise.reject(new Error(`unexpected ${apiId} ${path}`));
    });
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const outboundTab = container.querySelector("[data-testid='integration-tab-outbound']");
    act(() => {
      (outboundTab as HTMLButtonElement)?.click();
    });
    await flush();
    const presentCell = container.querySelector("[data-testid='endpoint-present']");
    expect(presentCell?.textContent).toBe("true");
    expect(container.textContent).toContain("wecom");
  });

  it("PUT outbound channels without URL in body", async () => {
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const outboundTab = container.querySelector("[data-testid='integration-tab-outbound']");
    act(() => {
      (outboundTab as HTMLButtonElement)?.click();
    });
    await flush();
    const addButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("新增草稿行"),
    );
    act(() => {
      addButton?.click();
    });
    await flush();
    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    const kindInput = container.querySelector("[aria-label='kind']") as HTMLInputElement;
    const endpointInput = container.querySelector("[aria-label='endpoint_ref']") as HTMLInputElement;
    act(() => {
      valueSetter?.call(kindInput, "wecom");
      kindInput.dispatchEvent(new Event("input", { bubbles: true }));
      valueSetter?.call(endpointInput, "env:WECOM_WEBHOOK_SECRET");
      endpointInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const saveButton = container.querySelector("[data-testid='save-outbound-channels']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    act(() => {
      saveButton.click();
    });
    await flush();
    const putCall = apiPut.mock.calls.find((call) => call[0] === "API-166");
    expect(putCall).toBeDefined();
    const body = putCall?.[2] as { channels?: Array<{ endpoint_ref?: string }> };
    expect(JSON.stringify(body)).not.toContain("http");
    expect(body.channels?.[0]?.endpoint_ref).toBe("env:WECOM_WEBHOOK_SECRET");
  });

  it("does not PUT empty outbound draft and requires confirm to clear", async () => {
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const outboundTab = container.querySelector("[data-testid='integration-tab-outbound']");
    act(() => {
      (outboundTab as HTMLButtonElement)?.click();
    });
    await flush();
    expect(container.textContent).not.toContain("从服务端加载到草稿");
    const saveButton = container.querySelector("[data-testid='save-outbound-channels']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
    act(() => {
      saveButton.click();
    });
    await flush();
    expect(apiPut.mock.calls.find((call) => call[0] === "API-166")).toBeUndefined();

    const clearButton = container.querySelector("[data-testid='clear-outbound-channels']") as HTMLButtonElement;
    act(() => {
      clearButton.click();
    });
    await flush();
    expect(apiPut.mock.calls.find((call) => call[0] === "API-166")).toBeUndefined();
    expect(clearButton.textContent).toContain("确认清空渠道");
    act(() => {
      clearButton.click();
    });
    await flush();
    const putCall = apiPut.mock.calls.find((call) => call[0] === "API-166");
    expect(putCall).toBeDefined();
    const body = putCall?.[2] as { channels?: unknown[] };
    expect(body.channels).toEqual([]);
  });

  it("shows empty outbound state when API-165 items are empty", async () => {
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const outboundTab = container.querySelector("[data-testid='integration-tab-outbound']");
    act(() => {
      (outboundTab as HTMLButtonElement)?.click();
    });
    await flush();
    expect(container.textContent).toContain("无出站渠道");
  });

  it("renders last_used_at from token list", async () => {
    apiGet.mockImplementation((apiId: string, path: string) => {
      if (apiId === "API-160") {
        return Promise.resolve({
          data: { items: [connectorItem] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<ConnectorListItem>);
      }
      if (apiId === "API-170") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "token-1",
                token_prefix: "ht_live_abc",
                scopes: ["read"],
                project_ids: ["proj-1"],
                expires_at: "2030-01-01T00:00:00.000Z",
                last_used_at: "2026-09-01T12:00:00.000Z",
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-164") {
        return Promise.resolve({
          data: { items: [deliveryItem] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<WebhookDeliveryItem>);
      }
      if (apiId === "API-165") {
        return Promise.resolve(outboundEmpty);
      }
      return Promise.reject(new Error(`unexpected ${apiId} ${path}`));
    });
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const tokensTab = container.querySelector("[data-testid='integration-tab-tokens']");
    act(() => {
      (tokensTab as HTMLButtonElement)?.click();
    });
    await flush();
    expect(container.textContent).toContain("2026-09-01T12:00:00.000Z");
  });

  it("list does not show token_hash", async () => {
    apiGet.mockImplementation((apiId: string, path: string) => {
      if (apiId === "API-160") {
        return Promise.resolve({
          data: { items: [connectorItem] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<ConnectorListItem>);
      }
      if (apiId === "API-170") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "token-1",
                token_prefix: "ht_live_abc",
                scopes: ["read"],
                project_ids: ["proj-1"],
                expires_at: "2030-01-01T00:00:00.000Z",
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-164") {
        return Promise.resolve({
          data: { items: [deliveryItem] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<WebhookDeliveryItem>);
      }
      if (apiId === "API-165") {
        return Promise.resolve(outboundEmpty);
      }
      return Promise.reject(new Error(`unexpected ${apiId} ${path}`));
    });
    const container = mount(<AdminIntegrationPage />);
    await flush();
    const tokensTab = container.querySelector("[data-testid='integration-tab-tokens']");
    act(() => {
      (tokensTab as HTMLButtonElement)?.click();
    });
    await flush();
    expect(container.textContent).toContain("ht_live_abc");
    expect(container.textContent).not.toContain("token_hash");
  });
});
