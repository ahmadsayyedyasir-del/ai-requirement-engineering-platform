/**
 * pages/LoginPage.jsx â€” Email + password login form.
 *
 * WHY THIS FILE EXISTS:
 *   The entry point for returning users. Collects email and password,
 *   calls the login API via AuthContext, and redirects to the dashboard.
 *
 * STATE MANAGEMENT:
 *   form    â†’ controlled inputs: { email, password }
 *             React "controlled inputs" means the input's value is always
 *             driven by React state, not the DOM. Every keystroke calls
 *             setForm(), keeping React in sync with what the user types.
 *   error   â†’ error message string shown in the red error box
 *   loading â†’ true while the API call is in flight (shows spinner, disables button)
 *
 * ERROR HANDLING PATTERN:
 *   try/catch around the async login call.
 *   err.response?.data?.detail extracts FastAPI's error message
 *   (e.g., "Incorrect email or password") from the 401 response body.
 *   The ?. optional chaining prevents crashes if the response has no body.
 *   Falls back to a generic message if no API detail is available.
 *
 * WHY e.preventDefault()?
 *   Forms submit by default by making a full page reload to the action URL.
 *   preventDefault() stops that and lets our async handleSubmit() run instead.
 */

import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext"; // Login function lives here
import { Brain, Loader } from "lucide-react";

export default function LoginPage() {
  const { login } = useAuth(); // Destructure just the login function from context
  const navigate = useNavigate();

  // Controlled form state â€” one object for all fields keeps the update pattern simple
  const [form, setForm] = useState({ email: "", password: "" });

  // Error message to display below the form inputs
  const [error, setError] = useState("");

  // Loading flag â€” prevents double-submission and shows visual feedback
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();   // Stop browser's default form submission
    setError("");          // Clear any previous error before trying again
    setLoading(true);

    try {
      // login() (from AuthContext) calls the API, stores the token, sets user state
      await login(form.email, form.password);

      // On success: redirect to the dashboard
      navigate("/");

    } catch (err) {
      // Show the API's error message (e.g., "Incorrect email or password")
      // or a generic fallback if the response body doesn't have a `detail` field
      setError(err.response?.data?.detail || "Login failed. Check your credentials.");
    } finally {
      setLoading(false); // Re-enable the form whether login succeeded or failed
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">

        {/* Logo + branding */}
        <div className="auth-logo">
          <Brain size={40} color="var(--color-primary)" />
          <h1>ReqAI Platform</h1>
          <p>AI-powered requirement engineering</p>
        </div>

        {/* Login form */}
        <form onSubmit={handleSubmit} className="auth-form">

          <div className="form-group">
            <label htmlFor="email">Email</label>
            {/*
              The `id="email"` matches the label's `htmlFor="email"`.
              This links them so clicking the label focuses the input â€”
              important for accessibility (screen readers, keyboard users).
            */}
            <input
              id="email"
              type="email"              /* Browser validates email format */
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="analyst@company.com"
              required
              autoFocus                 /* Focus this field when the page loads */
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"           /* Masks the input characters */
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
              required
            />
          </div>

          {/* Show error if login failed â€” only rendered when error string is non-empty */}
          {error && <div className="auth-error">{error}</div>}

          {/* Submit button â€” disabled while loading to prevent double-submit */}
          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={loading}
          >
            {/* Show spinner icon while the API call is running */}
            {loading && <Loader size={16} className="spin" />}
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        {/* Link to register â€” for users who don't have an account yet */}
        <p className="auth-footer">
          No account? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  );
}
