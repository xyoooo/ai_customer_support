import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";

export function WorkspacePage() {
  const { workspaceId = "" } = useParams();
  const { accessToken } = useAuth();
  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: () => api.workspaces(accessToken!), enabled: Boolean(accessToken) });
  const members = useQuery({ queryKey: ["members", workspaceId], queryFn: () => api.members(accessToken!, workspaceId), enabled: Boolean(accessToken && workspaceId) });
  const workspace = workspaces.data?.find((item) => item.id === workspaceId);
  return (
    <><Link className="back-link" to="/">← All workspaces</Link><div className="page-heading"><div><p className="eyebrow">WORKSPACE</p><h1>{workspace?.name ?? "Workspace"}</h1><p className="muted">Role-aware membership view for the Week 1 foundation.</p></div>{workspace && <span className={`role ${workspace.role}`}>{workspace.role}</span>}</div>
      <section className="section-card"><div className="section-heading"><div><h2>Members</h2><p className="muted">Membership data is filtered by the active workspace at the database layer.</p></div></div>
      {members.isLoading && <p className="muted">Loading members…</p>}{members.isError && <div className="alert error">Unable to load members.</div>}
      <div className="member-list">{members.data?.map((member) => <article className="member-row" key={member.id}><div className="avatar">{member.display_name[0]?.toUpperCase()}</div><div className="member-main"><strong>{member.display_name}</strong><span>{member.email}</span></div><span className={`role ${member.role}`}>{member.role}</span></article>)}</div></section>
    </>
  );
}

