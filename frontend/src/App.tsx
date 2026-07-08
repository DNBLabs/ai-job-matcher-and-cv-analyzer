/**
 * Root SPA component: wires the auth context and client-side routes.
 *
 * The router (BrowserRouter) is provided by `main.tsx` so tests can mount the
 * route table inside a MemoryRouter.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { AdminRoute } from "./auth/AdminRoute";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/AppLayout";
import { Admin } from "./pages/Admin";
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
              <AppLayout>
                <Dashboard />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/new"
          element={
            <ProtectedRoute>
              <AppLayout>
                <NewRun />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/:runId/results"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Results />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/runs/:runId"
          element={
            <ProtectedRoute>
              <AppLayout>
                <RunDetail />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AppLayout>
                <Admin />
              </AppLayout>
            </AdminRoute>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
