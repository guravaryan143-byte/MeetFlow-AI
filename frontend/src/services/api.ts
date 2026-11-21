const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface ReminderScheduleInput {
  action_item_id: string;
  scheduled_for?: string;
  reminder_type?: 'UPCOMING' | 'OVERDUE' | 'ESCALATION';
  timezone?: string;
  target_provider?: 'email' | 'slack';
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('meetflow_token');
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Auth
  register: (body: Record<string, unknown>) =>
    request('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: { email: string; password: string }) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request('/api/auth/me'),

  // Meetings & Transcripts
  listMeetings: () => request<{ meetings: any[] }>('/api/meetings'),
  getMeeting: (id: string) => request<any>(`/api/meetings/${id}`),
  createMeeting: (body: { title: string; meeting_date?: string; transcript_text?: string; participants?: string[] }) =>
    request('/api/meetings', { method: 'POST', body: JSON.stringify(body) }),
  uploadMeetingFile: (formData: FormData) =>
    request('/api/meetings/upload', { method: 'POST', body: formData }),
  processMeeting: (id: string) =>
    request(`/api/meetings/${id}/process`, { method: 'POST' }),
  getTranscript: (meetingId: string) =>
    request<any>(`/api/meetings/${meetingId}/transcript`),
  correctSpeaker: (transcriptId: string, segmentId: string, speaker_label: string) =>
    request(`/api/transcripts/${transcriptId}/segments/${segmentId}`, {
      method: 'PATCH',
      body: JSON.stringify({ speaker_label }),
    }),

  // Decisions & Conflicts
  listDecisions: () => request<{ decisions: any[] }>('/api/decisions'),
  getDecision: (id: string) => request<any>(`/api/decisions/${id}`),
  listConflicts: () => request<{ conflicts: any[] }>('/api/decisions/conflicts'),
  confirmDecision: (id: string, body: { conflict_id?: string; resolution_action: string; change_reason?: string }) =>
    request(`/api/decisions/${id}/confirm`, { method: 'POST', body: JSON.stringify(body) }),

  // Tasks
  listTasks: () => request<{ tasks: any[] }>('/api/tasks'),
  createTask: (body: Record<string, unknown>) =>
    request('/api/tasks', { method: 'POST', body: JSON.stringify(body) }),
  updateTask: (id: string, body: Record<string, unknown>) =>
    request(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTask: (id: string) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
  prepareTaskSync: (id: string, provider: 'linear' | 'trello') =>
    request(`/api/tasks/${id}/prepare-sync`, { method: 'POST', body: JSON.stringify({ provider }) }),

  // Memory
  searchMemory: (query: string) =>
    request<{ results: any[] }>('/api/memory/search', { method: 'POST', body: JSON.stringify({ query }) }),
  getMemoryHistory: () => request<{ history: any[] }>('/api/memory/history'),

  // Approvals (Central Human Approval Gate)
  listApprovals: (status?: string) =>
    request<{ approvals: any[] }>(`/api/approvals${status ? `?status=${status}` : ''}`),
  approveAction: (id: string, comment?: string) =>
    request(`/api/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ comment }) }),
  rejectAction: (id: string, comment?: string) =>
    request(`/api/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ comment }) }),
  executeAction: (id: string) =>
    request(`/api/approvals/${id}/execute`, { method: 'POST' }),

  // Integrations
  listIntegrations: () => request<{ integrations: any[]; mode: 'mock' | 'live'; simulated: boolean }>('/api/integrations'),
  connectIntegration: (provider: string, body: { workspace_name: string; project_id?: string; config?: Record<string, unknown> }) =>
    request(`/api/integrations/${provider}/connect`, { method: 'POST', body: JSON.stringify(body) }),

  // Reminders & Digests
  listReminders: () => request<{ reminders: any[] }>('/api/reminders'),
  scheduleReminder: (input: ReminderScheduleInput | string) =>
    request('/api/reminders/schedule', {
      method: 'POST',
      body: JSON.stringify(typeof input === 'string' ? { action_item_id: input } : input),
    }),
  listDigests: () => request<{ digests: any[] }>('/api/digests'),
  generateDigest: (body: Record<string, unknown> = {}) =>
    request('/api/digests/generate', { method: 'POST', body: JSON.stringify(body) }),

  // Analytics
  getAnalyticsOverview: () => request<any>('/api/analytics/overview'),
  getCommitmentRadar: () => request<any>('/api/analytics/radar'),
  getAuditLogs: () => request<{ audit_logs: any[] }>('/api/analytics/audit-logs'),
};
