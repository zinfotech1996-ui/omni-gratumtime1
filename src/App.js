import React from 'react';
import { BrowserRouter, Routes, Route, Navigate , HashRouter} from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { TimerProvider } from './contexts/TimerContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { Toaster } from './components/ui/sonner';
import { ProtectedRoute } from './components/ProtectedRoute';
import { DashboardLayout } from './components/DashboardLayout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { TimeTrackerPage } from './pages/TimeTrackerPage';
import { TimesheetsPage } from './pages/TimesheetsPage';
import { AdminApprovalsPage } from './pages/AdminApprovalsPage';
import { AdminTeamPage } from './pages/AdminTeamPage';
import { AdminProjectsPage } from './pages/AdminProjectsPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import './App.css';

function App() {
  return (
    <HashRouter>
      <ThemeProvider>
        <AuthProvider>
          <NotificationProvider>
            <TimerProvider>
              <div className="App">
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route
                    path="/"
                    element={
                      <ProtectedRoute>
                        <DashboardLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="dashboard" element={<DashboardPage />} />
                    <Route path="tracker" element={<TimeTrackerPage />} />
                    <Route path="timesheets" element={<TimesheetsPage />} />
                    <Route
                      path="admin/approvals"
                      element={
                        <ProtectedRoute requireAdmin>
                          <AdminApprovalsPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="admin/team"
                      element={
                        <ProtectedRoute requireAdmin>
                          <AdminTeamPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="admin/projects"
                      element={
                        <ProtectedRoute requireAdmin>
                          <AdminProjectsPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route path="reports" element={<ReportsPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                  </Route>
                </Routes>
                <Toaster position="top-right" />
              </div>
            </TimerProvider>
          </NotificationProvider>
        </AuthProvider>
      </ThemeProvider>
    </HashRouter>
  );
}

export default App;
