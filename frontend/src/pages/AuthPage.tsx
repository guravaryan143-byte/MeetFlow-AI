import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import { useAuthStore } from '../stores/authStore';

export const AuthPage: React.FC = () => {
  const [params] = useSearchParams();
  const [isRegister, setIsRegister] = useState(params.get('mode') === 'register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res: any = isRegister
        ? await api.register({
            email,
            password,
            full_name: fullName,
            organization_name: orgName || `${fullName}'s Workspace`,
          })
        : await api.login({ email, password });
      setSession(res);
      navigate('/app/overview');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#09090B] px-4 text-zinc-100">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-[#111114] p-8">
        <h1 className="text-2xl font-medium text-white">
          {isRegister ? 'Create your MeetFlow workspace' : 'Sign in to MeetFlow AI'}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">Conversations into commitments.</p>

        {error && (
          <div role="alert" className="mt-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          {isRegister && (
            <>
              <div>
                <label htmlFor="full-name" className="block text-xs text-zinc-400">Full Name</label>
                <input
                  id="full-name"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="organization-name" className="block text-xs text-zinc-400">Organization Name</label>
                <input
                  id="organization-name"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </>
          )}
          <div>
            <label htmlFor="email" className="block text-xs text-zinc-400">Email</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs text-zinc-400">Password</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>
          <button
            disabled={loading}
            type="submit"
            className="w-full rounded-lg bg-white py-2.5 text-sm font-medium text-zinc-950 transition hover:bg-zinc-200 disabled:opacity-50"
          >
            {loading ? 'Working...' : isRegister ? 'Create Workspace' : 'Sign In'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => setIsRegister((v) => !v)}
          className="mt-5 w-full text-center text-xs text-zinc-400 hover:text-white"
        >
          {isRegister ? 'Already have an account? Sign in' : 'Need a workspace? Get started'}
        </button>
      </div>
    </div>
  );
};
