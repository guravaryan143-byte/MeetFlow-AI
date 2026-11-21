import { create } from 'zustand';

interface AuthState {
  token: string | null;
  user: { id: string; email: string; full_name: string; timezone: string } | null;
  organization: { id: string; name: string; slug: string } | null;
  role: string | null;
  setSession: (payload: {
    access_token: string;
    user: AuthState['user'];
    organization: AuthState['organization'];
    role: string;
  }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('meetflow_token'),
  user: JSON.parse(localStorage.getItem('meetflow_user') || 'null'),
  organization: JSON.parse(localStorage.getItem('meetflow_org') || 'null'),
  role: localStorage.getItem('meetflow_role'),
  setSession: ({ access_token, user, organization, role }) => {
    localStorage.setItem('meetflow_token', access_token);
    localStorage.setItem('meetflow_user', JSON.stringify(user));
    localStorage.setItem('meetflow_org', JSON.stringify(organization));
    localStorage.setItem('meetflow_role', role);
    set({ token: access_token, user, organization, role });
  },
  logout: () => {
    localStorage.removeItem('meetflow_token');
    localStorage.removeItem('meetflow_user');
    localStorage.removeItem('meetflow_org');
    localStorage.removeItem('meetflow_role');
    set({ token: null, user: null, organization: null, role: null });
  },
}));
