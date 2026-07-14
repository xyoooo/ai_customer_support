import { Link, Outlet } from "react-router-dom";

import { useAuth } from "../auth";

export function AppShell() {
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand" aria-label="SupportPilot home">
          <span className="brand-mark">S</span>
          <span>SupportPilot</span>
        </Link>
        <div className="user-menu">
          <span>{user?.display_name}</span>
          <button className="button ghost" type="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      <main className="page"><Outlet /></main>
    </div>
  );
}

