/**
 * pages/DashboardPage.jsx — The project list (home screen after login).
 *
 * WHY THIS FILE EXISTS:
 *   After login the user lands here. They see all their projects as cards,
 *   can create a new project, open existing ones, or delete them.
 *
 * KEY REACT QUERY CONCEPTS USED:
 *
 *   useQuery — Fetches data and manages loading/error/data states automatically.
 *     queryKey: ["projects"]   → cache key. Invalidating this key re-fetches.
 *     queryFn: projectsApi.list → the function that calls the API.
 *     data defaults to []     → avoids undefined checks before the fetch completes.
 *
 *   useMutation — For write operations (create, delete).
 *     mutationFn: the API call to make.
 *     onSuccess: callback after the mutation succeeds.
 *     queryClient.invalidateQueries(["projects"]) tells React Query to discard
 *     the cached project list and re-fetch it — so the new/deleted project
 *     appears/disappears from the UI immediately.
 *
 * MODAL PATTERN:
 *   showCreate: boolean controls whether the modal is visible.
 *   Clicking the overlay (modal-overlay div) closes the modal by setting showCreate false.
 *   e.stopPropagation() on the modal card prevents clicks inside from
 *   bubbling up to the overlay and accidentally closing the modal.
 *
 * STATUS_COLORS:
 *   Maps project status strings to hex colours for the status pill.
 *   Applied as inline styles with opacity variants (hex + "22" = 13% opacity background,
 *   hex + "44" = 26% opacity border — a subtle "tinted" look without a solid colour).
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { Plus, FolderOpen, Loader, Trash2, ArrowRight, Brain } from "lucide-react";
import "./DashboardPage.css";

// Colour per project status — maps to the project lifecycle
const STATUS_COLORS = {
  draft:      "#94a3b8", // Grey     — just created, no input yet
  analyzing:  "#f59e0b", // Amber    — AI pipeline running
  analyzed:   "#22d3ee", // Cyan     — requirements extracted
  generating: "#a78bfa", // Purple   — docs/diagrams being generated
  completed:  "#22c55e", // Green    — everything done
  archived:   "#64748b", // Dim grey — no longer active
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Controls visibility of the "New Project" modal
  const [showCreate, setShowCreate] = useState(false);

  // Controlled form state for the new project modal
  const [form, setForm] = useState({ name: "", description: "", domain: "" });

  // ── DATA FETCHING ────────────────────────────────────────────────────────
  // Fetch all projects. React Query automatically shows loading state and
  // caches the result. Default [] prevents undefined errors before fetch completes.
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  // ── MUTATIONS ─────────────────────────────────────────────────────────────

  // Create project mutation — POST /projects/
  const createMutation = useMutation({
    mutationFn: projectsApi.create,
    onSuccess: (project) => {
      queryClient.invalidateQueries(["projects"]); // Re-fetch project list
      setShowCreate(false);                         // Close modal
      setForm({ name: "", description: "", domain: "" }); // Reset form
      navigate(`/projects/${project.id}`);          // Go to the new project
    },
  });

  // Delete project mutation — DELETE /projects/{id}
  const deleteMutation = useMutation({
    mutationFn: projectsApi.delete,
    onSuccess: () => queryClient.invalidateQueries(["projects"]), // Re-fetch list
  });

  return (
    <div className="dashboard">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1>Projects</h1>
          <p className="subtitle">Manage your requirement engineering projects</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={16} />
          New Project
        </button>
      </div>

      {/* ── Create Project Modal ─────────────────────────────────────────── */}
      {showCreate && (
        // Clicking the dark overlay closes the modal
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          {/* stopPropagation prevents clicks inside the modal from closing it */}
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>New Project</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate(form);
              }}
            >
              {/* Project name — required */}
              <div className="form-group">
                <label>Project Name *</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. E-Commerce Platform"
                  required
                />
              </div>

              {/* Description — optional context for the AI */}
              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Brief overview of the project..."
                  rows={3}
                />
              </div>

              {/* Domain — helps the AI tailor its analysis (fintech vs healthcare etc.) */}
              <div className="form-group">
                <label>Domain</label>
                <select
                  value={form.domain}
                  onChange={(e) => setForm({ ...form, domain: e.target.value })}
                >
                  <option value="">Select domain...</option>
                  <option value="fintech">Fintech</option>
                  <option value="healthcare">Healthcare</option>
                  <option value="ecommerce">E-Commerce</option>
                  <option value="edtech">EdTech</option>
                  <option value="saas">SaaS</option>
                  <option value="logistics">Logistics</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  {createMutation.isPending ? <Loader size={14} className="spin" /> : <Plus size={14} />}
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Project Grid ────────────────────────────────────────────────── */}
      {isLoading ? (
        // Loading state — shown while the first fetch is in progress
        <div className="loading-state">
          <Loader size={32} className="spin" />
          <p>Loading projects...</p>
        </div>

      ) : projects.length === 0 ? (
        // Empty state — shown when the user has no projects yet
        <div className="empty-state">
          <Brain size={64} color="var(--color-border)" />
          <h2>No projects yet</h2>
          <p>Create your first project to start automating requirement engineering.</p>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={16} /> Create Project
          </button>
        </div>

      ) : (
        // Project cards grid
        <div className="projects-grid">
          {projects.map((project) => (
            <div key={project.id} className="project-card card">

              {/* Card header: status pill + delete button */}
              <div className="project-card-header">
                {/*
                  Status pill: background is the status colour at 13% opacity (hex+"22"),
                  border is 26% opacity (hex+"44"), text is full colour.
                  This creates a subtle "tinted" style consistent with the dark theme.
                */}
                <div
                  className="project-status"
                  style={{
                    background: STATUS_COLORS[project.status] + "22",
                    color: STATUS_COLORS[project.status],
                    border: `1px solid ${STATUS_COLORS[project.status]}44`,
                  }}
                >
                  {project.status}
                </div>

                {/* Delete button — confirm dialog prevents accidental deletion */}
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    if (confirm("Delete this project? This cannot be undone.")) {
                      deleteMutation.mutate(project.id);
                    }
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Card body: project name, description, domain tag */}
              <div className="project-card-body">
                <h3>{project.name}</h3>
                <p>{project.description || "No description"}</p>
                {project.domain && <span className="tag">{project.domain}</span>}
              </div>

              {/* Card footer: creation date + open button */}
              <div className="project-card-footer">
                <span className="project-date">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => navigate(`/projects/${project.id}`)}
                >
                  Open <ArrowRight size={14} />
                </button>
              </div>

            </div>
          ))}
        </div>
      )}
    </div>
  );
}
