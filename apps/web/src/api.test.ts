import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthResponse } from "./types";

function auth(accessToken: string): AuthResponse {
  return {
    user: {
      id: "00000000-0000-0000-0000-000000000001",
      email: "owner@example.com",
      display_name: "Owner",
      created_at: "2026-07-14T00:00:00Z",
    },
    token: { access_token: accessToken, token_type: "bearer", expires_in: 900 },
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API authentication retry", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shares one refresh across concurrent 401 responses and retries with the new token", async () => {
    let refreshCalls = 0;
    const protectedTokens: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        const authorization = new Headers(init?.headers).get("Authorization");
        if (url.endsWith("/auth/login")) return json(auth("expired-token"));
        if (url.endsWith("/auth/refresh")) {
          refreshCalls += 1;
          await Promise.resolve();
          return json(auth("fresh-token"));
        }
        protectedTokens.push(authorization ?? "");
        if (authorization === "Bearer expired-token") return json({}, 401);
        if (authorization === "Bearer fresh-token") return json([]);
        return json({}, 500);
      }),
    );

    const { api } = await import("./api");
    await api.login("owner@example.com", "password");
    const observedTokens: Array<string | null> = [];
    const unsubscribe = api.subscribeAuth((value) => {
      observedTokens.push(value?.token.access_token ?? null);
    });

    await Promise.all([
      api.workspaces("expired-token"),
      api.members("expired-token", "00000000-0000-0000-0000-000000000002"),
    ]);

    unsubscribe();
    expect(refreshCalls).toBe(1);
    expect(protectedTokens.filter((token) => token === "Bearer expired-token")).toHaveLength(2);
    expect(protectedTokens.filter((token) => token === "Bearer fresh-token")).toHaveLength(2);
    expect(observedTokens).toEqual(["expired-token", "fresh-token"]);
  });

  it("retries a protected request only once", async () => {
    let refreshCalls = 0;
    let protectedCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/login")) return json(auth("expired-token"));
        if (url.endsWith("/auth/refresh")) {
          refreshCalls += 1;
          return json(auth("fresh-token"));
        }
        protectedCalls += 1;
        return json({ message: "authentication required" }, 401);
      }),
    );

    const { api } = await import("./api");
    await api.login("owner@example.com", "password");

    await expect(api.workspaces("expired-token")).rejects.toEqual(
      expect.objectContaining({ status: 401 }),
    );
    expect(refreshCalls).toBe(1);
    expect(protectedCalls).toBe(2);
  });

  it("clears subscribed auth state when refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/login")) return json(auth("expired-token"));
        if (url.endsWith("/auth/refresh")) {
          return json({ message: "session is invalid or expired" }, 401);
        }
        return json({}, 401);
      }),
    );

    const { api } = await import("./api");
    await api.login("owner@example.com", "password");
    const observedTokens: Array<string | null> = [];
    const unsubscribe = api.subscribeAuth((value) => {
      observedTokens.push(value?.token.access_token ?? null);
    });

    await expect(api.workspaces("expired-token")).rejects.toBeTruthy();

    unsubscribe();
    expect(observedTokens).toEqual(["expired-token", null]);
  });
});
