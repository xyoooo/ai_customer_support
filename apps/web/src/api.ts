import type {
  ApiErrorBody,
  AuthResponse,
  Membership,
  RegisterRequest,
  Workspace,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function errorMessage(body: ApiErrorBody): string {
  if (body.message) return body.message;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail) && body.detail[0]) return body.detail[0].msg;
  return "The request could not be completed.";
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(errorMessage(body), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  register: (payload: RegisterRequest) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  refresh: () => request<AuthResponse>("/auth/refresh", { method: "POST" }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  workspaces: (token: string) => request<Workspace[]>("/workspaces", {}, token),
  createWorkspace: (token: string, name: string, slug: string) =>
    request<Workspace>(
      "/workspaces",
      { method: "POST", body: JSON.stringify({ name, slug }) },
      token,
    ),
  members: (token: string, workspaceId: string) =>
    request<Membership[]>(`/workspaces/${workspaceId}/members`, {}, token),
  addMember: (token: string, workspaceId: string, email: string, role: string) =>
    request<Membership>(
      `/workspaces/${workspaceId}/members`,
      { method: "POST", body: JSON.stringify({ email, role }) },
      token,
    ),
};
