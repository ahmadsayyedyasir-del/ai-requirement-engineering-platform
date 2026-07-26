/**
 * components/Layout.jsx — The persistent sidebar shell for all authenticated pages.
 *
 * WHY THIS FILE EXISTS:
 *   Every page an authenticated user sees has the same left sidebar showing:
 *   - The app logo
 *   - Navigation links (Dashboard, Projects)
 *   - The logged-in user's name, role, and logout button
 *
 *   Rather than importing and rendering a sidebar inside every page component,
 *   React Router lets us define a "layout route" — a component that renders
 *   the shared chrome ONCE, with an <Outlet /> placeholder where the active
 *   page renders.
 *
 * HOW <Outlet /> WORKS:
 *   When the URL is /projects/abc123, React Router:
 *     1. Renders Layout (which draws the sidebar)
 *     2. Renders ProjectPage inside <Outlet /> (the main content area)
 *   The sidebar stays mounted and static; only the <Outlet /> changes per URL.
 *
 * KEY IMPORTS EXPLAINED:
 *   Outlet     — React Router placeholder for the active child route
 *   NavLink    — Like <Link> but adds an "active" class when the URL matches.
 *                We use this to highlight the current nav item.
 *   useNavigate — Programmatic navigation (used for logout redirect)
 *   useAuth    — Our custom hook to get the logged-in user and logout function
 *   lucide-react — Icon library (tree-shakeable SVG icons)
 */

import React from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LayoutDashboard, FolderOpen, LogOut, Brain } from "lucide-react";
import "./Layout.css";

export default function Layout() {
  // Get the current user (for displaying name/role) and the logout function
  const { user, logout } = useAuth();

  // useNavigate gives us a function to programmatically change the URL
  const navigate = useNavigate();

  // Logout: clear auth state then redirect to /login
  const handleLogout = () => {
    logout();           // Clears token from localStorage and user from state
    navigate("/login"); // Redirect to login page
  };

  return (
    <div className="layout">
      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      {/*
        Fixed sidebar — stays in place while the page content scrolls.
        Width is 240px (defined in Layout.css), which is the standard width
        for secondary navigation sidebars.
      */}
      <aside className="sidebar">

        {/* Brand logo and app name */}
        <div className="sidebar-logo">
          {/* Brain icon = AI-themed logo mark */}
          <Brain size={28} color="var(--color-primary)" />
          <span>ReqAI</span>
        </div>

        {/* Navigation links */}
        <nav className="sidebar-nav">
          {/*
            NavLink automatically applies the "active" className when the
            current URL matches its `to` prop.
            The `end` prop on the Dashboard link means it only activates
            for EXACTLY "/" — without it, "/" would also match "/projects/..."
          */}
          <NavLink
            to="/"
            end  /* Only active when URL is exactly "/" */
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <LayoutDashboard size={18} />
            Dashboard
          </NavLink>

          {/*
            Note: "Projects" navigates to "/" because the dashboard IS the
            project list. In a larger app you'd have /projects as a separate list.
          */}
          <NavLink
            to="/projects"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <FolderOpen size={18} />
            Projects
          </NavLink>
        </nav>

        {/* User info and logout — pinned to the bottom of the sidebar */}
        <div className="sidebar-footer">
          <div className="user-info">
            {/*
              Avatar — shows the first letter of the user's name as a coloured
              circle. A simple alternative to profile photos that always works.
              user?.full_name?.[0] uses optional chaining (?.) to safely access
              the first character — prevents crashes if user is null during loading.
              toUpperCase() ensures the avatar letter is always a capital.
            */}
            <div className="avatar">
              {user?.full_name?.[0]?.toUpperCase()}
            </div>
            <div>
              <div className="user-name">{user?.full_name}</div>
              <div className="user-role">{user?.role}</div>
            </div>
          </div>

          {/* Logout button */}
          <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
            <LogOut size={14} />
            Logout
          </button>
        </div>
      </aside>

      {/* ── Main content area ─────────────────────────────────────────────── */}
      {/*
        margin-left: 240px — pushes the content right so it doesn't overlap
        the fixed sidebar. This value must match the sidebar width in Layout.css.

        <Outlet /> is the React Router magic — it renders whichever child route
        is currently active. For /projects/abc123, it renders <ProjectPage />.
        For /, it renders <DashboardPage />. The sidebar stays untouched.
      */}
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
