/**
 * App.jsx — The root component: defines ALL routes and the authentication gate.
 *
 * WHY THIS FILE EXISTS:
 *   React Router needs every route declared in one place. This file is the
 *   "table of contents" for the entire application — you can see every page
 *   URL and what component it renders at a glance.
 *
 * ROUTE STRUCTURE:
 *   /login           → LoginPage  (public — no login required)
 *   /register        → RegisterPage (public)
 *   /                → Layout wrapper (protected — must be logged in)
 *     index (/)      → DashboardPage  (project list — same as /projects)
 *     projects       → DashboardPage  (explicit /projects alias for sidebar NavLink)
 *     projects/:id   → ProjectPage    (pipeline hub for one project)
 *     projects/:id/requirements → RequirementsPage
 *     projects/:id/documents    → DocumentsPage
 *     projects/:id/planning     → PlanningPage
 *     projects/:id/diagrams     → DiagramsPage
 *     projects/:id/review       → ReviewPage
 *   *                → Catch-all redirect to /
 *
 * WHY IS THERE BOTH index AND "projects"?
 *   The sidebar in Layout.jsx has:
 *     NavLink to="/"         → Dashboard link
 *     NavLink to="/projects" → Projects link
 *   Both logically show the same project list page (DashboardPage).
 *   Without a <Route path="projects"> entry, the /projects URL would
 *   hit the catch-all and redirect to "/" — the NavLink would never
 *   show its "active" highlight state correctly.
 *   Adding an explicit "projects" route pointing to DashboardPage fixes this.
 *
 * WHY NEST PAGES INSIDE A LAYOUT ROUTE?
 *   All authenticated pages share the same sidebar (Layout.jsx). By making
 *   Layout the element of the "/" route, React Router renders it for every
 *   child route. The <Outlet /> inside Layout renders the active child page.
 *   Without nesting, every page would need to import and render <Layout>.
 *
 * ProtectedRoute:
 *   A wrapper that checks auth state before rendering children.
 *   Three states:
 *     loading=true  → show spinner (checking if stored token is valid)
 *     user=null     → redirect to /login (not authenticated)
 *     user!=null    → render children (authenticated, proceed normally)
 *
 * AuthProvider placement:
 *   Placed HERE wrapping everything, so auth state is available both
 *   inside ProtectedRoute AND in the Layout sidebar (user name/avatar).
 */

import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";

// ── Public pages (no login required) ─────────────────────────────────────────
import LoginPage    from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";

// ── Protected pages (login required) ─────────────────────────────────────────
import DashboardPage    from "./pages/DashboardPage";
import ProjectPage      from "./pages/ProjectPage";
import RequirementsPage from "./pages/RequirementsPage";
import DocumentsPage    from "./pages/DocumentsPage";
import PlanningPage     from "./pages/PlanningPage";
import DiagramsPage     from "./pages/DiagramsPage";
import ReviewPage       from "./pages/ReviewPage";

// ── Shared layout (sidebar + main content area) ───────────────────────────────
import Layout from "./components/Layout";

/**
 * ProtectedRoute — Guards any route that requires authentication.
 *
 * Usage:
 *   <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>} />
 *
 * If the user navigates directly to a protected URL while not logged in,
 * they are redirected to /login. The `replace` prop prevents the protected
 * page from appearing in browser history — the back button won't loop back.
 */
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  // Still checking whether the stored token is valid — show a blank loader
  // to prevent a flash of the login page before auth resolves
  if (loading) return <div className="loading-screen">Loading...</div>;

  // No authenticated user → send to login
  if (!user) return <Navigate to="/login" replace />;

  // Authenticated → render the actual page
  return children;
}

/**
 * App — Root component wiring auth, routing, and all pages together.
 */
export default function App() {
  return (
    // AuthProvider wraps everything so useAuth() works in any component
    <AuthProvider>
      <Routes>

        {/* ── Public routes — no authentication needed ─────────────────── */}
        <Route path="/login"    element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* ── Protected routes — rendered inside the sidebar Layout ──────
            Layout renders the sidebar shell. Its <Outlet /> placeholder
            renders whichever child route is currently active.
            Every nested route below automatically has the sidebar.
        ─────────────────────────────────────────────────────────────────── */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          {/* index: renders DashboardPage when the URL is exactly "/" */}
          <Route index element={<DashboardPage />} />

          {/*
            "projects" route: renders DashboardPage when the URL is "/projects".
            WHY: The sidebar NavLink to="/projects" needs a matching route or it
            hits the catch-all and redirects to "/". Both "/" and "/projects"
            show the same project list — this is intentional.
          */}
          <Route path="projects" element={<DashboardPage />} />

          {/* Individual project hub — input, analysis, generation, nav cards */}
          <Route path="projects/:projectId" element={<ProjectPage />} />

          {/* Per-project artifact pages */}
          <Route path="projects/:projectId/requirements" element={<RequirementsPage />} />
          <Route path="projects/:projectId/documents"    element={<DocumentsPage />} />
          <Route path="projects/:projectId/planning"     element={<PlanningPage />} />
          <Route path="projects/:projectId/diagrams"     element={<DiagramsPage />} />
          <Route path="projects/:projectId/review"       element={<ReviewPage />} />
        </Route>

        {/* Catch-all — any unknown URL goes to the dashboard */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </AuthProvider>
  );
}
