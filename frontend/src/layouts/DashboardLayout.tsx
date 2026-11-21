import React, { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  CheckSquare,
  Dna,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  Mail,
  Plug,
  Radar,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAuthStore } from '../stores/authStore';

const NAV_ITEMS = [
  { to: '/app/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/app/meetings', label: 'Meetings', icon: FileText },
  { to: '/app/decisions', label: 'Decisions', icon: Activity },
  { to: '/app/conflicts', label: 'Conflict Review', icon: AlertTriangle },
  { to: '/app/tasks', label: 'Action Items', icon: CheckSquare },
  { to: '/app/reminders', label: 'Reminders', icon: Bell },
  { to: '/app/approvals', label: 'Approval Inbox', icon: Inbox },
  { to: '/app/decision-dna', label: 'Decision DNA', icon: Dna },
  { to: '/app/radar', label: 'Commitment Radar', icon: Radar },
  { to: '/app/digests', label: 'Weekly Digests', icon: Mail },
  { to: '/app/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/app/integrations', label: 'Integrations', icon: Plug },
  { to: '/app/settings', label: 'Settings', icon: Settings },
];

export const DashboardLayout: React.FC = () => {
  const { user, organization, role, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const activeItem = NAV_ITEMS.find(({ to }) =>
    to === '/app/meetings'
      ? location.pathname === to || location.pathname.startsWith(`${to}/`)
      : location.pathname === to,
  );
  const displayName = user?.full_name?.trim() || user?.email || 'Workspace member';
  const initials = displayName
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100 lg:flex">
      {mobileNavOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
        />
      )}
      <aside
        id="primary-navigation"
        className={`fixed inset-y-0 left-0 z-50 flex w-[min(86vw,18rem)] shrink-0 flex-col border-r border-white/[0.07] bg-[#0D0D10] p-4 shadow-2xl transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:translate-x-0 lg:shadow-none ${
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between px-2 py-3">
            <Link to="/app/overview" className="flex items-center gap-2 text-base font-semibold tracking-tight text-white">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
              </span>
              MeetFlow <span className="font-playfair italic font-normal text-zinc-400">AI</span>
            </Link>
            <button
              type="button"
              aria-label="Close navigation"
              onClick={() => setMobileNavOpen(false)}
              className="rounded-lg p-2 text-zinc-400 transition hover:bg-white/[0.06] hover:text-white lg:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-5 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <p className="truncate text-xs font-medium text-zinc-200">{organization?.name || 'Workspace'}</p>
            <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-zinc-500">{role || 'MEMBER'} workspace</p>
          </div>
          <nav aria-label="Main navigation" className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to !== '/app/meetings'}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors duration-150 ${
                    isActive
                      ? 'bg-emerald-400/[0.09] font-medium text-emerald-200 ring-1 ring-inset ring-emerald-300/[0.13]'
                      : 'text-zinc-400 hover:bg-white/[0.045] hover:text-zinc-100'
                  }`
                }
              >
                <item.icon className="h-4 w-4 shrink-0 transition-colors group-hover:text-emerald-300" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-4 border-t border-white/[0.07] pt-4">
            <div className="flex min-w-0 items-center gap-3 px-1">
              <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[11px] font-semibold text-zinc-200">
                {initials}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-zinc-200">{displayName}</p>
                <p className="truncate text-[11px] text-zinc-500">{user?.email}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                logout();
                navigate('/auth');
              }}
              className="mt-3 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-zinc-400 transition hover:bg-rose-400/[0.08] hover:text-rose-200"
            >
              <LogOut className="h-3.5 w-3.5" /> Sign Out
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#09090B]/90 px-4 py-3 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                aria-label="Open navigation"
                aria-controls="primary-navigation"
                aria-expanded={mobileNavOpen}
                onClick={() => setMobileNavOpen(true)}
                className="rounded-lg border border-white/[0.08] p-2 text-zinc-300 transition hover:bg-white/[0.06] hover:text-white lg:hidden"
              >
                <Menu className="h-4 w-4" />
              </button>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-white">{activeItem?.label || 'MeetFlow AI'}</p>
                <p className="hidden truncate text-[11px] text-zinc-500 sm:block">
                  {organization?.name || 'Your workspace'} · Decision intelligence
                </p>
              </div>
            </div>
            <Link
              to="/app/meetings"
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-zinc-950 shadow-sm transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#09090B] sm:px-4"
            >
              <FileText className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">New meeting</span>
              <span className="sm:hidden">New</span>
            </Link>
          </div>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
