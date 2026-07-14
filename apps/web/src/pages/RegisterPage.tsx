import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api";
import { useAuth } from "../auth";
import { AuthLayout } from "./LoginPage";

export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ display_name: "", email: "", password: "", workspace_name: "", workspace_slug: "" });

  if (user) return <Navigate to="/" replace />;
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setSubmitting(true);
    try { await register(form); navigate("/", { replace: true }); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Unable to create the workspace."); }
    finally { setSubmitting(false); }
  };
  return (
    <AuthLayout title="Create your workspace" subtitle="Start with an isolated workspace and an owner account.">
      <form className="auth-form two-column" onSubmit={(event) => void submit(event)}>
        <label>Display name<input required minLength={2} value={form.display_name} onChange={(e) => update("display_name", e.target.value)} /></label>
        <label>Email<input type="email" required value={form.email} onChange={(e) => update("email", e.target.value)} /></label>
        <label className="full">Password<input type="password" required minLength={12} autoComplete="new-password" value={form.password} onChange={(e) => update("password", e.target.value)} /><small>At least 12 characters</small></label>
        <label>Workspace name<input required minLength={2} value={form.workspace_name} onChange={(e) => update("workspace_name", e.target.value)} /></label>
        <label>Workspace slug<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={form.workspace_slug} onChange={(e) => update("workspace_slug", e.target.value.toLowerCase())} /></label>
        {error && <div className="alert error full" role="alert">{error}</div>}
        <button className="button primary full" disabled={submitting}>{submitting ? "Creating…" : "Create workspace"}</button>
      </form>
      <p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p>
    </AuthLayout>
  );
}

