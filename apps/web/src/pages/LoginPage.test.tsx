import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth";
import { LoginPage } from "./LoginPage";

vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));

describe("LoginPage", () => {
  it("renders accessible credentials fields", async () => {
    const router = createMemoryRouter([{ path: "/login", element: <LoginPage /> }], { initialEntries: ["/login"] });
    render(<QueryClientProvider client={new QueryClient()}><AuthProvider><RouterProvider router={router} /></AuthProvider></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });
});

