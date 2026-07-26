/**
 * pages/DocumentsPage.jsx — Split-panel document viewer with regeneration.
 *
 * WHY THIS FILE EXISTS:
 *   Shows the 8 AI-generated documents in a sidebar + content-area layout.
 *   The user clicks a document type in the sidebar to view its latest content.
 *   Each document is rendered using react-markdown, which converts the markdown
 *   string from the API into formatted HTML (headings, tables, bold, etc.).
 *
 * LAYOUT PATTERN — Sidebar + Content:
 *   A two-column flex layout where:
 *     - Left sidebar (220px): list of all 8 document types
 *     - Right content (flex: 1): the currently selected document
 *   This is the same pattern used by VS Code, Notion, and most IDEs.
 *
 * GENERATED STATUS INDICATOR:
 *   generatedTypes is a Set of doc_type strings built from the documents array.
 *   If a type is in the Set, a green dot (●) appears next to its name in the
 *   sidebar, giving a quick visual of which documents exist.
 *
 * REACT QUERY CACHING:
 *   The document list (listDocuments) is fetched once and cached.
 *   The selected document content (getDocument) uses queryKey ["document", projectId, selected]
 *   so each document type has its own cache entry. Switching between documents
 *   is instant if they've been viewed before.
 *   enabled: !!selected prevents fetching when no type is selected.
 *   retry: false prevents showing an error for documents that don't exist yet.
 *
 * REGENERATE BUTTON:
 *   setTimeout 8000ms after triggering regeneration before invalidating cache.
 *   This is because the API returns 202 immediately but generation takes ~5-15s.
 *   After 8s we invalidate to re-fetch — the new version should be ready.
 *   (In production you'd use WebSockets or polling instead.)
 *
 * CONTENT FALLBACK:
 *   currentDoc.content_markdown || JSON.stringify(currentDoc.content_json, null, 2)
 *   Prefers the rendered markdown for display, falls back to raw JSON if markdown
 *   wasn't generated (rare edge case).
 */

import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import { FileText, Loader, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown"; // Renders markdown strings as HTML

// All 8 document types in the order they appear in the sidebar
const DOC_TYPES = [
  "srs", "brd", "user_stories", "use_cases",
  "acceptance_criteria", "glossary", "functional_spec", "non_functional_spec",
];

// Human-readable labels for each document type
const DOC_LABELS = {
  srs:                  "Software Requirements Specification",
  brd:                  "Business Requirements Document",
  user_stories:         "User Stories",
  use_cases:            "Use Cases",
  acceptance_criteria:  "Acceptance Criteria",
  glossary:             "Glossary",
  functional_spec:      "Functional Specification",
  non_functional_spec:  "Non-Functional Specification",
};

export default function DocumentsPage() {
  const { projectId } = useParams();
  const queryClient = useQueryClient();

  // Currently selected document type in the sidebar
  const [selected, setSelected] = useState("srs");

  // ── QUERY: fetch all document headers (to know which types exist) ─────────
  const { data: documents = [] } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => projectsApi.listDocuments(projectId),
  });

  // ── QUERY: fetch the content of the currently selected document ───────────
  const { data: currentDoc, isLoading: docLoading } = useQuery({
    queryKey: ["document", projectId, selected],
    queryFn: () => projectsApi.getDocument(projectId, selected),
    enabled: !!selected,   // Only fetch when a type is selected
    retry: false,          // Don't retry 404s (document not generated yet)
  });

  // ── MUTATION: trigger regeneration of a document ─────────────────────────
  const regenMutation = useMutation({
    mutationFn: (docType) => projectsApi.generateDocuments(projectId, [docType]),
    onSuccess: () => {
      // Wait 8 seconds for generation to complete, then re-fetch
      setTimeout(() => {
        queryClient.invalidateQueries(["document", projectId, selected]);
      }, 8000);
    },
  });

  // Set of document types that have been generated — for the green dot indicator
  const generatedTypes = new Set(documents.map((d) => d.doc_type));

  return (
    <div style={{ maxWidth: 1000, display: "flex", gap: 24 }}>

      {/* ── LEFT SIDEBAR: Document type list ── */}
      <div style={{ width: 220, flexShrink: 0 }}>
        <h3 style={{
          fontSize: 11, textTransform: "uppercase",
          letterSpacing: "0.08em", color: "var(--color-text-muted)", marginBottom: 12,
        }}>
          Documents
        </h3>

        {DOC_TYPES.map((type) => {
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
                // Full text colour if generated, muted if not yet generated
                color: isSelected ? "white" : isGenerated ? "var(--color-text)" : "var(--color-text-muted)",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                textAlign: "left",
                marginBottom: 2,
              }}
            >
              <FileText size={14} />
              {/* Show first 2 words of label to fit in narrow sidebar */}
              <span style={{ flex: 1 }}>{DOC_LABELS[type].split(" ").slice(0, 2).join(" ")}</span>

              {/* Green dot: this document has been generated */}
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

      {/* ── RIGHT PANEL: Document content ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Content header: document title + regenerate button */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700 }}>{DOC_LABELS[selected]}</h2>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => regenMutation.mutate(selected)}
            disabled={regenMutation.isPending}
            title="Regenerate this document (creates a new version)"
          >
            {regenMutation.isPending ? <Loader size={12} className="spin" /> : <RefreshCw size={12} />}
            Regenerate
          </button>
        </div>

        {/* Document content states */}
        {docLoading ? (
          // Loading: fetching document content
          <div className="loading-state"><Loader className="spin" /></div>

        ) : currentDoc ? (
          // Loaded: render the markdown content
          <div className="card markdown-content" style={{ padding: 28, lineHeight: 1.7 }}>
            {/*
              ReactMarkdown converts the content_markdown string into HTML elements.
              The .markdown-content class in index.css styles the resulting HTML
              (headings, tables, bold, code, etc.) to match the dark theme.
            */}
            <ReactMarkdown>
              {currentDoc.content_markdown || JSON.stringify(currentDoc.content_json, null, 2)}
            </ReactMarkdown>
          </div>

        ) : (
          // Not generated yet
          <div className="card" style={{ textAlign: "center", padding: 48 }}>
            <FileText size={48} color="var(--color-border)" style={{ margin: "0 auto 16px" }} />
            <p style={{ color: "var(--color-text-muted)" }}>
              This document hasn't been generated yet. Go to the project page and click "Generate Everything".
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
