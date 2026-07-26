/**
 * api/auth.js — Authentication API calls (login, register, get current user, logout).
 *
 * WHY A SEPARATE FILE FROM client.js?
 *   The login endpoint uses form-encoded data (not JSON) because it follows
 *   the OAuth2 specification that FastAPI's OAuth2PasswordRequestForm expects.
 *   A regular JSON POST would fail with a 422 Unprocessable Entity error.
 *
 *   So login uses raw axios with Content-Type: application/x-www-form-urlencoded,
 *   while all other auth calls use the standard client (JSON).
 *
 * OAUTH2 FORM FORMAT:
 *   The FastAPI login endpoint uses OAuth2PasswordRequestForm which parses
 *   form-encoded data with fields named `username` and `password`.
 *   We use email as the username — the form doesn't care about semantics.
 *   URLSearchParams produces: "username=user@example.com&password=mypass"
 */

import client from "./client";    // Our configured Axios instance with JWT interceptor
import axios from "axios";        // Raw Axios — used only for login (special content-type)

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const authApi = {
  /**
   * login — Authenticate and receive a JWT access token.
   *
   * WHY URLSearchParams INSTEAD OF JSON?
   *   FastAPI's OAuth2PasswordRequestForm expects form-encoded data, not JSON.
   *   URLSearchParams.append() builds "username=...&password=..." format.
   *   We set Content-Type to "application/x-www-form-urlencoded" explicitly.
   *
   * RETURNS: { access_token: "eyJ...", token_type: "bearer" }
   * The AuthContext stores access_token in localStorage after this resolves.
   */
  login: async (email, password) => {
    // Build form-encoded body — OAuth2 standard format
    const form = new URLSearchParams();
    form.append("username", email);    // FastAPI calls this "username" (we use email)
    form.append("password", password);

    const response = await axios.post(`${BASE_URL}/api/v1/auth/login`, form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return response.data; // { access_token, token_type }
  },

  /**
   * register — Create a new analyst account.
   *
   * Uses standard JSON POST. Returns the created user (without password).
   * After registration, the user is redirected to login — they're not logged in yet.
   */
  register: (data) =>
    client.post("/auth/register", data).then((r) => r.data),
  // data = { email, full_name, password }

  /**
   * me — Fetch the profile of the currently authenticated user.
   *
   * Called by AuthContext on app startup to:
   *   1. Check if the stored token is still valid
   *   2. Get the user's name/role for display in the sidebar
   * If the token is expired/invalid, this will return 401 → interceptor clears token.
   */
  me: () => client.get("/auth/me").then((r) => r.data),
  // Returns: { id, email, full_name, role, is_active }

  /**
   * logout — Clear the stored JWT token (client-side only).
   *
   * WHY NO SERVER CALL?
   *   JWTs are stateless — the server has no session to invalidate.
   *   Removing the token from localStorage is sufficient because:
   *     1. The token will expire naturally (24 hours)
   *     2. Without the token, no authenticated requests can be made
   *   For higher security, implement a server-side token blacklist.
   */
  logout: () => localStorage.removeItem("access_token"),
};
