/**
 * api/client.js — Axios HTTP client + auth API calls.
 *
 * Two things in one file:
 *   1. `client` — Axios instance with JWT injection and 401 redirect
 *   2. `authApi` — login, register, me, logout (previously in auth.js)
 *
 * auth.js was merged here because it was only ~40 lines, imported by exactly
 * one file (AuthContext.jsx), and always loaded alongside this module anyway.
 */

import axios from "axios";

// PRODUCTION: set VITE_API_URL=https://your-api.railway.app in Vercel dashboard.
// DEVELOPMENT: leave unset — Vite proxy (vite.config.js) forwards /api/... to localhost:8000.
const BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "";

// ── Axios instance ────────────────────────────────────────────────────────────
const client = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Inject JWT token before every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401: clear invalid token and redirect to login
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default client;

// ── Auth API ──────────────────────────────────────────────────────────────────
// Login uses form-encoded data (not JSON) because FastAPI's
// OAuth2PasswordRequestForm expects "username=...&password=..." format.
// All other auth calls use the standard JSON client above.
export const authApi = {
  login: async (email, password) => {
    const form = new URLSearchParams();
    form.append("username", email); // FastAPI calls this "username"; we use email
    form.append("password", password);
    const res = await axios.post(`${BASE_URL}/api/v1/auth/login`, form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return res.data; // { access_token, token_type }
  },

  register: (data) => client.post("/auth/register", data).then((r) => r.data),

  me: () => client.get("/auth/me").then((r) => r.data),

  // JWTs are stateless — clearing localStorage is sufficient to log out
  logout: () => localStorage.removeItem("access_token"),
};
