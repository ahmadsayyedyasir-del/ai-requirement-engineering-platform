/**
 * api/client.js — Axios HTTP client with automatic JWT token injection.
 *
 * WHY THIS FILE EXISTS:
 *   Every API call in the app needs to:
 *     1. Send the JWT token in the Authorization header
 *     2. Handle 401 errors (token expired / invalid) by redirecting to login
 *   Without this file, every single api/... function would need to manually
 *   add the header and handle 401s. Instead, we configure it ONCE here.
 *
 * HOW AXIOS INTERCEPTORS WORK:
 *   Interceptors are middleware that run before a request is sent (request interceptor)
 *   or after a response is received (response interceptor).
 *
 *   Request interceptor: runs BEFORE the request leaves the browser.
 *     We use this to inject the Authorization header with the stored JWT token.
 *
 *   Response interceptor: runs AFTER the server responds.
 *     We use this to catch 401 errors (auth failures) and redirect to /login.
 *
 * HOW JWT TOKENS ARE STORED:
 *   localStorage is used to persist the token across page refreshes.
 *   The token is stored by the AuthContext after a successful login.
 *   It's removed by AuthContext on logout or by the response interceptor on 401.
 *
 *   Note: localStorage is accessible by JavaScript on the same origin.
 *   For higher security in production, consider httpOnly cookies instead.
 *
 * WHAT IS BASE_URL?
 *   In development (Vite dev server): VITE_API_BASE_URL is empty (""),
 *   so requests go to /api/v1/... and Vite proxies them to http://localhost:8000.
 *   In production (Docker): VITE_API_BASE_URL is set and requests go directly
 *   to the API container. The trailing "" (empty string) is a safe default.
 */

import axios from "axios";

// Read the API base URL from the Vite environment variable.
// Set in .env as: VITE_API_BASE_URL=http://localhost:8000
// Falls back to "" in development (Vite proxy handles routing).
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

// Create an Axios instance with default configuration.
// All API calls in the app use THIS instance, not raw axios.
const client = axios.create({
  baseURL: `${BASE_URL}/api/v1`,              // All requests are prefixed with /api/v1
  headers: { "Content-Type": "application/json" },
});

// ── REQUEST INTERCEPTOR ────────────────────────────────────────────────────────
// Runs before EVERY request sent by this client instance.
// Reads the JWT token from localStorage and adds it to the Authorization header.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token"); // Stored by AuthContext after login

  if (token) {
    // Standard HTTP Authorization header format for Bearer tokens.
    // The FastAPI backend reads this header via the oauth2_scheme dependency.
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config; // Return the (possibly modified) config to proceed with the request
});

// ── RESPONSE INTERCEPTOR ───────────────────────────────────────────────────────
// Runs after EVERY response received by this client instance.
client.interceptors.response.use(
  // Success handler: called when response status is 2xx.
  // Just pass the response through — no modification needed.
  (response) => response,

  // Error handler: called when response status is NOT 2xx.
  (error) => {
    if (error.response?.status === 401) {
      // 401 = Unauthorized. This means the token is:
      //   - Missing (user not logged in)
      //   - Expired (token's "exp" claim has passed)
      //   - Invalid (tampered or using wrong key)

      // Clear the invalid token from storage so the next page load
      // shows the login page instead of an infinite redirect loop.
      localStorage.removeItem("access_token");

      // Redirect to login. window.location.href causes a full page reload,
      // which clears all React state (clean slate for login page).
      window.location.href = "/login";
    }

    // Re-throw the error so individual API calls can handle it
    // (e.g., show "Login failed" message on the login page)
    return Promise.reject(error);
  }
);

export default client; // Export for use in all api/*.js files
