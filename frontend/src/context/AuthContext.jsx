/**
 * context/AuthContext.jsx — Global authentication state management.
 *
 * WHY A CONTEXT?
 *   Many components need to know: "Is a user logged in? What's their name?"
 *   Without context, we'd pass user data down as props through every level:
 *     App → Layout → Sidebar → UserInfo (props hell)
 *   With context, ANY component can access auth state with useAuth().
 *
 * WHAT IS REACT CONTEXT?
 *   Context is React's built-in state sharing mechanism. A Provider wraps
 *   the whole app and holds state. Children can read from it via useContext().
 *   When the shared state changes (e.g., user logs in), all consumers re-render.
 *
 * WHAT STATE IS MANAGED HERE:
 *   user    → the logged-in User object from the API (or null if not logged in)
 *   loading → true while we're checking if an existing token is still valid
 *
 * STARTUP FLOW:
 *   1. App mounts → AuthProvider runs → checks localStorage for a token
 *   2. If token found → calls authApi.me() to validate it and get user profile
 *   3. If token invalid/missing → user stays null → ProtectedRoute redirects to login
 *
 * USAGE IN COMPONENTS:
 *   const { user, login, logout } = useAuth();
 *   if (!user) return <LoginPage />;
 */

import React, { createContext, useContext, useState, useEffect } from "react";
import { authApi } from "../api/auth";

// Create the context object. null is the default value (only used if a component
// tries to access context OUTSIDE of an AuthProvider — our useAuth hook catches this).
const AuthContext = createContext(null);

/**
 * AuthProvider — wraps the entire app and provides auth state to all children.
 *
 * Place this at the top of the component tree (in main.jsx), wrapping everything else.
 */
export function AuthProvider({ children }) {
  // user: the authenticated User object, or null if not logged in
  const [user, setUser] = useState(null);

  // loading: true until we've finished checking the stored token.
  // WHY: Without this, the app flashes the dashboard for a split second before
  // redirecting to login (because user is null before the /me call resolves).
  const [loading, setLoading] = useState(true);

  // On first mount: check if there's a valid stored token and fetch the user profile
  useEffect(() => {
    const token = localStorage.getItem("access_token");

    if (token) {
      // A token exists — validate it by calling the /auth/me endpoint.
      // If valid: set the user state. If expired/invalid: clear the token.
      authApi
        .me()
        .then(setUser)   // Valid token → save user profile to state
        .catch(() => localStorage.removeItem("access_token"))  // Invalid → clear it
        .finally(() => setLoading(false));  // Done either way → stop showing spinner
    } else {
      // No token — user is definitely not logged in
      setLoading(false);
    }
  }, []); // Empty dependency array = run once on mount

  /**
   * login — Authenticate and store the user in state.
   *
   * FLOW:
   *   1. Call the login API → get { access_token }
   *   2. Store the token in localStorage (persists across page refreshes)
   *   3. Call /auth/me to get the full user profile
   *   4. Store the user in state → all components re-render with the new user
   *
   * WHY CALL /me AFTER LOGIN?
   *   The token response only contains the token string. To get the user's
   *   name, role, etc., we need a separate /me call.
   */
  const login = async (email, password) => {
    const { access_token } = await authApi.login(email, password);
    localStorage.setItem("access_token", access_token); // Persist across refreshes
    const me = await authApi.me(); // Fetch the full user profile
    setUser(me); // Update state → triggers re-render in all consumers
    return me;
  };

  /**
   * logout — Clear auth state and token.
   * The API client's response interceptor also calls localStorage.removeItem
   * on 401 responses, so this is the "intentional" logout path.
   */
  const logout = () => {
    authApi.logout(); // Removes token from localStorage
    setUser(null);    // Clears user from state → ProtectedRoute redirects to login
  };

  // Provide state and functions to all children via context
  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * useAuth — Custom hook to access auth context from any component.
 *
 * WHY A CUSTOM HOOK?
 *   Instead of: const ctx = useContext(AuthContext); if (!ctx) throw error;
 *   You just write: const { user, login } = useAuth();
 *   The error message makes debugging easier if used outside the provider.
 *
 * USAGE:
 *   function MyComponent() {
 *     const { user, logout } = useAuth();
 *     return <button onClick={logout}>Hello {user.full_name}</button>;
 *   }
 */
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // This error only fires in development if useAuth() is called outside AuthProvider
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
};
