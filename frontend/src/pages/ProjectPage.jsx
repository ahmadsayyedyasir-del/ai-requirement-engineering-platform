/**
 * pages/ProjectPage.jsx â€” The central hub for one project.
 *
 * WHY THIS FILE EXISTS:
 *   Every project goes through a 3-step pipeline before artifacts are ready:
 *     Step 1 â€” Submit business input (text, transcript, or file upload)
 *     Step 2 â€” Run AI analysis (triggers the LangGraph pipeline)
 *     Step 3 â€” Generate full document package (docs + planning + diagrams)
 *   This page guides the analyst through those three steps in order.
 *   It also shows navigation cards linking to each artifact tab.
 *
 * KEY POLLING BEHAVIOUR:
 *   The project status query uses `refetchInterval` to auto-refresh every 3s
 *   when the project is in "analyzing" or "generating" state. This is how
 *   the spinner on the status pill stays in sync without the user refreshing.
 *   When the status becomes "analyzed" or "completed", refetchInterval returns
 *   false and polling stops automatically.
 *
 * GENERATE ALL MUTATION:
 *   generateAllMutation calls THREE API endpoints in sequence (documents,
 *   planning, diagrams). Each returns 202 immediately â€” the actual generation
 *   runs on the server. The mutation just kicks all three off at once.
 *
 * FILE DRAG-AND-DROP:
 *   The drop zone div handles onDragOver (prevents default browser behaviour
 *   which would otherwise open the file in the browser) and onDrop (captures
 *   the dropped file and sets it in state). The hidden <input type="file">
 *   covers the entire zone so clicking anywhere also opens the file picker.
 *
 * CONDITIONAL SECTION (Step 3):
 *   Step 3 "Generate Everything" only renders AFTER requirements are analyzed.
 *   Project status "analyzed", "completed", or "generating" all trigger this.
 *   This prevents generating documents before there are any requirements.
 */

import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../api/projects";
import {
  Upload, FileText, Brain, FileSearch, BarChart2, GitBranch,
  MessageSquare, CheckCircle2, Loader, ArrowRight, Zap, AlertTriangle, RotateCcw,
} from "lucide-react";

// Turns project.generation_errors into a simple per-section summary:
// { documents: { total: 8, ok: 6, failed: 2, failedNames: [...] }, ... }
// Used to render real progress and a "Retry Failed" action instead of a
// spinner that stops the instant the 202 responses come back (which used to
// happen well before the actual background generation was anywhere near done).
function summarizeGeneration(generationErrors) {
  const sections = ["documents", "planning", "diagrams"];
  const summary = {};
  for (const section of sections) {
    const items = generationErrors?.[section] || {};
    const names = Object.keys(items);
    const failedNames = names.filter((n) => items[n] !== "ok");
    summary[section] = {
      total: names.length,
      ok: names.length - failedNames.length,
      failed: failedNames.length,
      failedNames,
    };
  }
  return summary;
}

export default function ProjectPage() {
  // projectId comes from the URL path: /projects/:projectId
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Text input state
  const [textInput, setTextInput]     = useState("");
  const [isTranscript, setIsTranscript] = useState(false);

  // File upload state â€” holds the File object selected by the user
  const [uploadFile, setUploadFile] = useState(null);

  // Success message banner state (shown after actions like "Input submitted")
  const [actionMsg, setActionMsg] = useState("");

  // â”€â”€ QUERIES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  // Fetch the project â€” auto-polls every 3s while analyzing/generating
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId),
    refetchInterval: (data) =>
      // If the pipeline is running, keep polling every 3s to pick up status changes
      data?.status === "analyzing" || data?.status === "generating" ? 3000 : false,
  });

  // Fetch the list of submitted inputs for this project
  const { data: inputs = [] } = useQuery({
    queryKey: ["inputs", projectId],
    queryFn: () => projectsApi.listInputs(projectId),
  });

  // â”€â”€ MUTATIONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  // Submit text input
  const textMutation = useMutation({
    mutationFn: () =>
      projectsApi.submitText(projectId, { text: textInput, is_transcript: isTranscript }),
    onSuccess: () => {
      queryClient.invalidateQueries(["inputs", projectId]); // Refresh inputs list
      setTextInput("");
      setActionMsg("Input submitted successfully.");
    },
  });

  // Upload file input
  const uploadMutation = useMutation({
    mutationFn: () => projectsApi.uploadFile(projectId, uploadFile),
    onSuccess: () => {
      queryClient.invalidateQueries(["inputs", projectId]);
      setUploadFile(null);
      setActionMsg("File uploaded and queued for text extraction.");
    },
  });

  // Trigger AI requirement analysis
  const analyzeMutation = useMutation({
    mutationFn: () => projectsApi.analyzeRequirements(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries(["project", projectId]); // Picks up "analyzing" status
      setActionMsg("AI analysis started. This takes 30â€“60 seconds.");
    },
  });

  // Generate ALL artifacts (documents + planning + diagrams) in one click
  const generateAllMutation = useMutation({
    mutationFn: async () => {
      // These three calls all return 202 immediately â€” generation runs on the
      // server. project.status flips to "generating" as soon as the first one
      // starts, which is what actually drives the progress UI below (via the
      // 3s poll on the project query) â€” not this mutation's pending state.
      await projectsApi.generateDocuments(projectId);
      await projectsApi.generatePlanning(projectId);
      await projectsApi.generateDiagrams(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries(["project", projectId]); // Picks up "generating" status
      setActionMsg("Generation started â€” watch the progress below.");
    },
  });

  // Retry only the items that failed on the last run, per section
  const retryFailedMutation = useMutation({
    mutationFn: async () => {
      await projectsApi.generateDocuments(projectId, null, true);
      await projectsApi.generatePlanning(projectId, true);
      await projectsApi.generateDiagrams(projectId, true);
    },
    onSuccess: () => {
      queryClient.invalidateQueries(["project", projectId]);
      setActionMsg("Retrying failed items.");
    },
  });

  // Live per-section progress derived from project.generation_errors, which
  // the backend updates as each item finishes (not just when the whole batch does).
  const genSummary = summarizeGeneration(project?.generation_errors);
  const totalFailed = genSummary.documents.failed + genSummary.planning.failed + genSummary.diagrams.failed;
  const totalDone = genSummary.documents.ok + genSummary.planning.ok + genSummary.diagrams.ok;
  const totalItems = 8 + 8 + 6; // 8 documents + 8 planning artifacts + 6 diagrams
  const isGenerating = project?.status === "generating";

  // â”€â”€ NAVIGATION CARDS CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Each card links to an artifact tab within this project
  const navCards = [
    { label: "Requirements", icon: Brain,      path: "requirements", color: "#6366f1" },
    { label: "Documents",    icon: FileText,   path: "documents",    color: "#22d3ee" },
    { label: "Planning",     icon: BarChart2,  path: "planning",     color: "#f59e0b" },
    { label: "Diagrams",     icon: GitBranch,  path: "diagrams",     color: "#a78bfa" },
    { label: "AI Review",    icon: FileSearch, path: "review",       color: "#22c55e" },
  ];

  // Show spinner while project is loading for the first time
  if (!project) return <div className="loading-state"><Loader className="spin" /></div>;

  return (
    <div className="project-page">

      {/* â”€â”€ Page header: project name + status pill â”€â”€ */}
      <div className="page-header">
        <div>
          <h1>{project.name}</h1>
          <p className="subtitle">{project.description}</p>
        </div>
        {/* data-status drives the colour via CSS attribute selectors */}
        <div className="status-pill" data-status={project.status}>
          {/* Spinner icon only when actively analyzing */}
          {project.status === "analyzing" && <Loader size={12} className="spin" />}
          {project.status}
        </div>
      </div>

      {/* â”€â”€ Success action banner â”€â”€ */}
      {actionMsg && (
        <div className="action-banner">
          <CheckCircle2 size={16} />
          {actionMsg}
          {/* Ã— button clears the message */}
          <button onClick={() => setActionMsg("")}>Ã—</button>
        </div>
      )}

      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {/* STEP 1 â€” Submit Business Input                                      */}
      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <section className="section">
        <h2><span className="step-num">1</span> Add Business Input</h2>

        <div className="input-grid">

          {/* LEFT: Text / Transcript input */}
          <div className="card">
            <div className="card-title"><MessageSquare size={16} /> Text / Transcript</div>
            <textarea
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder="Paste your business idea, requirements description, or meeting transcript here..."
              rows={6}
            />
            <div className="card-footer">
              {/* Checkbox: is this a meeting transcript? (affects AI extraction strategy) */}
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={isTranscript}
                  onChange={(e) => setIsTranscript(e.target.checked)}
                />
                Meeting transcript
              </label>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => textMutation.mutate()}
                disabled={!textInput.trim() || textMutation.isPending}
              >
                {textMutation.isPending && <Loader size={12} className="spin" />}
                Submit
              </button>
            </div>
          </div>

          {/* RIGHT: File upload (PDF/DOCX) */}
          <div className="card">
            <div className="card-title"><Upload size={16} /> Upload Document</div>
            {/* Drag-and-drop zone */}
            <div
              className="drop-zone"
              onDragOver={(e) => e.preventDefault()} // Must prevent default to enable drop
              onDrop={(e) => {
                e.preventDefault();
                setUploadFile(e.dataTransfer.files[0]); // Capture the dropped file
              }}
            >
              {uploadFile ? (
                // Show selected filename
                <p><FileText size={16} /> {uploadFile.name}</p>
              ) : (
                <p>Drop PDF or DOCX here, or click to browse</p>
              )}
              {/* Hidden file input â€” covers the whole zone, opens picker on click */}
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={(e) => setUploadFile(e.target.files[0])}
              />
            </div>
            <div className="card-footer" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => uploadMutation.mutate()}
                disabled={!uploadFile || uploadMutation.isPending}
              >
                {uploadMutation.isPending && <Loader size={12} className="spin" />}
                Upload
              </button>
            </div>
          </div>
        </div>

        {/* List of submitted inputs â€” shows type, preview, and processing status */}
        {inputs.length > 0 && (
          <div className="inputs-list">
            {inputs.map((inp) => (
              <div key={inp.id} className="input-item">
                {/* Type badge: "text", "pdf", "transcript", etc. */}
                <span className="tag">{inp.input_type}</span>
                {/* Content preview: filename for uploads, first 80 chars for text */}
                <span>{inp.file_name || (inp.raw_text?.slice(0, 80) + "...")}</span>
                {/* Processing status dot */}
                <span className={`status-dot ${inp.is_processed ? "done" : "pending"}`}>
                  {inp.is_processed ? "processed" : "pending"}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {/* STEP 2 â€” Run AI Analysis                                            */}
      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <section className="section">
        <h2><span className="step-num">2</span> Run AI Analysis</h2>
        <p className="section-desc">
          Extract structured requirements using the 5-node LangGraph pipeline with ChromaDB RAG context.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => analyzeMutation.mutate()}
          disabled={
            inputs.length === 0            ||  // No inputs yet â€” nothing to analyze
            project.status === "analyzing" ||  // Already running â€” prevent duplicate
            analyzeMutation.isPending          // Mutation in flight
          }
        >
          {project.status === "analyzing"
            ? <Loader size={16} className="spin" />
            : <Brain size={16} />
          }
          {project.status === "analyzing" ? "Analyzing..." : "Analyze Requirements"}
        </button>
      </section>

      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {/* STEP 3 â€” Generate Full Document Package                             */}
      {/* Only shown after requirements have been analyzed.                   */}
      {/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {(project.status === "analyzed" ||
        project.status === "completed" ||
        project.status === "generating") && (
        <section className="section">
          <h2><span className="step-num">3</span> Generate Full Document Package</h2>
          <p className="section-desc">
            Generate SRS, BRD, User Stories, Planning artifacts, and 6 Mermaid.js diagrams in one click.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => generateAllMutation.mutate()}
            disabled={generateAllMutation.isPending || isGenerating}
            style={{ background: "linear-gradient(135deg, #6366f1, #22d3ee)" }}
          >
            {(generateAllMutation.isPending || isGenerating)
              ? <Loader size={16} className="spin" />
              : <Zap size={16} />
            }
            {isGenerating ? "Generating..." : "Generate Everything"}
          </button>

          {/* Live progress â€” driven by project.generation_errors, refreshed by the
              3s poll while status === "generating". Replaces the old behaviour
              where the button's spinner stopped the instant the three 202
              responses came back, long before generation had actually finished. */}
          {(isGenerating || totalDone > 0 || totalFailed > 0) && (
            <div className="generation-progress" style={{ marginTop: 16 }}>
              <p className="section-desc">
                {totalDone + totalFailed} / {totalItems} items processed
                {isGenerating && " â€” still working..."}
              </p>
              {["documents", "planning", "diagrams"].map((section) => {
                const s = genSummary[section];
                if (s.total === 0) return null;
                return (
                  <div key={section} className="tag" style={{ marginRight: 8, marginBottom: 8, display: "inline-flex", gap: 6, alignItems: "center" }}>
                    {section}: {s.ok} ok{s.failed > 0 && `, ${s.failed} failed`}
                  </div>
                );
              })}

              {!isGenerating && totalFailed > 0 && (
                <div className="action-banner" style={{ background: "var(--color-danger-bg, #2a1414)", marginTop: 8 }}>
                  <AlertTriangle size={16} />
                  {totalFailed} item{totalFailed > 1 ? "s" : ""} failed to generate
                  (usually a transient rate-limit â€” safe to retry).
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => retryFailedMutation.mutate()}
                    disabled={retryFailedMutation.isPending}
                    style={{ marginLeft: 12 }}
                  >
                    {retryFailedMutation.isPending
                      ? <Loader size={12} className="spin" />
                      : <RotateCcw size={12} />
                    }
                    Retry Failed Only
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* â”€â”€ Artifact navigation cards â”€â”€ */}
      <section className="section">
        <h2>Artifacts</h2>
        <div className="nav-cards">
          {navCards.map(({ label, icon: Icon, path, color }) => (
            <button
              key={path}
              className="nav-card card"
              onClick={() => navigate(`/projects/${projectId}/${path}`)}
            >
              <Icon size={24} color={color} />
              <span>{label}</span>
              <ArrowRight size={14} color="var(--color-text-muted)" />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
