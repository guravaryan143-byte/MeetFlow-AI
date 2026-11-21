import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { SpotlightHero } from '../src/components/SpotlightHero';

describe('SpotlightHero', () => {
  it('renders MeetFlow AI hero heading and primary CTAs', () => {
    render(
      <MemoryRouter>
        <SpotlightHero />
      </MemoryRouter>
    );
    expect(screen.getByText(/Meetings end\./i)).toBeInTheDocument();
    expect(screen.getByText(/Execution begins\./i)).toBeInTheDocument();
    expect(screen.getByText(/Start Meeting/i)).toBeInTheDocument();
    expect(screen.getByText(/Explore the Platform/i)).toBeInTheDocument();
  });
});
