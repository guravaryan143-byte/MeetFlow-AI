import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowUpRight, Bell, CalendarDays, Clock3, Search, Users } from 'lucide-react';
import { api } from '../services/api';
import { useAuthStore } from '../stores/authStore';

const Card: React.FC<{ title?: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="rounded-2xl border border-white/[0.07] bg-gradient-to-br from-[#131316] to-[#0f0f12] p-4 shadow-[0_12px_40px_rgba(0,0,0,0.12)] transition-colors duration-200 hover:border-white/[0.11] sm:p-5">
    {title && <h2 className="mb-4 text-sm font-medium tracking-wide text-zinc-200">{title}</h2>}
    {children}
  </section>
);

const PageHeader: React.FC<{
  title: string;
  description?: string;
  eyebrow?: string;
  action?: React.ReactNode;
}> = ({ title, description, eyebrow, action }) => (
  <div className="flex flex-col gap-4 border-b border-white/[0.06] pb-5 sm:flex-row sm:items-end sm:justify-between">
    <div className="min-w-0">
      {eyebrow && <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-300/80">{eyebrow}</p>}
      <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]">{title}</h1>
      {description && <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-400">{description}</p>}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </div>
);

const fieldClass =
  'w-full rounded-xl border border-white/[0.09] bg-[#09090b]/80 px-3.5 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 transition focus:border-emerald-400/50 focus:bg-[#09090b] focus:outline-none';

const formatDate = (value?: string | null) => {
  if (!value) return 'Not set';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Not set';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
};

const StatusBadge: React.FC<{ value: string }> = ({ value }) => {
  const tone =
    value.includes('CONFIRMED') || value.includes('EXECUTED') || value.includes('COMPLETED') || value === 'CONNECTED'
      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
      : value.includes('REJECTED') || value.includes('FAILED') || value.includes('OPEN') || value === 'HIGH'
      ? 'border-rose-500/40 bg-rose-500/10 text-rose-300'
      : 'border-amber-500/40 bg-amber-500/10 text-amber-300';
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${tone}`}>
      {value}
    </span>
  );
};

const QueryFeedback: React.FC<{
  isLoading: boolean;
  error: Error | null;
  emptyMessage: string;
}> = ({ isLoading, error, emptyMessage }) => {
  if (isLoading) {
    return (
      <div role="status" aria-busy="true" className="space-y-3 py-2">
        <span className="sr-only">Loading data...</span>
        <div className="h-4 w-2/3 animate-pulse rounded bg-zinc-800/80" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-zinc-900" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-zinc-900" />
      </div>
    );
  }
  if (error) {
    return <p role="alert" className="text-sm text-rose-300">Could not load data. {error.message}</p>;
  }
  return <p className="text-sm text-zinc-500">{emptyMessage}</p>;
};

const MutationFeedback: React.FC<{ error?: Error | null; notice?: string }> = ({ error, notice }) => (
  <>
    {error && <p role="alert" className="text-sm text-rose-300">{error.message}</p>}
    {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
  </>
);

// 1. Overview
export const OverviewPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({ queryKey: ['analytics'], queryFn: api.getAnalyticsOverview });
  if (isLoading || error) {
    return <QueryFeedback isLoading={isLoading} error={error} emptyMessage="Workspace overview is unavailable." />;
  }

  const stats = [
    { label: 'Meetings Processed', value: data?.meetings_count ?? 0 },
    { label: 'Decisions Tracked', value: data?.decisions_count ?? 0 },
    { label: 'Open Conflicts', value: data?.open_conflicts_count ?? 0 },
    { label: 'Pending Approvals', value: data?.pending_approvals_count ?? 0 },
    { label: 'Accountability Score', value: `${data?.accountability_score?.score ?? 0}%` },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        eyebrow="Workspace pulse"
        description="A live view of decisions, follow-through, and items that need attention."
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map((s) => (
          <Card key={s.label}>
            <div className="text-xs font-medium text-zinc-400">{s.label}</div>
            <div className="mt-3 text-3xl font-semibold tracking-tight text-white">{s.value}</div>
          </Card>
        ))}
      </div>
      <Card title="Accountability Methodology">
        <p className="max-w-3xl text-sm leading-6 text-zinc-400">{data?.accountability_score?.methodology}</p>
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Completed', data?.tasks_summary?.completed ?? 0],
            ['Pending', data?.tasks_summary?.pending ?? 0],
            ['Overdue', data?.tasks_summary?.overdue ?? 0],
            ['Completion rate', `${data?.tasks_summary?.completion_rate_pct ?? 0}%`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-3">
              <p className="text-[11px] text-zinc-500">{label}</p>
              <p className="mt-1 text-lg font-semibold text-zinc-100">{value}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

// 2. Meetings (Create, Upload & Process)
export const MeetingsPage: React.FC = () => {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['meetings'], queryFn: api.listMeetings });
  const [title, setTitle] = useState('');
  const [transcript, setTranscript] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [participantText, setParticipantText] = useState('');
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [notice, setNotice] = useState('');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [uploadKey, setUploadKey] = useState(0);

  const refreshMeetingData = () => {
    ['meetings', 'decisions', 'approvals', 'analytics', 'tasks', 'conflicts', 'radar', 'memory-history']
      .forEach((key) => qc.invalidateQueries({ queryKey: [key] }));
  };

  const createAndProcess = useMutation({
    mutationFn: async () => {
      const m: any = await api.createMeeting({
        title: title.trim(),
        meeting_date: meetingDate || undefined,
        transcript_text: transcript.trim(),
        participants: participantText.split(',').map((name) => name.trim()).filter(Boolean),
      });
      return api.processMeeting(m.id);
    },
    onSuccess: () => {
      setTitle('');
      setTranscript('');
      setMeetingDate('');
      setParticipantText('');
      setNotice('Meeting processed and saved.');
      refreshMeetingData();
    },
  });

  const uploadAndProcess = useMutation({
    mutationFn: async () => {
      if (!uploadFile) throw new Error('Choose a transcript file first.');
      const form = new FormData();
      form.append('title', uploadTitle);
      form.append('file', uploadFile);
      const meeting: any = await api.uploadMeetingFile(form);
      const result = await api.processMeeting(meeting.id);
      return result;
    },
    onSuccess: () => {
      setUploadTitle('');
      setUploadFile(null);
      setUploadKey((key) => key + 1);
      setNotice('Transcript uploaded and processed.');
      refreshMeetingData();
    },
  });

  const meetings = data?.meetings ?? [];
  const filteredMeetings = meetings.filter((meeting) => {
    const matchesText = `${meeting.title} ${meeting.summary || ''}`.toLowerCase().includes(searchText.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || meeting.status === statusFilter;
    return matchesText && matchesStatus;
  });
  const processedCount = meetings.filter((meeting) => meeting.status === 'PROCESSED' || meeting.status === 'COMPLETED').length;
  const needsReviewCount = meetings.filter((meeting) => meeting.status === 'NEEDS_REVIEW' || meeting.status === 'FAILED').length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Meetings"
        eyebrow="Transcript intelligence"
        description="Capture a conversation, preserve its evidence, and turn it into decisions and accountable work."
      />
      {notice && <p role="status" className="rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] px-4 py-3 text-sm text-emerald-200">{notice}</p>}
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ['Meetings', meetings.length, 'All records in this workspace'],
          ['Processed', processedCount, 'Ready for review and follow-through'],
          ['Needs attention', needsReviewCount, 'Failed or review-needed records'],
        ].map(([label, value, note]) => (
          <Card key={label}>
            <p className="text-xs font-medium text-zinc-500">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
            <p className="mt-1 text-[11px] text-zinc-600">{note}</p>
          </Card>
        ))}
      </div>
      <Card title="Create from transcript">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setNotice('');
            createAndProcess.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5 text-xs text-zinc-400">
              Meeting title
          <input
            required
            aria-label="Meeting title"
            placeholder="Meeting title (e.g., Q4 Product Launch Sync)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
                className={fieldClass}
          />
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              Meeting date
              <input
                type="date"
                value={meetingDate}
                onChange={(event) => setMeetingDate(event.target.value)}
                className={fieldClass}
              />
            </label>
          </div>
          <label className="block space-y-1.5 text-xs text-zinc-400">
            Participants <span className="text-zinc-600">· separate names with commas</span>
            <input
              value={participantText}
              onChange={(event) => setParticipantText(event.target.value)}
              className={fieldClass}
              placeholder="Maya Chen, Jordan Lee"
            />
          </label>
          <label className="block space-y-1.5 text-xs text-zinc-400">
            Transcript
          <textarea
            required
            rows={4}
            placeholder="[00:00:10] Maya Lin: The product launch date is confirmed as December 10."
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
                className={`${fieldClass} min-h-32 resize-y leading-6`}
          />
          </label>
          <button
            type="submit"
            disabled={!title.trim() || !transcript.trim() || createAndProcess.isPending}
            className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createAndProcess.isPending ? 'Processing transcript…' : 'Process meeting'}
            {!createAndProcess.isPending && <ArrowUpRight className="h-4 w-4" />}
          </button>
          <MutationFeedback error={createAndProcess.error} />
        </form>
      </Card>

      <Card title="Upload transcript file">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1 space-y-1.5 text-xs text-zinc-400">
            Meeting title
            <input
              aria-label="Uploaded meeting title"
              required
              placeholder="Meeting title"
              value={uploadTitle}
              onChange={(event) => setUploadTitle(event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="min-w-0 flex-1 space-y-1.5 text-xs text-zinc-400">
            Transcript file <span className="text-zinc-600">· .txt, .md, .vtt, .srt, .json</span>
            <input
              aria-label="Transcript file"
              key={uploadKey}
              type="file"
              accept=".txt,.md,.vtt,.srt,.json"
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
              className="block w-full cursor-pointer rounded-xl border border-white/[0.08] bg-[#09090b]/70 p-2 text-xs text-zinc-400 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-xs file:font-medium file:text-zinc-100 hover:file:bg-zinc-700"
            />
          </label>
          <button
            type="button"
            disabled={!uploadTitle.trim() || !uploadFile || uploadAndProcess.isPending}
            onClick={() => uploadAndProcess.mutate()}
            className="rounded-xl border border-white/[0.1] px-4 py-2.5 text-sm font-medium text-zinc-100 transition hover:border-emerald-400/30 hover:bg-emerald-400/[0.05] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploadAndProcess.isPending ? 'Uploading and processing...' : 'Upload & Process'}
          </button>
        </div>
        {uploadAndProcess.isError && (
          <p role="alert" className="mt-3 text-sm text-rose-300">{uploadAndProcess.error.message}</p>
        )}
      </Card>

      <Card title="Meeting library">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search meetings</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search title or summary"
              className={`${fieldClass} pl-9`}
            />
          </label>
          <label className="sr-only" htmlFor="meeting-status-filter">Filter meetings by status</label>
          <select
            id="meeting-status-filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className={`${fieldClass} sm:w-52`}
          >
            <option value="ALL">All statuses</option>
            {[...new Set(meetings.map((meeting) => meeting.status))].filter(Boolean).map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </div>
        {isLoading || error || !meetings.length ? (
          <QueryFeedback
            isLoading={isLoading}
            error={error}
            emptyMessage="No meetings recorded yet. Process a transcript above to start your workspace memory."
          />
        ) : !filteredMeetings.length ? (
          <p className="rounded-xl border border-dashed border-white/[0.1] px-4 py-8 text-center text-sm text-zinc-500">
            No meetings match the current search and status filter.
          </p>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {filteredMeetings.map((m) => (
              <div key={m.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <Link to={`/app/meetings/${m.id}`} className="group inline-flex items-center gap-2 text-sm font-medium text-white transition hover:text-emerald-300">
                    <span className="truncate">{m.title}</span>
                    <ArrowUpRight className="h-3.5 w-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" />
                  </Link>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500">{m.summary || 'Transcript saved · processing summary unavailable'}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-zinc-600">
                    {m.meeting_date && <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" />{formatDate(m.meeting_date)}</span>}
                    {Array.isArray(m.participants) && m.participants.length > 0 && <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{m.participants.length} participants</span>}
                  </div>
                </div>
                <StatusBadge value={m.status} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

// 3. Meeting Details & Speaker Correction
export const MeetingDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { data: meeting, isLoading: meetingLoading, error: meetingError } = useQuery({
    queryKey: ['meeting', id],
    queryFn: () => api.getMeeting(id!),
    enabled: !!id,
  });
  const { data: transcript, isLoading: transcriptLoading, error: transcriptError } = useQuery({
    queryKey: ['transcript', id],
    queryFn: () => api.getTranscript(id!),
    enabled: !!id,
  });
  const [editingSeg, setEditingSeg] = useState<string | null>(null);
  const [speakerInput, setSpeakerInput] = useState('');

  const fixSpeaker = useMutation({
    mutationFn: ({ tid, sid, label }: { tid: string; sid: string; label: string }) =>
      api.correctSpeaker(tid, sid, label),
    onSuccess: () => {
      setEditingSeg(null);
      qc.invalidateQueries({ queryKey: ['transcript', id] });
    },
  });

  if (!meeting) {
    return <QueryFeedback isLoading={meetingLoading} error={meetingError} emptyMessage="Meeting not found." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={meeting.title}
        eyebrow="Meeting record"
        description={meeting.summary || 'Transcript record and extracted intelligence.'}
        action={
          <div className="flex items-center gap-3">
            <Link to="/app/meetings" className="text-xs font-medium text-zinc-400 transition hover:text-white">All meetings</Link>
            <StatusBadge value={meeting.status} />
          </div>
        }
      />
      <div className="flex flex-wrap gap-2">
        {meeting.meeting_date && (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-xs text-zinc-400">
            <CalendarDays className="h-3.5 w-3.5 text-emerald-300" />{formatDate(meeting.meeting_date)}
          </span>
        )}
        {Array.isArray(meeting.participants) && meeting.participants.map((participant: string) => (
          <span key={participant} className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-xs text-zinc-400">
            <Users className="h-3.5 w-3.5 text-zinc-500" />{participant}
          </span>
        ))}
      </div>

      <Card title="Transcript intelligence">
        <p className="mb-4 text-xs leading-5 text-zinc-500">
          Review the original transcript evidence and correct speaker labels where attribution needs attention.
        </p>
        <div className="space-y-3">
          {transcriptLoading || transcriptError || !transcript?.segments?.length ? (
            <QueryFeedback
              isLoading={transcriptLoading}
              error={transcriptError}
              emptyMessage="No transcript segments are available."
            />
          ) : transcript.segments.map((seg: any) => (
            <article key={seg.id} className="rounded-xl border border-white/[0.06] bg-black/20 p-4 text-sm">
              <div className="flex flex-col gap-2 text-xs text-zinc-500 sm:flex-row sm:items-center sm:justify-between">
                <span className="font-semibold text-emerald-300">{seg.speaker_label || 'Unknown speaker'}</span>
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />{seg.start_time}s – {seg.end_time}s</span>
                  <button
                    type="button"
                    disabled={fixSpeaker.isPending}
                    onClick={() => {
                      setEditingSeg(seg.id);
                      setSpeakerInput(seg.speaker_label);
                    }}
                    className="rounded-md px-2 py-1 text-zinc-300 underline decoration-zinc-700 underline-offset-4 transition hover:bg-white/[0.05] hover:text-white"
                  >
                    Correct Speaker
                  </button>
                </div>
              </div>
              <p className="mt-1.5 text-zinc-200">{seg.text}</p>
              {editingSeg === seg.id && (
                <div className="mt-2 flex gap-2">
                  <input
                    value={speakerInput}
                    onChange={(e) => setSpeakerInput(e.target.value)}
                    aria-label="Corrected speaker name"
                    className={`${fieldClass} max-w-xs`}
                  />
                  <button
                    type="button"
                    disabled={fixSpeaker.isPending || !speakerInput.trim()}
                    onClick={() =>
                      fixSpeaker.mutate({ tid: transcript.transcript.id, sid: seg.id, label: speakerInput })
                    }
                    className="rounded-lg bg-emerald-400 px-3 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:opacity-50"
                  >
                    Save
                  </button>
                </div>
              )}
            </article>
          ))}
          <MutationFeedback
            error={fixSpeaker.error}
            notice={fixSpeaker.isSuccess ? 'Speaker correction saved.' : undefined}
          />
        </div>
      </Card>
    </div>
  );
};

// 4. Decisions
export const DecisionsPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({ queryKey: ['decisions'], queryFn: api.listDecisions });
  const [searchText, setSearchText] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const decisions = data?.decisions ?? [];
  const filteredDecisions = decisions.filter((decision) => {
    const text = `${decision.subject} ${decision.statement} ${decision.meeting_title || ''}`.toLowerCase();
    return text.includes(searchText.toLowerCase()) && (typeFilter === 'ALL' || decision.decision_type === typeFilter);
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Decisions"
        eyebrow="Decision record"
        description="Confirmed commitments and proposals, with their source meeting and evidence kept alongside."
      />
      <Card title="Decision ledger">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search decisions</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Search decision, statement, or meeting" className={`${fieldClass} pl-9`} />
          </label>
          <label className="sr-only" htmlFor="decision-type-filter">Filter decisions by type</label>
          <select id="decision-type-filter" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className={`${fieldClass} sm:w-52`}>
            <option value="ALL">All decision types</option>
            {[...new Set(decisions.map((decision) => decision.decision_type))].filter(Boolean).map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </div>
        {isLoading || error || !decisions.length ? (
          <QueryFeedback isLoading={isLoading} error={error} emptyMessage="Decisions will appear as meetings are processed." />
        ) : !filteredDecisions.length ? (
          <p className="py-8 text-center text-sm text-zinc-500">No decisions match these filters.</p>
        ) : (
          <div className="space-y-3">
            {filteredDecisions.map((d) => (
              <article key={d.id} className="rounded-xl border border-white/[0.06] bg-black/20 p-4 transition-colors hover:border-white/[0.1] sm:p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-[11px] uppercase tracking-wide text-zinc-500">{d.subject}</p>
                    <p className="mt-1.5 text-sm font-medium leading-6 text-zinc-100">{d.statement}</p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <StatusBadge value={d.decision_type} />
                    <StatusBadge value={d.status} />
                  </div>
                </div>
                {d.evidence_quote && (
                  <blockquote className="mt-4 border-l-2 border-emerald-400/40 pl-3 text-xs italic leading-5 text-zinc-400">
                    “{d.evidence_quote}”
                  </blockquote>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/[0.05] pt-3 text-[11px] text-zinc-500">
                  {d.meeting_id ? <Link to={`/app/meetings/${d.meeting_id}`} className="transition hover:text-emerald-300">{d.meeting_title || 'Source meeting'} ↗</Link> : <span>{d.meeting_title || 'Source meeting'}</span>}
                  {d.meeting_date && <span>{formatDate(d.meeting_date)}</span>}
                  <span>Version {d.current_version}</span>
                  {d.key_value && <span>Value · {d.key_value}</span>}
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

// 5. Decision DNA (Chronological Version History)
export const DecisionDnaPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({ queryKey: ['memory-history'], queryFn: api.getMemoryHistory });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Decision DNA"
        eyebrow="Durable team memory"
        description="A chronological audit trail of decision changes across meetings. Historical versions are preserved rather than overwritten."
      />
      <div className="space-y-3">
        {data?.history?.length ? data.history.map((v) => (
          <Card key={v.id}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <span className="text-sm font-medium text-white">{v.subject} <span className="text-zinc-500">· v{v.version_number}</span></span>
              <StatusBadge value={v.status} />
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-300">{v.statement}</p>
            {v.evidence_quote && <blockquote className="mt-3 border-l-2 border-zinc-700 pl-3 text-xs italic leading-5 text-zinc-500">“{v.evidence_quote}”</blockquote>}
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 border-t border-white/[0.05] pt-3 text-[11px] text-zinc-500">
              <span>{v.meeting_title || 'Source meeting'}</span>
              <span>{v.change_reason || 'Version recorded'}</span>
              {v.created_at && <span>{formatDate(v.created_at)}</span>}
            </div>
          </Card>
        )) : <QueryFeedback isLoading={isLoading} error={error} emptyMessage="Decision history will appear here." />}
      </div>
    </div>
  );
};

// 6. Conflict Review
export const ConflictReviewPage: React.FC = () => {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['conflicts'], queryFn: api.listConflicts });
  const resolve = useMutation({
    mutationFn: ({ decisionId, conflictId, action }: { decisionId: string; conflictId: string; action: string }) =>
      api.confirmDecision(decisionId, { conflict_id: conflictId, resolution_action: action }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conflicts'] });
      qc.invalidateQueries({ queryKey: ['decisions'] });
      qc.invalidateQueries({ queryKey: ['memory-history'] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Conflict review"
        eyebrow="Cross-meeting memory"
        description="Compare new proposals with the evidence and decisions already recorded. Your resolution is appended to decision history."
      />
      <MutationFeedback
        error={resolve.error}
        notice={resolve.isSuccess ? 'Conflict resolution saved.' : undefined}
      />
      {isLoading || error || !data?.conflicts?.length ? (
        <Card>
          <QueryFeedback isLoading={isLoading} error={error} emptyMessage="No cross-meeting conflicts need review." />
        </Card>
      ) : (
        <div className="space-y-4">
          {data.conflicts.map((c) => (
            <Card key={c.id}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{c.conflict_type} · {c.severity} priority</p>
                  <h2 className="mt-1 text-base font-semibold text-white">{c.existing_subject}</h2>
                </div>
                <StatusBadge value={c.status} />
              </div>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-zinc-300">{c.explanation}</p>
              {c.suggested_resolution && (
                <p className="mt-3 rounded-lg border border-amber-400/10 bg-amber-400/[0.035] px-3 py-2 text-xs leading-5 text-amber-100/80">
                  Suggested review: {c.suggested_resolution}
                </p>
              )}
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/[0.07] bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-zinc-500">
                    <span>Previously recorded</span>
                    <span className="truncate">{c.existing_meeting_title}</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-zinc-200">{c.existing_evidence}</p>
                  {c.existing_value && <p className="mt-2 text-xs text-zinc-500">Recorded value · {c.existing_value}</p>}
                  {c.existing_meeting_id && <Link to={`/app/meetings/${c.existing_meeting_id}`} className="mt-3 inline-flex text-xs text-emerald-300 hover:text-emerald-200">Open source meeting ↗</Link>}
                </div>
                <div className="rounded-xl border border-amber-300/15 bg-amber-300/[0.025] p-4">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-amber-100/60">
                    <span>New proposal or discussion · not yet confirmed</span>
                    <span className="truncate">{c.new_meeting_title}</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-zinc-200">{c.new_evidence}</p>
                  {c.new_value && <p className="mt-2 text-xs text-zinc-500">Proposed value · {c.new_value}</p>}
                  {c.new_meeting_id && <Link to={`/app/meetings/${c.new_meeting_id}`} className="mt-3 inline-flex text-xs text-emerald-300 hover:text-emerald-200">Open source meeting ↗</Link>}
                </div>
              </div>
              {c.status === 'OPEN' ? (
                <div className="mt-5 flex flex-col gap-2 border-t border-white/[0.06] pt-4 sm:flex-row sm:items-center">
                  <span className="mr-auto text-xs text-zinc-500">Choose which commitment becomes current; historical evidence stays in Decision DNA.</span>
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate({ decisionId: c.new_decision_id, conflictId: c.id, action: 'ADOPT_NEW' })}
                    className="rounded-xl bg-emerald-400 px-3.5 py-2.5 text-xs font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:opacity-50"
                  >
                    Confirm New Decision (Supersede Old)
                  </button>
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate({ decisionId: c.existing_decision_id, conflictId: c.id, action: 'KEEP_EXISTING' })}
                    className="rounded-xl border border-white/[0.1] px-3.5 py-2.5 text-xs font-medium text-zinc-200 transition hover:bg-white/[0.05] disabled:opacity-50"
                  >
                    Keep Existing Decision
                  </button>
                </div>
              ) : (
                <p className="mt-4 border-t border-white/[0.06] pt-3 text-xs text-zinc-500">This conflict has been resolved. Review the evidence above or open Decision DNA to inspect the preserved history.</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

// 7. Action Items
export const TasksPage: React.FC = () => {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['tasks'], queryFn: api.listTasks });
  const [notice, setNotice] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [assignedName, setAssignedName] = useState('');
  const [deadline, setDeadline] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [syncProvider, setSyncProvider] = useState<'linear' | 'trello'>('linear');
  const user = useAuthStore((state) => state.user);

  const refreshTasks = () => {
    ['tasks', 'analytics', 'radar'].forEach((key) => qc.invalidateQueries({ queryKey: [key] }));
  };
  const createTask = useMutation({
    mutationFn: () => api.createTask({
      title: title.trim(),
      description: description.trim() || undefined,
      assigned_name: assignedName.trim() || undefined,
      deadline: deadline || undefined,
      priority,
    }),
    onSuccess: () => {
      setTitle('');
      setDescription('');
      setAssignedName('');
      setDeadline('');
      setPriority('MEDIUM');
      setNotice('Action item saved to this workspace.');
      refreshTasks();
    },
  });
  const syncPrep = useMutation({
    mutationFn: ({ id, provider }: { id: string; provider: 'linear' | 'trello' }) => api.prepareTaskSync(id, provider),
    onSuccess: () => {
      setNotice('External sync is ready for human review in the Approval Inbox.');
      qc.invalidateQueries({ queryKey: ['approvals'] });
    },
  });
  const reminder = useMutation({
    mutationFn: (task: any) => api.scheduleReminder({
      action_item_id: task.id,
      reminder_type: 'UPCOMING',
      timezone: user?.timezone || 'UTC',
      target_provider: 'email',
    }),
    onSuccess: () => {
      setNotice('Reminder prepared and sent to the Approval Inbox for review.');
      qc.invalidateQueries({ queryKey: ['reminders'] });
      qc.invalidateQueries({ queryKey: ['approvals'] });
    },
  });
  const markDone = useMutation({
    mutationFn: (id: string) => api.updateTask(id, { status: 'COMPLETED' }),
    onSuccess: () => {
      setNotice('Task marked completed.');
      refreshTasks();
    },
  });

  const tasks = data?.tasks ?? [];
  const filteredTasks = tasks.filter((task) => {
    const text = `${task.title} ${task.description || ''} ${task.assigned_name || ''}`.toLowerCase();
    return text.includes(searchText.toLowerCase()) && (statusFilter === 'ALL' || task.status === statusFilter);
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Action items"
        eyebrow="Commitment tracking"
        description="Keep ownership and deadlines visible. External task sync and reminders are always routed through human approval."
      />
      <MutationFeedback error={createTask.error || markDone.error || syncPrep.error || reminder.error} notice={notice} />
      <Card title="Add an action item">
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            setNotice('');
            createTask.mutate();
          }}
        >
          <label className="space-y-1.5 text-xs text-zinc-400 md:col-span-2">
            Task
            <input required minLength={2} value={title} onChange={(event) => setTitle(event.target.value)} className={fieldClass} placeholder="What needs to be done?" />
          </label>
          <label className="space-y-1.5 text-xs text-zinc-400 md:col-span-2">
            Description <span className="text-zinc-600">· optional</span>
            <textarea rows={2} value={description} onChange={(event) => setDescription(event.target.value)} className={fieldClass} placeholder="Add context or acceptance criteria" />
          </label>
          <label className="space-y-1.5 text-xs text-zinc-400">
            Owner <span className="text-zinc-600">· optional</span>
            <input value={assignedName} onChange={(event) => setAssignedName(event.target.value)} className={fieldClass} placeholder="Unassigned" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5 text-xs text-zinc-400">
              Due date
              <input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} className={fieldClass} />
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              Priority
              <select value={priority} onChange={(event) => setPriority(event.target.value)} className={fieldClass}>
                {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </div>
          <div className="flex items-end md:col-span-2">
            <button type="submit" disabled={!title.trim() || createTask.isPending} className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">
              {createTask.isPending ? 'Saving…' : 'Save action item'}
            </button>
          </div>
        </form>
      </Card>
      <Card title="Task board">
        <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto]">
          <label className="relative">
            <span className="sr-only">Search action items</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Search title, description, or owner" className={`${fieldClass} pl-9`} />
          </label>
          <label className="sr-only" htmlFor="task-status-filter">Filter tasks by status</label>
          <select id="task-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className={`${fieldClass} sm:w-48`}>
            <option value="ALL">All statuses</option>
            {[...new Set(tasks.map((task) => task.status))].filter(Boolean).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </div>
        {isLoading || error || !tasks.length ? (
          <QueryFeedback isLoading={isLoading} error={error} emptyMessage="No action items yet. Process a transcript or create an item above." />
        ) : !filteredTasks.length ? (
          <p className="py-8 text-center text-sm text-zinc-500">No action items match the current filters.</p>
        ) : (
          <div className="space-y-3">
            {filteredTasks.map((t) => (
              <article key={t.id} className="rounded-xl border border-white/[0.06] bg-black/20 p-4 transition-colors hover:border-white/[0.1]">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium text-white">{t.title}</h2>
                    {t.description && <p className="mt-1.5 text-xs leading-5 text-zinc-400">{t.description}</p>}
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-zinc-500">
                      <span className={t.assigned_name ? '' : 'text-amber-300'}>Owner · {t.assigned_name || 'Unassigned — review needed'}</span>
                      <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" />Due · {formatDate(t.deadline)}</span>
                      {t.meeting_id && <Link to={`/app/meetings/${t.meeting_id}`} className="transition hover:text-emerald-300">Source meeting ↗</Link>}
                    </div>
                    {t.evidence_quote && <p className="mt-3 border-l-2 border-zinc-700 pl-3 text-xs italic leading-5 text-zinc-500">“{t.evidence_quote}”</p>}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <StatusBadge value={t.priority} />
                    <StatusBadge value={t.status} />
                    {t.sync_status && <StatusBadge value={t.sync_status} />}
                  </div>
                </div>
                <div className="mt-4 flex flex-col gap-3 border-t border-white/[0.05] pt-3 sm:flex-row sm:items-center">
                  <div className="flex flex-wrap gap-2">
                    {t.status !== 'COMPLETED' && (
                      <button type="button" disabled={markDone.isPending} onClick={() => markDone.mutate(t.id)} className="rounded-lg border border-white/[0.09] px-3 py-2 text-xs text-zinc-300 transition hover:bg-white/[0.05] disabled:opacity-50">
                        Mark completed
                      </button>
                    )}
                    {t.status !== 'COMPLETED' && t.status !== 'CANCELLED' && (
                      <button type="button" disabled={reminder.isPending} onClick={() => reminder.mutate(t)} className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/15 px-3 py-2 text-xs text-amber-100/80 transition hover:bg-amber-300/[0.06] disabled:opacity-50">
                        <Bell className="h-3.5 w-3.5" /> Prepare reminder
                      </button>
                    )}
                  </div>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    <label className="sr-only" htmlFor={`sync-provider-${t.id}`}>External task provider for {t.title}</label>
                    <select id={`sync-provider-${t.id}`} value={syncProvider} onChange={(event) => setSyncProvider(event.target.value as 'linear' | 'trello')} className="rounded-lg border border-white/[0.08] bg-[#09090b] px-2.5 py-2 text-xs text-zinc-300">
                      <option value="linear">Linear</option>
                      <option value="trello">Trello</option>
                    </select>
                    <button type="button" disabled={syncPrep.isPending} onClick={() => syncPrep.mutate({ id: t.id, provider: syncProvider })} className="rounded-lg border border-emerald-400/20 px-3 py-2 text-xs font-medium text-emerald-200 transition hover:bg-emerald-400/[0.06] disabled:opacity-50">
                      Prepare sync · approval required
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

export const RemindersPage: React.FC = () => {
  const qc = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const { data: remindersData, isLoading: remindersLoading, error: remindersError } = useQuery({
    queryKey: ['reminders'],
    queryFn: api.listReminders,
  });
  const { data: tasksData, isLoading: tasksLoading, error: tasksError } = useQuery({
    queryKey: ['tasks'],
    queryFn: api.listTasks,
  });
  const [actionItemId, setActionItemId] = useState('');
  const [reminderType, setReminderType] = useState<'UPCOMING' | 'OVERDUE' | 'ESCALATION'>('UPCOMING');
  const [targetProvider, setTargetProvider] = useState<'email' | 'slack'>('email');
  const [scheduledAt, setScheduledAt] = useState('');
  const [notice, setNotice] = useState('');
  const schedule = useMutation({
    mutationFn: () => api.scheduleReminder({
      action_item_id: actionItemId,
      scheduled_for: scheduledAt || undefined,
      reminder_type: reminderType,
      timezone: user?.timezone || 'UTC',
      target_provider: targetProvider,
    }),
    onSuccess: () => {
      setActionItemId('');
      setScheduledAt('');
      setNotice('Reminder prepared. Review it in the Approval Inbox before it can be sent.');
      qc.invalidateQueries({ queryKey: ['reminders'] });
      qc.invalidateQueries({ queryKey: ['approvals'] });
    },
  });
  const tasks = tasksData?.tasks ?? [];
  const reminders = remindersData?.reminders ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reminders"
        eyebrow="Human-controlled follow-through"
        description="Prepare deadline reminders from real action items. Sending always requires an explicit approval."
        action={<Link to="/app/approvals" className="inline-flex items-center gap-2 rounded-lg border border-white/[0.1] px-3 py-2 text-xs font-medium text-zinc-200 transition hover:bg-white/[0.05]">Approval Inbox <ArrowUpRight className="h-3.5 w-3.5" /></Link>}
      />
      {notice && <p role="status" className="rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] px-4 py-3 text-sm text-emerald-200">{notice}</p>}
      <MutationFeedback error={schedule.error} />
      <Card title="Prepare a reminder">
        {tasksError ? (
          <p role="alert" className="text-sm text-rose-300">Could not load action items. {tasksError.message}</p>
        ) : (
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              setNotice('');
              schedule.mutate();
            }}
          >
            <label className="space-y-1.5 text-xs text-zinc-400 md:col-span-2">
              Action item
              <select required value={actionItemId} onChange={(event) => setActionItemId(event.target.value)} className={fieldClass}>
                <option value="">{tasksLoading ? 'Loading action items…' : 'Choose a task'}</option>
                {tasks.filter((task) => task.status !== 'COMPLETED' && task.status !== 'CANCELLED').map((task) => (
                  <option key={task.id} value={task.id}>{task.title}{task.deadline ? ` · due ${formatDate(task.deadline)}` : ''}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              Reminder type
              <select value={reminderType} onChange={(event) => setReminderType(event.target.value as 'UPCOMING' | 'OVERDUE' | 'ESCALATION')} className={fieldClass}>
                <option value="UPCOMING">Upcoming deadline</option>
                <option value="OVERDUE">Overdue task</option>
                <option value="ESCALATION">Escalation</option>
              </select>
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              Delivery provider
              <select value={targetProvider} onChange={(event) => setTargetProvider(event.target.value as 'email' | 'slack')} className={fieldClass}>
                <option value="email">Email</option>
                <option value="slack">Slack</option>
              </select>
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              Schedule time <span className="text-zinc-600">· optional, defaults to deadline or now</span>
              <input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} className={fieldClass} />
            </label>
            <div className="flex items-end justify-between gap-3">
              <p className="text-[11px] leading-5 text-zinc-500">Timezone · {user?.timezone || 'UTC'}</p>
              <button type="submit" disabled={!actionItemId || schedule.isPending || tasksLoading} className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">
                {schedule.isPending ? 'Preparing…' : 'Send to approval'}
              </button>
            </div>
          </form>
        )}
      </Card>
      <Card title={`Reminder history · ${reminders.length}`}>
        {remindersLoading || remindersError || !reminders.length ? (
          <QueryFeedback
            isLoading={remindersLoading}
            error={remindersError}
            emptyMessage="No reminders have been prepared for this workspace."
          />
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {reminders.map((reminder: any) => (
              <div key={reminder.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-100">{reminder.task_title || 'Action item reminder'}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-500">
                    <span>{reminder.reminder_type}</span>
                    <span>{reminder.target_provider}</span>
                    <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />{formatDateTime(reminder.scheduled_for)}</span>
                    {reminder.timezone && <span>{reminder.timezone}</span>}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge value={reminder.status} />
                  {reminder.approval_id && <Link to="/app/approvals" className="text-xs text-emerald-300 hover:text-emerald-200">Review approval ↗</Link>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

// 8. Approval Inbox (Central Human Approval Gate)
export const ApprovalInboxPage: React.FC = () => {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const { data, isLoading, error } = useQuery({
    queryKey: ['approvals', statusFilter],
    queryFn: () => api.listApprovals(statusFilter === 'ALL' ? undefined : statusFilter),
  });
  const [notice, setNotice] = useState('');
  const refreshApprovals = () => {
    ['approvals', 'analytics', 'reminders', 'digests'].forEach((key) => qc.invalidateQueries({ queryKey: [key] }));
  };
  const approve = useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => api.approveAction(id, comment),
    onSuccess: () => {
      setNotice('Action approved.');
      refreshApprovals();
    },
  });
  const reject = useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => api.rejectAction(id, comment),
    onSuccess: () => {
      setNotice('Action rejected.');
      refreshApprovals();
    },
  });
  const execute = useMutation({
    mutationFn: (id: string) => api.executeAction(id),
    onSuccess: () => {
      setNotice('Approved action executed.');
      refreshApprovals();
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approval inbox"
        eyebrow="Human control"
        description="Review the proposed action and its evidence. External execution remains blocked until an authorized person approves it."
      />
      <MutationFeedback error={approve.error || reject.error || execute.error} notice={notice} />
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-medium text-zinc-200">Review queue</h2>
            <p className="mt-1 text-xs text-zinc-500">{data?.approvals?.length ?? 0} records in this view</p>
          </div>
          <label className="sr-only" htmlFor="approval-status-filter">Filter approvals by status</label>
          <select id="approval-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className={`${fieldClass} sm:w-52`}>
            <option value="ALL">All approvals</option>
            {['PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED'].map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
        </div>
        <div className="mt-4 space-y-3">
          {isLoading || error || !data?.approvals?.length ? (
            <QueryFeedback isLoading={isLoading} error={error} emptyMessage="No actions are waiting for approval." />
          ) : data.approvals.map((a) => (
            <article key={a.id} className="rounded-xl border border-white/[0.07] bg-black/20 p-4 sm:p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{a.target_provider} · {a.action_type}</p>
                  <h3 className="mt-1 text-sm font-semibold text-white">{a.proposed_content?.title || a.proposed_content?.subject || 'Proposed external action'}</h3>
                </div>
                <StatusBadge value={a.status} />
              </div>
              {a.supporting_evidence && (
                <blockquote className="mt-4 border-l-2 border-emerald-400/40 pl-3 text-xs italic leading-5 text-zinc-400">
                  “{a.supporting_evidence}”
                </blockquote>
              )}
              <details className="mt-4 rounded-lg border border-white/[0.05] bg-[#09090b]/50">
                <summary className="cursor-pointer px-3 py-2.5 text-xs font-medium text-zinc-300 marker:text-zinc-600">Inspect proposed payload</summary>
                <pre className="max-h-64 overflow-auto border-t border-white/[0.05] p-3 text-[11px] leading-5 text-zinc-400">{JSON.stringify(a.proposed_content, null, 2)}</pre>
              </details>
              {a.status === 'PENDING' && (
                <div className="mt-4 space-y-3 border-t border-white/[0.06] pt-4">
                  <label className="block space-y-1.5 text-xs text-zinc-400">
                    Review note <span className="text-zinc-600">· optional, recorded with your decision</span>
                    <textarea
                      rows={2}
                      value={reviewNotes[a.id] || ''}
                      onChange={(event) => setReviewNotes((notes) => ({ ...notes, [a.id]: event.target.value }))}
                      className={fieldClass}
                      placeholder="Add context for the audit trail"
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={approve.isPending || reject.isPending || execute.isPending} onClick={() => approve.mutate({ id: a.id, comment: reviewNotes[a.id] })} className="rounded-lg bg-emerald-400 px-3.5 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:opacity-50">
                      Approve
                    </button>
                    <button type="button" disabled={approve.isPending || reject.isPending || execute.isPending} onClick={() => reject.mutate({ id: a.id, comment: reviewNotes[a.id] })} className="rounded-lg border border-rose-400/20 bg-rose-400/[0.06] px-3.5 py-2 text-xs font-medium text-rose-200 transition hover:bg-rose-400/[0.12] disabled:opacity-50">
                      Reject
                    </button>
                  </div>
                </div>
              )}
              {a.status === 'APPROVED' && (
                <div className="mt-4 flex flex-col gap-3 border-t border-white/[0.06] pt-4 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs text-zinc-500">Approved actions can now be sent through the authorized integration adapter.</p>
                  <button type="button" disabled={approve.isPending || reject.isPending || execute.isPending} onClick={() => execute.mutate(a.id)} className="rounded-lg bg-white px-3.5 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-emerald-100 disabled:opacity-50">
                    Execute via Authorized Adapter
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      </Card>
    </div>
  );
};

// 9. Commitment Radar
export const CommitmentRadarPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({ queryKey: ['radar'], queryFn: api.getCommitmentRadar });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Commitment radar"
        eyebrow="Early attention"
        description="At-risk commitments and unresolved decision conflicts from your workspace records."
      />
      {isLoading || error ? (
        <QueryFeedback isLoading={isLoading} error={error} emptyMessage="" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Card title={`At-Risk Commitments (${data?.at_risk_commitments?.length ?? 0})`}>
            {data?.at_risk_commitments?.length ? data.at_risk_commitments.map((item: any) => (
              <article key={item.task.id} className="border-b border-white/[0.06] py-3 last:border-0">
                <Link to={item.task.meeting_id ? `/app/meetings/${item.task.meeting_id}` : '/app/tasks'} className="text-sm font-medium text-zinc-100 transition hover:text-emerald-300">{item.task.title}</Link>
                <p className="mt-1 text-xs leading-5 text-rose-300">{item.reason}</p>
                <p className="mt-1 text-[11px] text-zinc-500">{item.task.assigned_name || 'Unassigned'} · {formatDate(item.task.deadline)}</p>
              </article>
            )) : <p className="text-sm text-zinc-500">No commitments are currently at risk.</p>}
          </Card>
          <Card title={`Open Decision Conflicts (${data?.open_conflicts?.length ?? 0})`}>
            {data?.open_conflicts?.length ? data.open_conflicts.map((c: any) => (
              <article key={c.id} className="border-b border-white/[0.06] py-3 last:border-0">
                <p className="text-sm leading-5 text-zinc-200">{c.explanation}</p>
                <Link to="/app/conflicts" className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-200">Review conflict <ArrowUpRight className="h-3 w-3" /></Link>
              </article>
            )) : <p className="text-sm text-zinc-500">No open conflicts.</p>}
          </Card>
        </div>
      )}
    </div>
  );
};

// 10. Weekly Digests
export const WeeklyDigestsPage: React.FC = () => {
  const qc = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const { data, isLoading, error } = useQuery({ queryKey: ['digests'], queryFn: api.listDigests });
  const [deliveryDay, setDeliveryDay] = useState('Monday');
  const [deliveryTime, setDeliveryTime] = useState('09:00');
  const gen = useMutation({
    mutationFn: () => api.generateDigest({
      delivery_day: deliveryDay,
      delivery_time: deliveryTime,
      timezone: user?.timezone || 'UTC',
      digest_format: 'markdown',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['digests'] });
      qc.invalidateQueries({ queryKey: ['approvals'] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Weekly digests"
        eyebrow="A clear week, ahead"
        description="Generate a personal summary from recorded work and send it to the approval queue before delivery."
        action={<Link to="/app/approvals" className="inline-flex items-center gap-2 rounded-lg border border-white/[0.1] px-3 py-2 text-xs font-medium text-zinc-200 transition hover:bg-white/[0.05]">Approval Inbox <ArrowUpRight className="h-3.5 w-3.5" /></Link>}
      />
      <Card title="Delivery preferences">
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <label className="space-y-1.5 text-xs text-zinc-400">
            Delivery day
            <select value={deliveryDay} onChange={(event) => setDeliveryDay(event.target.value)} className={fieldClass}>
              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day) => <option key={day} value={day}>{day}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-xs text-zinc-400">
            Delivery time
            <input type="time" value={deliveryTime} onChange={(event) => setDeliveryTime(event.target.value)} className={fieldClass} />
          </label>
          <button type="button" disabled={gen.isPending} onClick={() => gen.mutate()} className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">
            {gen.isPending ? 'Generating…' : 'Generate digest'}
          </button>
        </div>
        <p className="mt-3 text-[11px] text-zinc-500">Timezone · {user?.timezone || 'UTC'}. Generated digests are queued for approval; nothing is sent from this screen.</p>
      </Card>
      <MutationFeedback
        error={gen.error}
        notice={gen.isSuccess ? 'Digest generated and queued for approval.' : undefined}
      />
      <Card title={`Generated summaries · ${data?.digests?.length ?? 0}`}>
        {isLoading || error || !data?.digests?.length ? (
          <QueryFeedback isLoading={isLoading} error={error} emptyMessage="No weekly digests have been generated." />
        ) : (
          <div className="space-y-3">
            {data.digests.map((d: any) => (
              <article key={d.id} className="rounded-xl border border-white/[0.06] bg-black/20 p-4 sm:p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-zinc-100">{d.content?.recipient_name || 'Workspace digest'}</p>
                    <p className="mt-1 text-xs text-zinc-500">{formatDate(d.period_start)} — {formatDate(d.period_end)}</p>
                  </div>
                  <StatusBadge value={d.status} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[
                    ['Assigned', d.content?.assigned_tasks?.length ?? 0],
                    ['Completed', d.content?.completed_tasks?.length ?? 0],
                    ['Pending', d.content?.pending_tasks?.length ?? 0],
                    ['Overdue', d.content?.overdue_tasks?.length ?? 0],
                  ].map(([label, count]) => (
                    <div key={label} className="rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2">
                      <p className="text-[10px] text-zinc-500">{label}</p>
                      <p className="mt-1 text-base font-semibold text-zinc-200">{count}</p>
                    </div>
                  ))}
                </div>
                {d.content?.markdown && <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-white/[0.05] bg-[#09090b]/70 p-4 text-xs leading-6 text-zinc-300">{d.content.markdown}</pre>}
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

// 11. Analytics (Recharts grounded in real API data)
export const AnalyticsPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({ queryKey: ['analytics'], queryFn: api.getAnalyticsOverview });
  const chartData = [
    { name: 'Completed', count: data?.tasks_summary?.completed ?? 0 },
    { name: 'Pending', count: data?.tasks_summary?.pending ?? 0 },
    { name: 'Overdue', count: data?.tasks_summary?.overdue ?? 0 },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Execution analytics"
        eyebrow="Measured follow-through"
        description="Task completion and accountability metrics calculated from persisted workspace activity."
      />
      {isLoading || error ? (
        <QueryFeedback isLoading={isLoading} error={error} emptyMessage="" />
      ) : (
        <Card title="Task commitment breakdown">
          {chartData.every((item) => item.count === 0) ? (
            <p className="text-sm text-zinc-500">Task analytics will appear after meetings produce action items.</p>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <XAxis dataKey="name" stroke="#71717A" fontSize={12} />
                  <YAxis stroke="#71717A" fontSize={12} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#10B981" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

// 12. Integrations
export const IntegrationsPage: React.FC = () => {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['integrations'], queryFn: api.listIntegrations });
  const connect = useMutation({
    mutationFn: (provider: string) =>
      api.connectIntegration(provider, { workspace_name: `${provider.toUpperCase()} Workspace` }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations'] }),
  });

  const providers = ['linear', 'trello', 'google_calendar', 'email', 'slack'];
  const connectedMap = new Map((data?.integrations || []).map((i: any) => [i.provider, i]));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrations"
        eyebrow="Connected workflows"
        description={data?.simulated
          ? 'Demo mode is active. Actions are simulated by the backend and are not sent to providers.'
          : 'Live mode is active. Approved actions use provider credentials configured on the backend.'}
      />
      {data && <p className="inline-flex items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-zinc-400"><span className={`h-1.5 w-1.5 rounded-full ${data.simulated ? 'bg-amber-300' : 'bg-emerald-300'}`} />{data.mode.toUpperCase()} MODE · provider actions require approval</p>}
      {error && <p role="alert" className="text-sm text-rose-300">{error.message}</p>}
      {connect.isError && <p role="alert" className="text-sm text-rose-300">{connect.error.message}</p>}
      {isLoading && <QueryFeedback isLoading error={null} emptyMessage="" />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((p) => {
          const existing: any = connectedMap.get(p);
          return (
            <Card key={p}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium capitalize text-white">{p.replace('_', ' ')}</span>
                <StatusBadge value={existing ? existing.status : 'DISCONNECTED'} />
              </div>
              <button
                type="button"
                disabled={connect.isPending}
                onClick={() => connect.mutate(p)}
                className="mt-4 rounded-lg border border-white/[0.1] px-3 py-2 text-xs font-medium text-zinc-200 transition hover:border-emerald-400/30 hover:bg-emerald-400/[0.05] disabled:opacity-50"
              >
                {connect.isPending ? 'Saving…' : existing ? 'Refresh connection' : 'Connect workspace'}
              </button>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

// 13. Settings
export const SettingsPage: React.FC = () => {
  const { user, organization, role } = useAuthStore();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Workspace settings"
        eyebrow="Your account"
        description="Profile and organization context for this session."
      />
      <Card title="Profile & organization">
        <div className="space-y-2 text-sm text-zinc-300">
          {[
            ['Name', user?.full_name],
            ['Email', user?.email],
            ['Organization', organization?.name],
            ['Role', role],
            ['Timezone', user?.timezone],
          ].map(([label, value]) => (
            <div key={label} className="flex flex-col gap-1 border-b border-white/[0.05] py-3 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-xs text-zinc-500">{label}</span>
              <span className="text-sm text-zinc-200">{value || 'Not set'}</span>
            </div>
          ))}
          <div className="rounded-xl border border-emerald-400/10 bg-emerald-400/[0.035] p-4 text-xs leading-5 text-emerald-100/80">
            Approval policy · Human authorization is required before external actions can execute.
          </div>
        </div>
      </Card>
    </div>
  );
};
