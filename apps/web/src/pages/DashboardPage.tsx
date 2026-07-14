import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";

export function DashboardPage() {
  const { accessToken, user } = useAuth();
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.workspaces(accessToken!),
    enabled: Boolean(accessToken),
  });
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">FOUNDATION DEMO</p><h1>Good morning, {user?.display_name}</h1><p className="muted">Your workspaces are isolated by application authorization and PostgreSQL RLS.</p></div><span className="status-pill"><i />All systems ready</span></div>
      <section className="metric-grid"><article><span>Workspaces</span><strong>{workspaces.data?.length ?? "—"}</strong></article><article><span>Foundation</span><strong>Week 1</strong></article><article><span>Tenant policy</span><strong>RLS active</strong></article></section>
      <section className="section-card"><div className="section-heading"><div><h2>Workspaces</h2><p className="muted">Select a workspace to review its role and members.</p></div></div>
        {workspaces.isLoading && <p className="muted">Loading workspaces…</p>}
        {workspaces.isError && <div className="alert error">Unable to load workspaces.</div>}
        <div className="workspace-grid">{workspaces.data?.map((workspace) => <Link className="workspace-card" to={`/workspaces/${workspace.id}`} key={workspace.id}><div className="workspace-icon">{workspace.name[0]?.toUpperCase()}</div><div><h3>{workspace.name}</h3><p>{workspace.slug}</p></div><span className={`role ${workspace.role}`}>{workspace.role}</span></Link>)}</div>
      </section>
    </>
  );
}

