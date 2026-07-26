/**
 * pages/RequirementsPage.jsx — Displays all AI-extracted requirements with filtering.
 *
 * WHY THIS FILE EXISTS:
 *   After the AI analysis pipeline completes, the structured requirements are
 *   stored in PostgreSQL. This page fetches and displays them grouped by category,
 *   with colour-coded MoSCoW priority badges.
 *   It also provides the "MoSCoW AI" button (bonus feature) that triggers
 *   AI-driven re-prioritization of all requirements.
 *
 * KEY PATTERNS:
 *
 *   GROUPING: The `grouped` variable uses Array.reduce() to transform the flat
 *   requirements array into a dict keyed by category:
 *     { "functional": [...], "non_functional": [...], "risk": [...] }
 *   Object.entries(grouped).map() then renders one section per category.
 *
 *   CATEGORY FILTER: The filter state changes which category is passed to
 *   listRequirements(). React Query uses the filter in the queryKey so
 *   each category gets its own cache entry — switching tabs is instant
 *   if the data is already cached.
 *
 *   PRIORITY_BADGE: Maps priority strings to CSS class names defined in index.css.
 *   badge-must (red), badge-should (amber), badge-could (blue), badge-wont (grey).
 *
 *   MOSCOW AI BUTTON: Calls projectsApi.moscowPrioritize() which sends all
 *   requirements to GPT-4o for MoSCoW re-evaluation. On success, invalidates
 *   the requirements cache so the updated priorities are shown immediately.
 */

import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { Brain, Loader, Wand2 } from "lucide-react";

// All 8 requirement categories + "" for "All"
const CATEGORIES = [
  "", "functional", "non_functional", "user_role",
  "business_rule", "constraint", "assumption", "risk", "dependency",
];

// Maps priority value to CSS badge class (defined in index.css)
const PRIORITY_BADGE = {
  must_have:   "badge-must",
  should_have: "badge-should",
  could_have:  "badge-could",
  wont_have:   "badge-wont",
};

export default function RequirementsPage() {
  const { projectId } = useParams();
  const queryClient = useQueryClient();

  // Active category filter — "" means "All categories"
  const [filter, setFilter] = useState("");

  // Message shown in the banner after MoSCoW AI completes
  const [moscowMsg, setMoscowMsg] = useState("");

  // ── QUERY: fetch requirements (re-fetches when `filter` changes) ─────────
  const { data: requirements = [], isLoading } = useQuery({
    queryKey: ["requirements", projectId, filter],  // filter is part of the key
    queryFn: () => projectsApi.listRequirements(projectId, filter || null),
    // filter || null: pass null when filter is "" (API returns all categories)
  });

  // ── MUTATION: MoSCoW AI re-prioritization ─────────────────────────────────
  const moscowMutation = useMutation({
    mutationFn: () => projectsApi.moscowPrioritize(projectId),
    onSuccess: (data) => {
      // Invalidate ALL requirement cache entries for this project (all filters)
      queryClient.invalidateQueries(["requirements", projectId]);
      setMoscowMsg(`MoSCoW complete: ${data.changes?.length || 0} requirements re-prioritized.`);
    },
  });

  // Group the flat array by category for section rendering
  const grouped = requirements.reduce((acc, req) => {
    if (!acc[req.category]) acc[req.category] = [];
    acc[req.category].push(req);
    return acc;
  }, {});

  return (
    <div style={{ maxWidth: 900 }}>

      {/* ── Page header ── */}
      <div className="page-header">
        <div>
          <h1>Requirements</h1>
          <p className="subtitle">{requirements.length} requirements extracted</p>
        </div>
        {/* MoSCoW AI button — bonus feature, re-evaluates all priorities */}
        <button
          className="btn btn-ghost"
          onClick={() => moscowMutation.mutate()}
          disabled={moscowMutation.isPending}
          title="AI-powered MoSCoW re-prioritization — re-evaluates all requirement priorities"
        >
          {moscowMutation.isPending
            ? <Loader size={14} className="spin" />
            : <Wand2 size={14} />
          }
          MoSCoW AI
        </button>
      </div>

      {/* Success banner after MoSCoW AI completes */}
      {moscowMsg && (
        <div className="action-banner" style={{ marginBottom: 16 }}>
          <Brain size={16} />
          {moscowMsg}
          <button onClick={() => setMoscowMsg("")}>×</button>
        </div>
      )}

      {/* ── Category filter tabs ── */}
      {/* Each button filters the requirements list. Active button gets primary colour. */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            className="btn btn-ghost btn-sm"
            style={{
              textTransform: "capitalize",
              // Active state: override with primary colour
              ...(filter === cat
                ? { background: "var(--color-primary)", color: "white", border: "none" }
                : {}),
            }}
            onClick={() => setFilter(cat)}
          >
            {cat || "All"}
          </button>
        ))}
      </div>

      {/* ── Content ── */}
      {isLoading ? (
        <div className="loading-state"><Loader className="spin" /></div>

      ) : requirements.length === 0 ? (
        <div className="empty-state">
          <Brain size={48} color="var(--color-border)" />
          <p>No requirements found. Go back and run the AI analysis first.</p>
        </div>

      ) : (
        // Render one section per category (e.g., "FUNCTIONAL (12)", "RISK (4)")
        Object.entries(grouped).map(([category, reqs]) => (
          <div key={category} style={{ marginBottom: 32 }}>

            {/* Category section heading */}
            <h2 style={{
              fontSize: 14,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              color: "var(--color-text-muted)",
              marginBottom: 12,
            }}>
              {category.replace(/_/g, " ")} ({reqs.length})
              {/* replace underscore with space: "non_functional" → "non functional" */}
            </h2>

            {/* Requirement cards */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {reqs.map((req) => (
                <div key={req.id} className="card" style={{ padding: 18 }}>

                  {/* Header: req_id (code style) + priority badge */}
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    {/* req_id in monospace — "FR-001", "NFR-003" etc. */}
                    <code style={{
                      fontSize: 12,
                      color: "var(--color-accent)",
                      fontFamily: "var(--font-mono)",
                    }}>
                      {req.req_id}
                    </code>

                    {/* MoSCoW priority badge — colour-coded via CSS class */}
                    <span className={`badge ${PRIORITY_BADGE[req.priority] || ""}`}>
                      {req.priority?.replace(/_/g, " ")} {/* "must_have" → "must have" */}
                    </span>
                  </div>

                  {/* Requirement title */}
                  <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
                    {req.title}
                  </h3>

                  {/* Full description */}
                  <p style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                    {req.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
