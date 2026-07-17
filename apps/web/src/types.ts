import type { components } from "./generated/openapi";

export type WorkspaceRole = components["schemas"]["WorkspaceRole"];
export type User = components["schemas"]["UserResponse"];
export type Token = components["schemas"]["TokenResponse"];
export type AuthResponse = components["schemas"]["AuthResponse"];
export type Workspace = components["schemas"]["WorkspaceResponse"];
export type Membership = components["schemas"]["MembershipResponse"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];
export type DocumentVersion = components["schemas"]["DocumentVersionResponse"];
export type DocumentSummary = components["schemas"]["DocumentResponse"];
export type DocumentDetail = components["schemas"]["DocumentDetailResponse"];
export type DocumentUpload = components["schemas"]["DocumentUploadResponse"];
export type Job = components["schemas"]["JobResponse"];

export interface ApiErrorBody {
  code?: string;
  message?: string;
  detail?: string | Array<{ msg: string }>;
}
