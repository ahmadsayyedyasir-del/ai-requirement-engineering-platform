/**
 * pages/PlanningPage.jsx — AI-generated software planning artifacts viewer.
 *
 * WHY THIS FILE EXISTS:
 *   Shows the 8 planning artifacts (roadmap, sprints, cost, team, etc.) in the
 *   same sidebar + content pattern as DocumentsPage.
 *
 *   The planning generator creates all 8 artifacts from the extracted requirements.
 *   This page fetches the list once and lets the user browse each artifact.
 *
 * SAME PATTERN AS DOCUMENTS PAGE:
 *   - Sidebar of artifact types (left)
 *   - Rendered markdown content (right)
 *   - Green dot when an artifact exists
 *   - .find() to pick the selected artifact from the list
 *
 * WHY USE summary_markdown INSTEAD OF content?
 *   content is the raw structured JSON (e.g., {"phases": [...], "costs": [...]}).
 *   summary_markdown is a pre-rendered Markdown representation of that JSON.
 *   The markdown is already formatted for display (headers, tables, bullet points),
 *   so we don't need to write custom rendering code for each artifact type.
 *   The JSON is still available via content for programmatic use (e.g., charts).
 *
 * FALLBACK:
 *   summary_markdown || JSON.stringify(content, null, 2)
 *   If markdown rendering failed during generation, we display the raw JSON.
 *   This is an edge case but prevents a blank screen.
 */

import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { BarChart2, Loader } from "lucide-react";
import ReactMarkdown from "react-markdown";

// Planning types in the order they appear in the sidebar
const PLANNING_TYPES = [
  "module_breakdown", "roadmap", "sprints",
  "team_composition", "tech_stack", "timeline",
  "cost_estimation", "risk_assessment",
];

// Human-readable labels for the sidebar buttons and page title
const PLANNING_LABELS = {
  module_breakdown:  "Module Breakdown",
  roadmap:           "Development Roadmap",
  sprints:           "Sprint Plan",
  team_composition:  "Team Composition",
  tech_stack:        "Technology Stack",
  timeline:          "Project Timeline",
  cost_estimation:   "Cost Estimation",
  risk_assessment:   "Risk Assessment",
};

export default function PlanningPage() {
  const { projectId } = useParams();

  // Selected planning type — "roadmap" is a good default as it's the most overview-ish
  const [selected, setSelected] = useState("roadmap");

  // ── QUERY: fetch all generated planning artifacts ─────────────────────────
  const { data: artifacts = [], isLoading } = useQuery({
    queryKey: ["planning", projectId],
    queryFn: () => projectsApi.listPlanning(projectId),
  });

  // The currently selected artifact (or undefined if not yet generated)
  const current = artifacts.find((a) => a.planning_type === selected);

  // Set of types that have been generated — for the green dot indicator
  const generatedTypes = new Set(artifacts.map((a) => a.planning_type));

  return (
    <div style={{ maxWidth: 1000, display: "flex", gap: 24 }}>

      {/* ── LEFT SIDEBAR ── */}
      <div style={{ width: 200, flexShrink: 0 }}>
        <h3 style={{
          fontSize: 11, textTransform: "uppercase",
          letterSpacing: "0.08em", color: "var(--color-text-muted)", marginBottom: 12,
        }}>
          Planning
        </h3>

        {PLANNING_TYPES.map((type) => {
          const isGenerated = generatedTypes.has(type);
          const isSelected  = selected === type;

          return (
            <button
              key={type}
              onClick={() => setSelected(type)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "9px 12px",
                borderRadius: 6,
                background: isSelected ? "var(--color-primary)" : "transparent",
                border: "none",
                color: isSelected ? "white" : isGenerated ? "var(--color-text)" : "var(--color-text-muted)",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                textAlign: "left",
                marginBottom: 2,
              }}
            >
              <span style={{ flex: 1 }}>{PLANNING_LABELS[type]}</span>
              {/* Green dot when artifact exists */}
              {isGenerated && (
                <span style={{
                  width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                  background: isSelected ? "rgba(255,255,255,0.6)" : "var(--color-success)",
                }} />
              )}
            </button>
          );
        })}
      </div>

      {/* ── RIGHT CONTENT ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Page title for the selected artifact */}
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>
          {PLANNING_LABELS[selected]}
        </h2>

        {isLoading ? (
          // Loading spinner while fetching all artifacts on first load
          <div className="loading-state"><Loader className="spin" /></div>

        ) : current ? (
          // Render the planning artifact as formatted markdown
          <div className="card markdown-content" style={{ padding: 28 }}>
            <ReactMarkdown>
              {current.summary_markdown || JSON.stringify(current.content, null, 2)}
            </ReactMarkdown>
          </div>

        ) : (
          // Not yet generated — show guidance
          <div className="card" style={{ textAlign: "center", padding: 48 }}>
            <BarChart2 size={48} color="var(--color-border)" style={{ margin: "0 auto 16px" }} />
            <p style={{ color: "var(--color-text-muted)" }}>
              Planning not generated yet. Go to the project page and click "Generate Everything".
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
