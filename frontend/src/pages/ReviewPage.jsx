/**
 * pages/ReviewPage.jsx — AI Quality Review report display.
 *
 * WHY THIS FILE EXISTS:
 *   Shows the output of the AI second-pass reviewer (Phase 7):
 *     - A circular quality score gauge (0-100)
 *     - Severity counters (high / medium / low)
 *     - A list of all issues with type, severity, description, and suggestion
 *     - A collapsible full Markdown report
 *     - A "Run Review" button to trigger a new review
 *
 * KEY COMPONENTS IN THIS FILE:
 *
 *   QualityGauge — draws an SVG circle chart (arc) showing the quality score.
 *     Uses trigonometry via strokeDasharray to fill the circle proportionally:
 *       circumference = 2 × π × radius = 2 × 3.14159 × 40 ≈ 251.3px
 *       filled arc    = circumference × score / 100
 *     The circle is rotated -90deg so it starts at the top (12 o'clock).
 *     Colour: green ≥ 80, amber ≥ 60, red < 60.
 *
 * SEVERITY MAPS:
 *   SEVERITY_ICONS  — maps severity string to a coloured Lucide icon
 *   SEVERITY_STYLE  — maps severity to background/border colours for the issue card
 *   These make issue cards visually distinct at a glance.
 *
 * POLLING AFTER REVIEW:
 *   After triggering a review (useMutation), we use setTimeout 15s before
 *   invalidating the review cache. The review takes ~15-40s server-side.
 *   After invalidation, React Query re-fetches and the report appears.
 *
 * retry: false on the report query:
 *   If there's no review yet, the API returns 404. retry: false prevents
 *   React Query from retrying three times before giving up — the query just
 *   returns undefined immediately, which we handle by showing the "Run First Review" state.
 */

import React from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { FileSearch, Loader, AlertTriangle, AlertCircle, Info } from "lucide-react";
import ReactMarkdown from "react-markdown";

// Maps severity level to a colour-coded icon
const SEVERITY_ICONS = {
  high:   <AlertTriangle size={14} color="#ef4444" />, // Red triangle
  medium: <AlertCircle   size={14} color="#f59e0b" />, // Amber circle
  low:    <Info          size={14} color="#22d3ee" />, // Cyan info
};

// Maps severity to background and border colours for issue cards
const SEVERITY_STYLE = {
  high:   { background: "rgba(239,68,68,0.08)",  borderColor: "rgba(239,68,68,0.3)"  },
  medium: { background: "rgba(245,158,11,0.08)", borderColor: "rgba(245,158,11,0.3)" },
  low:    { background: "rgba(34,211,238,0.08)", borderColor: "rgba(34,211,238,0.3)" },
};

/**
 * QualityGauge — circular SVG arc chart showing the quality score.
 *
 * MATHS EXPLAINED:
 *   - SVG circle at centre (50,50) with radius 40
 *   - The circle's stroke (border) is used as the "fill"
 *   - strokeDasharray: "filledLength totalCircumference"
 *     filled = 2 * PI * 40 * (score / 100)
 *     total  = 2 * PI * 40
 *   - transform: rotate(-90deg) — starts at top instead of right (3 o'clock)
 *
 * Score colour thresholds:
 *   ≥ 80 → green (Excellent)
 *   ≥ 60 → amber (Fair)
 *   < 60 → red   (Needs Work)
 */
function QualityGauge({ score }) {
  const color = score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <div style={{ position: "relative", width: 100, height: 100 }}>
        <svg viewBox="0 0 100 100" style={{ width: "100%", transform: "rotate(-90deg)" }}>
          {/* Background track — full grey circle */}
          <circle cx="50" cy="50" r="40" fill="none" stroke="var(--color-border)" strokeWidth="10" />
          {/* Coloured arc — filled proportionally to the score */}
          <circle
            cx="50" cy="50" r="40"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray={`${2 * Math.PI * 40 * score / 100} ${2 * Math.PI * 40}`}
            strokeLinecap="round" // Rounded ends look nicer than flat ends
          />
        </svg>
        {/* Score number overlaid at centre — absolute positioned over the SVG */}
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
        }}>
          <span style={{ fontSize: 24, fontWeight: 700, color }}>{score}</span>
          <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>/100</span>
        </div>
      </div>

      {/* Text label to the right of the gauge */}
      <div>
        <div style={{ fontSize: 18, fontWeight: 700, color }}>
          {score >= 80 ? "Excellent" : score >= 60 ? "Fair" : "Needs Work"}
        </div>
        <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>Quality Score</div>
      </div>
    </div>
  );
}

export default function ReviewPage() {
  const { projectId } = useParams();
  const queryClient = useQueryClient();

  // ── QUERY: fetch the latest review report ─────────────────────────────────
  const { data: report, isLoading } = useQuery({
    queryKey: ["review", projectId],
    queryFn: () => projectsApi.getLatestReview(projectId),
    retry: false, // Don't retry 404 (no review yet) — just render the empty state
  });

  // ── MUTATION: trigger a new review ───────────────────────────────────────
  const runMutation = useMutation({
    mutationFn: () => projectsApi.runReview(projectId),
    onSuccess: () => {
      // Review takes ~15-40 seconds. Wait 15s then re-fetch to show the new report.
      setTimeout(() => queryClient.invalidateQueries(["review", projectId]), 15000);
    },
  });

  // Pre-filter issues by severity for the count badges at the top
  const highIssues   = report?.issues?.filter((i) => i.severity === "high")   || [];
  const medIssues    = report?.issues?.filter((i) => i.severity === "medium") || [];
  const lowIssues    = report?.issues?.filter((i) => i.severity === "low")    || [];

  return (
    <div style={{ maxWidth: 900 }}>
      {/* ── Page header ── */}
      <div className="page-header">
        <div>
          <h1>AI Review</h1>
          <p className="subtitle">Second-pass quality analysis of all requirements</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
        >
          {runMutation.isPending ? <Loader size={16} className="spin" /> : <FileSearch size={16} />}
          {runMutation.isPending ? "Running..." : "Run Review"}
        </button>
      </div>

      {/* ── Content ── */}
      {isLoading ? (
        <div className="loading-state"><Loader className="spin" /></div>

      ) : report ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

          {/* Quality score gauge + summary paragraph */}
          <div className="card" style={{ padding: 28 }}>
            <QualityGauge score={report.quality_score || 0} />
            {report.summary && (
              <p style={{ marginTop: 20, color: "var(--color-text-muted)", fontSize: 14, lineHeight: 1.7 }}>
                {report.summary}
              </p>
            )}
          </div>

          {/* Severity count boxes — quick summary of how many issues per level */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {[
              { label: "High",   count: highIssues.length, color: "#ef4444", bg: "rgba(239,68,68,0.08)"  },
              { label: "Medium", count: medIssues.length,  color: "#f59e0b", bg: "rgba(245,158,11,0.08)" },
              { label: "Low",    count: lowIssues.length,  color: "#22d3ee", bg: "rgba(34,211,238,0.08)" },
            ].map(({ label, count, color, bg }) => (
              <div key={label} style={{
                background: bg, border: `1px solid ${color}44`,
                borderRadius: 8, padding: "16px 20px", textAlign: "center",
              }}>
                <div style={{ fontSize: 28, fontWeight: 700, color }}>{count}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{label} Severity</div>
              </div>
            ))}
          </div>

          {/* Issues list — one card per issue */}
          {report.issues?.length > 0 && (
            <div>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Issues Found</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {report.issues.map((issue, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "14px 18px",
                      borderRadius: 8,
                      border: `1px solid ${SEVERITY_STYLE[issue.severity]?.borderColor || "var(--color-border)"}`,
                      background: SEVERITY_STYLE[issue.severity]?.background || "var(--color-surface)",
                    }}
                  >
                    {/* Issue header: icon + type label + title */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      {SEVERITY_ICONS[issue.severity]}
                      <span style={{
                        fontSize: 11, fontWeight: 600,
                        textTransform: "uppercase", letterSpacing: "0.08em",
                        color: "var(--color-text-muted)",
                      }}>
                        {issue.issue_type} {/* e.g., "MISSING", "CONFLICT" */}
                      </span>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{issue.title}</span>
                    </div>

                    {/* Issue description — what the problem is */}
                    <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 8 }}>
                      {issue.description}
                    </p>

                    {/* Suggestion — how to fix it */}
                    <p style={{ fontSize: 13, color: "var(--color-accent)" }}>
                      <strong>Suggestion:</strong> {issue.suggestion}
                    </p>

                    {/* Affected requirement IDs — clickable links to the requirement */}
                    {issue.affected_requirement_ids?.length > 0 && (
                      <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {issue.affected_requirement_ids.map((id) => (
                          <code key={id} style={{
                            fontSize: 11, background: "var(--color-surface-2)",
                            padding: "2px 6px", borderRadius: 4, color: "var(--color-accent)",
                          }}>
                            {id}
                          </code>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Full Markdown report — collapsible, for detailed reading */}
          {report.report_markdown && (
            <details>
              <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
                Full Report (Markdown)
              </summary>
              <div className="card markdown-content" style={{ padding: 28 }}>
                <ReactMarkdown>{report.report_markdown}</ReactMarkdown>
              </div>
            </details>
          )}
        </div>

      ) : (
        // No review yet — prompt the user to run their first review
        <div className="card" style={{ textAlign: "center", padding: 64 }}>
          <FileSearch size={56} color="var(--color-border)" style={{ margin: "0 auto 20px" }} />
          <h2 style={{ marginBottom: 8 }}>No Review Yet</h2>
          <p style={{ color: "var(--color-text-muted)", marginBottom: 24 }}>
            Run the AI review after generating your requirements and documents.
          </p>
          <button className="btn btn-primary" onClick={() => runMutation.mutate()}>
            <FileSearch size={16} /> Run First Review
          </button>
        </div>
      )}
    </div>
  );
}
