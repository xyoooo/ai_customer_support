import { Navigate, Outlet, RouterProvider, createBrowserRouter, useLocation } from "react-router-dom";

import { useAuth } from "./auth";
import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { WorkspacePage } from "./pages/WorkspacePage";

function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="loading-screen">Preparing your workspace…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { element: <ProtectedRoute />, children: [{ element: <AppShell />, children: [{ index: true, element: <DashboardPage /> }, { path: "workspaces/:workspaceId", element: <WorkspacePage /> }] }] },
]);

export function App() { return <RouterProvider router={router} />; }

