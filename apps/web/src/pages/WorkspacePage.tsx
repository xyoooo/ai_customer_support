import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";

export function WorkspacePage() {
  const { workspaceId = "" } = useParams();
  const { accessToken } = useAuth();
  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: () => api.workspaces(accessToken!), enabled: Boolean(accessToken) });
  const members = useQuery({ queryKey: ["members", workspaceId], queryFn: () => api.members(accessToken!, workspaceId), enabled: Boolean(accessToken && workspaceId) });
  const documents = useQuery({ queryKey: ["documents", workspaceId], queryFn: () => api.documents(accessToken!, workspaceId), enabled: Boolean(accessToken && workspaceId), refetchInterval: 2000 });
  const workspace = workspaces.data?.find((item) => item.id === workspaceId);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const queryClient = useQueryClient();
  const upload = useMutation({
    mutationFn: () => api.uploadDocument(accessToken!, workspaceId, file!, displayName),
    onSuccess: async () => {
      setFile(null);
      setDisplayName("");
      await queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    },
  });
  const canUpload = workspace?.role !== "viewer";
  const evidence = useMutation({
    mutationFn: () => api.searchEvidence(accessToken!, workspaceId, evidenceQuery),
  });
  function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (file) upload.mutate();
  }
  function submitEvidence(event: FormEvent) {
    event.preventDefault();
    if (evidenceQuery.trim()) evidence.mutate();
  }
  return (
    <><Link className="back-link" to="/">← All workspaces</Link><div className="page-heading"><div><p className="eyebrow">WORKSPACE</p><h1>{workspace?.name ?? "Workspace"}</h1><p className="muted">Role-aware membership view for the Week 1 foundation.</p></div>{workspace && <span className={`role ${workspace.role}`}>{workspace.role}</span>}</div>
      <section className="section-card document-section"><div className="section-heading"><div><h2>Knowledge documents</h2><p className="muted">Uploads are versioned, tenant-isolated, and processed by durable jobs.</p></div></div>
      {canUpload && <form className="upload-form" onSubmit={submitUpload}><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Defaults to filename" /></label><label>Document file<input type="file" accept=".pdf,.md,.txt,.html,.htm" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required /></label><button className="button primary" type="submit" disabled={!file || upload.isPending}>{upload.isPending ? "Uploading…" : "Upload document"}</button></form>}
      {upload.isError && <div className="alert error">{upload.error.message}</div>}
      {documents.isLoading && <p className="muted">Loading documents…</p>}{documents.isError && <div className="alert error">Unable to load documents.</div>}
      <div className="document-grid">{documents.data?.map((document) => <Link className="document-card" to={`/workspaces/${workspaceId}/documents/${document.id}`} key={document.id}><div><strong>{document.display_name}</strong><span>{document.latest_version ? `Version ${document.latest_version.version_number} · ${document.latest_version.original_filename}` : "No version"}</span></div>{document.latest_version && <span className={`job-state ${document.latest_version.status}`}>{document.latest_version.status}</span>}</Link>)}</div>
      {!documents.isLoading && documents.data?.length === 0 && <p className="empty-state">No documents yet. Upload a synthetic or public support file to begin.</p>}</section>
      <section className="section-card evidence-section"><div className="section-heading"><div><h2>Search indexed evidence</h2><p className="muted">Uses the selected C1+E1 pipeline and returns source-grounded passages.</p></div></div>
      <form className="evidence-form" onSubmit={submitEvidence}><label>Question<input value={evidenceQuery} onChange={(event) => setEvidenceQuery(event.target.value)} placeholder="Which policy applies to this request?" /></label><button className="button primary" type="submit" disabled={!evidenceQuery.trim() || evidence.isPending}>{evidence.isPending ? "Searching…" : "Search evidence"}</button></form>
      {evidence.isError && <div className="alert error">{evidence.error.message}</div>}
      {evidence.data && <div className="evidence-results">{evidence.data.results.map((result) => <article className="evidence-card" key={`${result.version_id}-${result.rank}`}><div className="evidence-meta"><strong>Result {result.rank}</strong><span>{result.heading_path.join(" › ") || "Document root"}{result.page_number ? ` · Page ${result.page_number}` : ""}</span></div><p>{result.text}</p><small>Dense rank {result.dense_rank ?? "—"} · Lexical rank {result.lexical_rank ?? "—"}</small></article>)}{evidence.data.results.length === 0 && <p className="empty-state">No active indexed evidence matched this question.</p>}</div>}</section>
      <section className="section-card"><div className="section-heading"><div><h2>Members</h2><p className="muted">Membership data is filtered by the active workspace at the database layer.</p></div></div>
      {members.isLoading && <p className="muted">Loading members…</p>}{members.isError && <div className="alert error">Unable to load members.</div>}
      <div className="member-list">{members.data?.map((member) => <article className="member-row" key={member.id}><div className="avatar">{member.display_name[0]?.toUpperCase()}</div><div className="member-main"><strong>{member.display_name}</strong><span>{member.email}</span></div><span className={`role ${member.role}`}>{member.role}</span></article>)}</div></section>
    </>
  );
}
