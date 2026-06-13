/**
 * Root SPA component: wires the auth context and client-side routes.
 *
 * The router (BrowserRouter) is provided by `main.tsx` so tests can mount the
 * route table inside a MemoryRouter.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { NewRun } from "./pages/NewRun";
import { Results } from "./pages/Results";
import { RunDetail } from "./pages/RunDetail";

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/new"
          element={
            <ProtectedRoute>
              <NewRun />
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/:runId/results"
          element={
            <ProtectedRoute>
              <Results />
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/:runId"
          element={
            <ProtectedRoute>
              <RunDetail />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
