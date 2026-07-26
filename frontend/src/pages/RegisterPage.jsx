/**
 * pages/RegisterPage.jsx — New user registration form.
 *
 * WHY THIS FILE EXISTS:
 *   Lets new analysts create an account. After successful registration,
 *   redirects to /login — they are NOT automatically logged in.
 *
 * WHY NOT AUTO-LOGIN AFTER REGISTER?
 *   Keeping registration and login as separate steps is simpler and more
 *   secure. The user goes to /login and explicitly enters their credentials.
 *   This also makes it obvious that registration succeeded.
 *
 * NOTE: authApi.register() is called directly here (not through AuthContext)
 *   because registration doesn't set a session — it just creates a DB record.
 *   Login is what creates a session, so that's what lives in AuthContext.
 *
 * FORM VALIDATION:
 *   minLength={8} on the password input lets the browser enforce the minimum
 *   before the form is submitted. Server-side validation enforces it too
 *   (FastAPI schema has min_length=8), so there's a double safety net.
 */

import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authApi } from "../api/auth"; // Direct API call — no context needed for register
import { Brain, Loader } from "lucide-react";
import "./AuthPage.css";

export default function RegisterPage() {
  const navigate = useNavigate();

  // Three-field form — email, full name, password
  const [form, setForm] = useState({ email: "", full_name: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault(); // Prevent browser form submit (page reload)
    setError("");
    setLoading(true);

    try {
      // Create the account — POST /auth/register with {email, full_name, password}
      await authApi.register(form);

      // On success: go to login page so user can sign in with their new account
      navigate("/login");

    } catch (err) {
      // Common error: "Email already registered" (HTTP 400 from FastAPI)
      setError(err.response?.data?.detail || "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">

        {/* Logo + branding — same as LoginPage for visual consistency */}
        <div className="auth-logo">
          <Brain size={40} color="var(--color-primary)" />
          <h1>Create Account</h1>
          <p>Join the ReqAI Platform</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">

          {/* Full name — displayed in the sidebar and on generated documents */}
          <div className="form-group">
            <label>Full Name</label>
            <input
              type="text"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              placeholder="Jane Smith"
              required
            />
          </div>

          {/* Email — used as the login username */}
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="jane@company.com"
              required
            />
          </div>

          {/* Password — minLength enforces the 8-char minimum client-side */}
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="Minimum 8 characters"
              minLength={8}
              required
            />
          </div>

          {error && <div className="auth-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={loading}
          >
            {loading && <Loader size={16} className="spin" />}
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="auth-footer">
          Have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
