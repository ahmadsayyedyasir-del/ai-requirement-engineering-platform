/**
 * main.jsx — The entry point of the React application.
 *
 * WHY THIS FILE EXISTS:
 *   This is the first JavaScript file the browser executes. It mounts the
 *   entire React component tree into the <div id="root"> in public/index.html.
 *
 * PROVIDER NESTING ORDER (outermost → innermost):
 *
 *   1. QueryClientProvider — React Query for server state management.
 *      Must wrap everything so any component can call useQuery/useMutation.
 *      Caches API responses, manages loading/error states, auto-refetches stale data.
 *
 *   2. BrowserRouter — React Router for URL-based navigation.
 *      Must wrap App so useNavigate/useParams/NavLink work in any component.
 *
 *   3. App — The root component containing all route definitions.
 *      AuthProvider lives inside App (not here) so it can use router hooks.
 *
 * QUERYCLIENT SETTINGS:
 *   retry: 1       → If a network request fails, retry once before showing error.
 *                    Without this, a single network hiccup would show an error immediately.
 *   staleTime: 30s → Cached data is considered "fresh" for 30 seconds.
 *                    If you navigate away and come back within 30s, no new API call is made.
 *                    After 30s, the next component mount re-fetches in the background.
 *
 * REACT.STRICTMODE:
 *   Intentionally double-invokes certain functions in development to expose
 *   bugs early (e.g., missing cleanup in useEffect). Has zero effect in production.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css"; // Global CSS variables, resets, utility classes

// Create the React Query client — one instance shared across the whole app.
// This manages the cache of all server responses.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,          // Retry once on failure before showing error UI
      staleTime: 30_000, // 30 000ms = 30 seconds before re-fetching
    },
  },
});

// ReactDOM.createRoot is the React 18 concurrent API.
// Find the <div id="root"> defined in public/index.html and mount our app inside it.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* React Query: makes useQuery/useMutation available anywhere in the tree */}
    <QueryClientProvider client={queryClient}>
      {/* React Router: enables URL-based routing with history API */}
      <BrowserRouter>
        {/* The full application — routes, layout, and all pages */}
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
