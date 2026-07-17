import type {
  ApiErrorBody,
  AuthResponse,
  DocumentDetail,
  DocumentSummary,
  DocumentUpload,
  Job,
  Membership,
  RegisterRequest,
  Workspace,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

type AuthListener = (auth: AuthResponse | null) => void;

let currentAuth: AuthResponse | null = null;
let refreshPromise: Promise<AuthResponse> | null = null;
const authListeners = new Set<AuthListener>();

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

function publishAuth(auth: AuthResponse | null): void {
  currentAuth = auth;
  authListeners.forEach((listener) => listener(auth));
}

function canReplayBody(body: BodyInit | null | undefined): boolean {
  return !(typeof ReadableStream !== "undefined" && body instanceof ReadableStream);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  accessToken: string | null = currentAuth?.token.access_token ?? null,
  retryAuth = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (
    response.status === 401 &&
    accessToken &&
    retryAuth &&
    !path.startsWith("/auth/") &&
    canReplayBody(options.body)
  ) {
    const auth = await refreshSession();
    return request<T>(path, options, auth.token.access_token, false);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(errorMessage(body), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function refreshSession(): Promise<AuthResponse> {
  if (!refreshPromise) {
    refreshPromise = request<AuthResponse>("/auth/refresh", { method: "POST" }, null, false)
      .then((auth) => {
        publishAuth(auth);
        return auth;
      })
      .catch((error: unknown) => {
        publishAuth(null);
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function authenticate(path: "/auth/login" | "/auth/register", body: unknown) {
  const auth = await request<AuthResponse>(
    path,
    { method: "POST", body: JSON.stringify(body) },
    null,
    false,
  );
  publishAuth(auth);
  return auth;
}

export const api = {
  subscribeAuth: (listener: AuthListener) => {
    authListeners.add(listener);
    listener(currentAuth);
    return () => authListeners.delete(listener);
  },

  register: (payload: RegisterRequest) => authenticate("/auth/register", payload),

  login: (email: string, password: string) =>
    authenticate("/auth/login", { email, password }),

  refresh: refreshSession,
  logout: async () => {
    try {
      await request<void>("/auth/logout", { method: "POST" }, null, false);
    } finally {
      publishAuth(null);
    }
  },
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
  documents: (token: string, workspaceId: string) =>
    request<DocumentSummary[]>(`/workspaces/${workspaceId}/documents`, {}, token),
  document: (token: string, workspaceId: string, documentId: string) =>
    request<DocumentDetail>(
      `/workspaces/${workspaceId}/documents/${documentId}`,
      {},
      token,
    ),
  uploadDocument: (
    token: string,
    workspaceId: string,
    file: File,
    displayName: string,
  ) => {
    const body = new FormData();
    body.set("file", file);
    if (displayName.trim()) body.set("display_name", displayName.trim());
    return request<DocumentUpload>(
      `/workspaces/${workspaceId}/documents`,
      {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body,
      },
      token,
    );
  },
  retryJob: (token: string, workspaceId: string, jobId: string) =>
    request<Job>(
      `/workspaces/${workspaceId}/jobs/${jobId}/retry`,
      { method: "POST" },
      token,
    ),
  deleteDocument: (token: string, workspaceId: string, documentId: string) =>
    request<void>(
      `/workspaces/${workspaceId}/documents/${documentId}`,
      { method: "DELETE" },
      token,
    ),
};
