import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";

export function DocumentPage() {
  const { workspaceId = "", documentId = "" } = useParams();
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.workspaces(accessToken!),
    enabled: Boolean(accessToken),
  });
  const document = useQuery({
    queryKey: ["document", workspaceId, documentId],
    queryFn: () => api.document(accessToken!, workspaceId, documentId),
    enabled: Boolean(accessToken && workspaceId && documentId),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) =>
        ["queued", "leased", "processing", "retrying"].includes(job.state),
      )
        ? 1500
        : false,
  });
  const role = workspaces.data?.find((workspace) => workspace.id === workspaceId)?.role;
  const canContribute = role !== "viewer";
  const canManage = role === "owner" || role === "admin";
  const retry = useMutation({
    mutationFn: (jobId: string) => api.retryJob(accessToken!, workspaceId, jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", workspaceId] }),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteDocument(accessToken!, workspaceId, documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
      await navigate(`/workspaces/${workspaceId}`);
    },
  });

  return (
    <>
      <Link className="back-link" to={`/workspaces/${workspaceId}`}>
        ← Workspace documents
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DOCUMENT LIFECYCLE</p>
          <h1>{document.data?.display_name ?? "Document"}</h1>
          <p className="muted">Immutable versions and durable processing history.</p>
        </div>
        {document.data?.latest_version && (
          <span className={`job-state ${document.data.latest_version.status}`}>
            {document.data.latest_version.status}
          </span>
        )}
      </div>
      {document.isLoading && <p className="muted">Loading document…</p>}
      {document.isError && <div className="alert error">Unable to load this document.</div>}
      {document.data && (
        <div className="document-layout">
          <section className="section-card">
            <div className="section-heading">
              <div>
                <h2>Versions</h2>
                <p className="muted">Content metadata cannot be changed after upload.</p>
              </div>
            </div>
            <div className="record-list">
              {document.data.versions.map((version) => (
                <article className="record-row" key={version.id}>
                  <div>
                    <strong>Version {version.version_number}</strong>
                    <span>{version.original_filename}</span>
                  </div>
                  <div className="record-meta">
                    <span>{Math.ceil(version.byte_size / 1024)} KB</span>
                    <span className={`job-state ${version.status}`}>{version.status}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <section className="section-card">
            <div className="section-heading">
              <div>
                <h2>Processing jobs</h2>
                <p className="muted">Lease, retry, and failure state are durable.</p>
              </div>
            </div>
            <div className="record-list">
              {document.data.jobs.map((job) => (
                <article className="record-row" key={job.id}>
                  <div>
                    <strong>{job.job_type.replaceAll("_", " ")}</strong>
                    <span>
                      Attempt {job.attempt_count} of {job.max_attempts}
                    </span>
                    {job.error_message && <span className="error-text">{job.error_message}</span>}
                  </div>
                  <div className="record-meta">
                    <span className={`job-state ${job.state}`}>{job.state.replaceAll("_", " ")}</span>
                    {canContribute && ["failed", "dead_letter"].includes(job.state) && (
                      <button
                        className="button ghost"
                        type="button"
                        disabled={retry.isPending}
                        onClick={() => retry.mutate(job.id)}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
          {canManage && (
            <section className="danger-card">
              <div>
                <strong>Delete document</strong>
                <p>Hide the document now and queue physical object cleanup.</p>
              </div>
              <button
                className="button danger"
                type="button"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                Delete
              </button>
            </section>
          )}
        </div>
      )}
    </>
  );
}
