/**
 * api/projects.js — All project-related API calls in one place.
 *
 * WHY THIS FILE EXISTS:
 *   Every feature page (Dashboard, Requirements, Documents, Diagrams...)
 *   needs to talk to the backend. Centralizing all API calls here means:
 *     - No duplicate fetch logic scattered across components
 *     - Easy to find and update API calls when endpoints change
 *     - All calls automatically get JWT headers from the client interceptor
 *
 * PATTERN USED:
 *   client.method(url, body).then((r) => r.data)
 *   All functions extract .data from the Axios response (not the full response object).
 *   React Query (useQuery/useMutation) wraps these in loading/error state management.
 *
 * MULTIPART UPLOADS:
 *   File uploads use FormData with multipart/form-data content-type.
 *   We override the Content-Type header so Axios includes the boundary parameter
 *   that multipart requests require.
 */

import client from "./client";

export const projectsApi = {
  // ── PROJECTS ──────────────────────────────────────────────────────────────
  list:   ()           => client.get("/projects/").then((r) => r.data),
  create: (data)       => client.post("/projects/", data).then((r) => r.data),
  get:    (id)         => client.get(`/projects/${id}`).then((r) => r.data),
  update: (id, data)   => client.patch(`/projects/${id}`, data).then((r) => r.data),
  delete: (id)         => client.delete(`/projects/${id}`),

  // ── INPUTS ────────────────────────────────────────────────────────────────
  /**
   * submitText — POST plain text or transcript as a requirement input.
   * data = { text: "...", is_transcript: false }
   */
  submitText: (projectId, data) =>
    client.post(`/projects/${projectId}/inputs/text`, data).then((r) => r.data),

  /**
   * uploadFile — POST a PDF/DOCX/TXT file for requirement extraction.
   * Uses FormData for multipart upload. Backend extracts text asynchronously.
   */
  uploadFile: (projectId, file) => {
    const form = new FormData();
    form.append("file", file); // "file" must match the FastAPI endpoint's File(...) parameter name
    return client.post(`/projects/${projectId}/inputs/upload`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      // Axios will automatically set the boundary when Content-Type is multipart
    }).then((r) => r.data);
  },

  listInputs: (projectId) =>
    client.get(`/projects/${projectId}/inputs/`).then((r) => r.data),

  // ── REQUIREMENTS ──────────────────────────────────────────────────────────
  /**
   * analyzeRequirements — Trigger the AI LangGraph pipeline.
   * Returns 202 immediately. Poll GET /requirements/ for results.
   * inputIds: optional — pass null to analyze all inputs.
   */
  analyzeRequirements: (projectId, inputIds = null) =>
    client.post(`/projects/${projectId}/requirements/analyze`, { input_ids: inputIds })
      .then((r) => r.data),

  /**
   * listRequirements — Get all extracted requirements.
   * category: optional filter, e.g., "functional" or "risk"
   */
  listRequirements: (projectId, category = null) =>
    client.get(`/projects/${projectId}/requirements/`, {
      params: category ? { category } : {},
    }).then((r) => r.data),

  updateRequirement: (projectId, reqId, data) =>
    client.patch(`/projects/${projectId}/requirements/${reqId}`, data).then((r) => r.data),

  // ── DOCUMENTS ─────────────────────────────────────────────────────────────
  /**
   * generateDocuments — Trigger AI document generation.
   * docTypes: null = all 8 types, or array like ["srs", "brd"]
   * retryFailedOnly: true = ignore docTypes, regenerate only previously-failed types
   */
  generateDocuments: (projectId, docTypes = null, retryFailedOnly = false) =>
    client.post(`/projects/${projectId}/documents/generate`, {
      doc_types: docTypes,
      retry_failed_only: retryFailedOnly,
    }).then((r) => r.data),

  listDocuments: (projectId) =>
    client.get(`/projects/${projectId}/documents/`).then((r) => r.data),

  /** getDocument — Returns the LATEST version's content (markdown + JSON) */
  getDocument: (projectId, docType) =>
    client.get(`/projects/${projectId}/documents/${docType}`).then((r) => r.data),

  getDocumentVersions: (projectId, docType) =>
    client.get(`/projects/${projectId}/documents/${docType}/versions`).then((r) => r.data),

  /** diffDocuments — Compare version vA vs vB of a document (bonus feature) */
  diffDocuments: (projectId, docType, vA, vB) =>
    client.get(`/projects/${projectId}/documents/${docType}/diff`, {
      params: { version_a: vA, version_b: vB },
    }).then((r) => r.data),

  // ── PLANNING ──────────────────────────────────────────────────────────────
  /**
   * generatePlanning — Trigger planning artifact generators (all 8 by default).
   * retryFailedOnly: true = regenerate only previously-failed artifact types
   */
  generatePlanning: (projectId, retryFailedOnly = false) =>
    client.post(`/projects/${projectId}/planning/generate`, {
      retry_failed_only: retryFailedOnly,
    }).then((r) => r.data),

  listPlanning: (projectId) =>
    client.get(`/projects/${projectId}/planning/`).then((r) => r.data),

  getPlanningArtifact: (projectId, type) =>
    client.get(`/projects/${projectId}/planning/${type}`).then((r) => r.data),

  // ── DIAGRAMS ──────────────────────────────────────────────────────────────
  /**
   * generateDiagrams — Trigger diagram generators (all 6 by default).
   * retryFailedOnly: true = regenerate only previously-failed diagram types
   */
  generateDiagrams: (projectId, retryFailedOnly = false) =>
    client.post(`/projects/${projectId}/diagrams/generate`, {
      retry_failed_only: retryFailedOnly,
    }).then((r) => r.data),

  listDiagrams: (projectId) =>
    client.get(`/projects/${projectId}/diagrams/`).then((r) => r.data),

  getDiagram: (projectId, type) =>
    client.get(`/projects/${projectId}/diagrams/${type}`).then((r) => r.data),

  // ── REVIEW ────────────────────────────────────────────────────────────────
  /** runReview — Trigger the AI second-pass quality reviewer */
  runReview: (projectId) =>
    client.post(`/projects/${projectId}/review/run`).then((r) => r.data),

  getLatestReview: (projectId) =>
    client.get(`/projects/${projectId}/review/latest`).then((r) => r.data),

  // ── BONUS FEATURES ────────────────────────────────────────────────────────
  /**
   * moscowPrioritize — Run AI MoSCoW re-prioritization on all requirements.
   * Returns synchronously with the list of priority changes.
   */
  moscowPrioritize: (projectId) =>
    client.post(`/projects/${projectId}/prioritize/moscow`).then((r) => r.data),
};