import type { components } from "./generated/openapi";

export type WorkspaceRole = components["schemas"]["WorkspaceRole"];
export type User = components["schemas"]["UserResponse"];
export type Token = components["schemas"]["TokenResponse"];
export type AuthResponse = components["schemas"]["AuthResponse"];
export type Workspace = components["schemas"]["WorkspaceResponse"];
export type Membership = components["schemas"]["MembershipResponse"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];

export interface ApiErrorBody {
  code?: string;
  message?: string;
  detail?: string | Array<{ msg: string }>;
}
