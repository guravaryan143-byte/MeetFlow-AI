import React from 'react';
import { SpotlightHero } from '../components/SpotlightHero';
import { GitBranch, ShieldAlert, CheckSquare, Mail } from 'lucide-react';

export const LandingPage: React.FC = () => {
  const pillars = [
    {
      icon: GitBranch,
      title: 'Cross-Meeting Decision Memory',
      desc: 'Semantic vector recall compares every new proposal against historical decisions, flagging deadline shifts and contradictions before teams lose alignment.',
    },
    {
      icon: ShieldAlert,
      title: 'Central Human Approval Gate',
      desc: 'No task, reminder, email, or weekly digest is ever dispatched externally without explicit authorized confirmation enforced in the backend.',
    },
    {
      icon: CheckSquare,
      title: 'Evidence-Backed Commitments',
      desc: 'Every extracted decision and action item preserves exact speaker attribution, timestamps, and transcript evidence — never invented owners or dates.',
    },
    {
      icon: Mail,
      title: 'Personalized Weekly Briefs',
      desc: 'Individualized digests generated strictly from persisted database records, previewed and approved prior to delivery.',
    },
  ];

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100">
      <SpotlightHero />
      <section id="features" className="mx-auto max-w-7xl px-6 py-24">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-widest text-emerald-400">Platform Architecture</p>
          <h2 className="mt-3 text-3xl font-medium tracking-tight text-white sm:text-4xl">
            Built for teams that turn discussions into <span className="font-playfair italic">accountable outcomes</span>.
          </h2>
        </div>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {pillars.map((p) => (
            <div key={p.title} className="rounded-2xl border border-zinc-800/80 bg-[#111114] p-6">
              <p.icon className="h-5 w-5 text-emerald-400" />
              <h3 className="mt-4 text-base font-medium text-white">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-400">{p.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
