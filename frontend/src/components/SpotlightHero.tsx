import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Menu, ShieldCheck, X } from 'lucide-react';

/**
 * Lithos-inspired cinematic dark hero with cursor-tracked radial spotlight.
 * Uses requestAnimationFrame interpolation + CSS radial-gradient mask directly
 * on a DOM ref (avoiding expensive canvas.toDataURL calls on render),
 * with prefers-reduced-motion support, touch-device fallback, and proper cleanup.
 */
export const SpotlightHero: React.FC = () => {
  const heroRef = useRef<HTMLDivElement | null>(null);
  const revealLayerRef = useRef<HTMLDivElement | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const container = heroRef.current;
    const revealEl = revealLayerRef.current;
    if (!container || !revealEl) return;

    const matchMedia = window.matchMedia?.bind(window);
    const prefersReducedMotion = matchMedia
      ? matchMedia('(prefers-reduced-motion: reduce)').matches
      : false;
    const isTouchDevice = matchMedia
      ? matchMedia('(pointer: coarse)').matches
      : false;
    if (prefersReducedMotion || isTouchDevice) {
      revealEl.style.opacity = '0.28';
      return;
    }

    let targetX = container.clientWidth * 0.5;
    let targetY = container.clientHeight * 0.45;
    let currentX = targetX;
    let currentY = targetY;
    let rafId = 0;

    const onPointerMove = (e: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      targetX = e.clientX - rect.left;
      targetY = e.clientY - rect.top;
    };

    const tick = () => {
      currentX += (targetX - currentX) * 0.1;
      currentY += (targetY - currentY) * 0.1;
      const mask = `radial-gradient(320px circle at ${currentX.toFixed(1)}px ${currentY.toFixed(1)}px, rgba(0,0,0,1) 0%, rgba(0,0,0,0.45) 45%, rgba(0,0,0,0) 75%)`;
      revealEl.style.maskImage = mask;
      revealEl.style.webkitMaskImage = mask;
      rafId = window.requestAnimationFrame(tick);
    };

    container.addEventListener('pointermove', onPointerMove, { passive: true });
    rafId = window.requestAnimationFrame(tick);

    return () => {
      container.removeEventListener('pointermove', onPointerMove);
      window.cancelAnimationFrame(rafId);
    };
  }, []);

  const navLinks = [
    { label: 'Features', href: '#features' },
  ];

  return (
    <section
      ref={heroRef}
      className="relative min-h-screen w-full overflow-hidden bg-[#09090B] text-zinc-100 flex flex-col justify-between"
    >
      {/* Base Dark Architectural Meeting Grid Visual */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 animate-hero-zoom"
        style={{
          backgroundImage:
            'radial-gradient(ellipse 80% 60% at 50% 20%, rgba(39,39,42,0.45), rgba(9,9,11,0.98)), linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '100% 100%, 64px 64px, 64px 64px',
        }}
      />

      {/* Second Reveal Layer (Illuminated Execution Graph under Cursor Spotlight) */}
      <div
        ref={revealLayerRef}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 transition-opacity duration-500"
        style={{
          backgroundImage:
            'radial-gradient(ellipse 75% 65% at 50% 35%, rgba(16,185,129,0.22), rgba(59,130,246,0.12), rgba(9,9,11,0)), linear-gradient(to right, rgba(16,185,129,0.14) 1px, transparent 1px), linear-gradient(to bottom, rgba(16,185,129,0.14) 1px, transparent 1px)',
          backgroundSize: '100% 100%, 64px 64px, 64px 64px',
        }}
      />

      {/* Top Navigation */}
      <header className="relative z-20 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6">
        <Link to="/" className="flex items-center gap-2.5 text-lg font-semibold tracking-tight text-white">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-900 text-emerald-400">
            <ShieldCheck className="h-4 w-4" />
          </span>
          MeetFlow <span className="font-playfair italic font-normal text-zinc-300">AI</span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm text-zinc-400">
          {navLinks.map((item) => (
            <a key={item.label} href={item.href} className="transition-colors hover:text-white">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-4">
          <Link to="/auth" className="text-sm text-zinc-300 hover:text-white transition-colors">
            Sign In
          </Link>
          <Link
            to="/auth?mode=register"
            className="rounded-full bg-white px-4 py-2 text-sm font-medium text-zinc-950 transition hover:bg-zinc-200"
          >
            Get Started
          </Link>
        </div>

        <button
          type="button"
          aria-label="Toggle navigation menu"
          aria-expanded={mobileMenuOpen}
          onClick={() => setMobileMenuOpen((v) => !v)}
          className="md:hidden rounded-lg border border-zinc-800 p-2 text-zinc-300 hover:text-white"
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="relative z-20 mx-6 rounded-xl border border-zinc-800 bg-zinc-950/95 p-5 md:hidden">
          <div className="flex flex-col gap-3 text-sm text-zinc-300">
            {navLinks.map((item) => (
              <a
                key={item.label}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className="py-1.5 hover:text-white"
              >
                {item.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2 border-t border-zinc-800 pt-3">
              <Link to="/auth" className="py-1.5 text-zinc-300 hover:text-white">
                Sign In
              </Link>
              <Link
                to="/auth?mode=register"
                className="rounded-lg bg-white px-4 py-2 text-center font-medium text-zinc-950"
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Hero Centerpiece */}
      <div className="relative z-10 mx-auto flex max-w-4xl flex-col items-center px-6 py-24 text-center">
        <div className="animate-fade-up mb-6 inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/70 px-3.5 py-1.5 text-xs text-zinc-300 backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Cross-Meeting Decision Memory + Human-Controlled Execution
        </div>

        <h1 className="animate-fade-up delay-150 text-5xl font-medium tracking-tight text-white sm:text-7xl leading-[1.06]">
          Meetings end.
          <br />
          <span className="font-playfair italic font-normal text-zinc-200">Execution begins.</span>
        </h1>

        <p className="animate-fade-up delay-300 mt-7 max-w-2xl text-base sm:text-lg leading-relaxed text-zinc-400">
          Every conversation creates commitments. MeetFlow AI remembers them, connects them, and
          helps your team follow through.
        </p>

        <div className="animate-fade-up delay-450 mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            to="/auth?mode=register"
            className="group inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-medium text-zinc-950 transition hover:bg-zinc-200"
          >
            Start Meeting
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <a
            href="#features"
            className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-900/60 px-6 py-3 text-sm font-medium text-zinc-200 backdrop-blur transition hover:border-zinc-500 hover:text-white"
          >
            Explore the Platform
          </a>
        </div>
      </div>

      {/* Subtle Bottom Proof Strip */}
      <div className="relative z-10 mx-auto w-full max-w-7xl border-t border-zinc-900 px-6 py-6 text-xs text-zinc-500 flex flex-wrap items-center justify-between gap-4">
        <span>Zero silent overwrites · Decision DNA versioning</span>
        <span>Backend-enforced Central Human Approval Gate</span>
        <span>Conversations into commitments.</span>
      </div>
    </section>
  );
};
