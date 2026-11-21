import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LandingPage } from './pages/LandingPage';
import { AuthPage } from './pages/AuthPage';
import { DashboardLayout } from './layouts/DashboardLayout';
import { useAuthStore } from './stores/authStore';

const queryClient = new QueryClient();
const OverviewPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).OverviewPage }));
const MeetingsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).MeetingsPage }));
const MeetingDetailsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).MeetingDetailsPage }));
const DecisionsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).DecisionsPage }));
const DecisionDnaPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).DecisionDnaPage }));
const ConflictReviewPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).ConflictReviewPage }));
const TasksPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).TasksPage }));
const RemindersPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).RemindersPage }));
const ApprovalInboxPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).ApprovalInboxPage }));
const CommitmentRadarPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).CommitmentRadarPage }));
const WeeklyDigestsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).WeeklyDigestsPage }));
const AnalyticsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).AnalyticsPage }));
const IntegrationsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).IntegrationsPage }));
const SettingsPage = lazy(async () => ({ default: (await import('./pages/DashboardPages')).SettingsPage }));

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/auth" replace />;
};

export const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <Suspense fallback={
        <div role="status" aria-busy="true" className="min-h-screen bg-[#09090B] p-6 text-sm text-zinc-400">
          Loading your workspace…
        </div>
      }>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/app/overview" replace />} />
            <Route path="overview" element={<OverviewPage />} />
            <Route path="meetings" element={<MeetingsPage />} />
            <Route path="meetings/:id" element={<MeetingDetailsPage />} />
            <Route path="decisions" element={<DecisionsPage />} />
            <Route path="decision-dna" element={<DecisionDnaPage />} />
            <Route path="conflicts" element={<ConflictReviewPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="reminders" element={<RemindersPage />} />
            <Route path="approvals" element={<ApprovalInboxPage />} />
            <Route path="radar" element={<CommitmentRadarPage />} />
            <Route path="digests" element={<WeeklyDigestsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="integrations" element={<IntegrationsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  </QueryClientProvider>
);

export default App;
