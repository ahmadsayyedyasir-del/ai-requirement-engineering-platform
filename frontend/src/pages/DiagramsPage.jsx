/**
 * pages/DiagramsPage.jsx — Live Mermaid.js diagram viewer with source code toggle.
 *
 * WHY THIS FILE EXISTS:
 *   Displays the 6 AI-generated technical diagrams rendered live in the browser
 *   using Mermaid.js. The user can tab between diagram types and copy the
 *   raw Mermaid source code to use in other tools.
 *
 * HOW MERMAID RENDERING WORKS:
 *   1. We configure mermaid once at module level (dark theme matching the app)
 *   2. The MermaidDiagram component receives the source_code string
 *   3. In a useEffect, it calls mermaid.render(id, code) → returns { svg }
 *   4. We inject the SVG HTML string into the div via ref.current.innerHTML
 *   The SVG is fully interactive and scales to fit the container.
 *
 * WHY useRef?
 *   mermaid.render() gives us back an SVG string, not a React component.
 *   We need direct DOM access to inject that string, which is what useRef
 *   provides. ref.current.innerHTML = svg skips React's virtual DOM for
 *   this one insertion.
 *
 * WHY UNIQUE id for each render call?
 *   mermaid.render(id, code) uses the id to create an SVG element internally.
 *   If two diagrams share the same id, the second render overwrites the first.
 *   We pass the diagram type as the id ("mermaid-er_diagram", "mermaid-sequence").
 *
 * ERROR HANDLING:
 *   If the LLM generated invalid Mermaid syntax (e.g., a missing curly brace),
 *   mermaid.render() throws. We catch it and show the raw source code in a
 *   <pre> block instead of a blank area — always useful for debugging.
 *
 * COPY BUTTON:
 *   Uses navigator.clipboard.writeText() to copy the source code.
 *   `copied` state gives a 2-second "Copied!" feedback before reverting.
 *
 * MERMAID INITIALIZATION:
 *   startOnLoad: false — we call render() manually (not on DOM ready)
 *   theme: "dark"      — Mermaid's built-in dark palette
 *   themeVariables     — overrides default dark colours to match our custom palette
 */

import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { Loader, GitBranch, Copy, Check } from "lucide-react";
import mermaid from "mermaid";

// Configure Mermaid once at module load time.
// These settings apply to ALL diagrams rendered on this page.
mermaid.initialize({
  startOnLoad: false,        // Don't auto-scan DOM — we call render() ourselves
  theme: "dark",             // Use dark base theme
  themeVariables: {
    background:         "#1a1d2e", // Matches var(--color-surface)
    mainBkg:            "#252840", // Node fill colour
    nodeBorder:         "#2e3250", // Node border colour
    clusterBkg:         "#1a1d2e", // Subgraph background
    titleColor:         "#e2e8f0", // Text colour
    edgeLabelBackground:"#252840", // Arrow label background
  },
});

// Display labels for each diagram type
const DIAGRAM_LABELS = {
  use_case:      "Use Case Diagram",
  flowchart:     "Core Process Flowchart",
  er_diagram:    "Entity Relationship Diagram",
  sequence:      "Sequence Diagram",
  class_diagram: "Class Diagram",
  architecture:  "System Architecture",
};

/**
 * MermaidDiagram — renders one Mermaid.js diagram into an SVG.
 *
 * Props:
 *   code — the Mermaid source code string (e.g., "flowchart TD\n A --> B")
 *   id   — unique string ID for this diagram (used by mermaid.render internally)
 */
function MermaidDiagram({ code, id }) {
  // ref holds direct access to the DOM div where we inject the SVG
  const ref   = useRef(null);
  const [error, setError] = useState(null);

  // Re-render whenever code or id changes (e.g., user switches diagram type)
  useEffect(() => {
    if (!ref.current || !code) return; // Don't render if no container or no code

    mermaid
      .render(`mermaid-${id}`, code) // Returns a Promise<{ svg }>
      .then(({ svg }) => {
        // Inject the SVG string directly into the div via the DOM ref
        ref.current.innerHTML = svg;
        setError(null); // Clear any previous error
      })
      .catch((e) => {
        // Mermaid syntax error — store the message to show a helpful fallback
        setError(e.message);
      });
  }, [code, id]);

  // Error state: show the raw source instead of a blank div
  if (error) {
    return (
      <div style={{ background: "var(--color-bg)", padding: 16, borderRadius: 8 }}>
        <p style={{ color: "var(--color-danger)", marginBottom: 8, fontSize: 12 }}>
          Render error: {error}
        </p>
        {/* Show raw source — helps debug what's wrong with the Mermaid syntax */}
        <pre style={{
          fontFamily: "var(--font-mono)", fontSize: 11,
          color: "var(--color-text-muted)", whiteSpace: "pre-wrap",
        }}>
          {code}
        </pre>
      </div>
    );
  }

  // Normal state: the useEffect injects the SVG into this div
  return <div ref={ref} style={{ overflow: "auto" }} />;
}

export default function DiagramsPage() {
  const { projectId } = useParams();

  // Default to "architecture" — most informative for a first look
  const [selected, setSelected] = useState("architecture");

  // copied: drives the "Copied!" feedback on the copy button
  const [copied, setCopied] = useState(false);

  // ── QUERY: fetch all generated diagrams ───────────────────────────────────
  const { data: diagrams = [], isLoading } = useQuery({
    queryKey: ["diagrams", projectId],
    queryFn: () => projectsApi.listDiagrams(projectId),
  });

  // Find the currently selected diagram object
  const currentDiagram = diagrams.find((d) => d.diagram_type === selected);

  // Copy source code to clipboard, show "Copied!" for 2s then revert
  const copy = () => {
    if (currentDiagram) {
      navigator.clipboard.writeText(currentDiagram.source_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div style={{ maxWidth: 1000 }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <div>
          <h1>Diagrams</h1>
          <p className="subtitle">{diagrams.length} diagrams generated</p>
        </div>
      </div>

      {/* ── Diagram type tabs ── */}
      {/* Horizontal scrollable tab bar — one button per diagram type */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 24 }}>
        {Object.entries(DIAGRAM_LABELS).map(([type, label]) => {
          const exists = diagrams.some((d) => d.diagram_type === type);
          return (
            <button
              key={type}
              onClick={() => setSelected(type)}
              className="btn btn-ghost btn-sm"
              style={{
                // Active tab: fill with primary colour
                ...(selected === type ? { background: "var(--color-primary)", color: "white", border: "none" } : {}),
                // Greyed out if not generated yet
                ...(exists ? {} : { opacity: 0.5 }),
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* ── Diagram content ── */}
      {isLoading ? (
        <div className="loading-state"><Loader className="spin" /></div>

      ) : currentDiagram ? (
        <div>
          {/* Content header: diagram title + copy button */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600 }}>{DIAGRAM_LABELS[selected]}</h2>
            {/* Copy Mermaid source — useful for pasting into GitHub, Notion, etc. */}
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? "Copied!" : "Copy Mermaid"}
            </button>
          </div>

          {/* Rendered diagram — Mermaid.js draws this as an SVG */}
          <div className="card" style={{ padding: 24, marginBottom: 16 }}>
            <MermaidDiagram code={currentDiagram.source_code} id={selected} />
          </div>

          {/* Collapsible raw source — useful for debugging or copying to external tools */}
          <details>
            <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--color-text-muted)", marginBottom: 8 }}>
              View Mermaid source
            </summary>
            <pre style={{
              background: "var(--color-bg)", border: "1px solid var(--color-border)",
              borderRadius: 6, padding: 16, fontSize: 12,
              fontFamily: "var(--font-mono)", color: "var(--color-text-muted)",
              overflow: "auto", whiteSpace: "pre-wrap",
            }}>
              {currentDiagram.source_code}
            </pre>
          </details>
        </div>

      ) : (
        // No diagrams generated yet
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <GitBranch size={48} color="var(--color-border)" style={{ margin: "0 auto 16px" }} />
          <p style={{ color: "var(--color-text-muted)" }}>
            No diagrams yet. Generate them from the project page.
          </p>
        </div>
      )}
    </div>
  );
}
