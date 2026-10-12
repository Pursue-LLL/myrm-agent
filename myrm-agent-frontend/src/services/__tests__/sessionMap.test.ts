/**
 * [INPUT]
 * - sessionMap service methods from ../sessionMap
 * - apiClient mock from ../api
 *
 * [OUTPUT]
 * - Comprehensive unit tests for fetchSessionMapProjects, fetchFleetCockpitSummary, and searchSessionMap
 *
 * [POS]
 * Unit test suite for Project-Centric Session Map client service layer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../api';
import {
  fetchSessionMapProjects,
  fetchFleetCockpitSummary,
  searchSessionMap,
  type ProjectCluster,
  type FleetCockpitSummary,
  type SessionSearchResponse,
} from '../sessionMap';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('sessionMap service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchSessionMapProjects', () => {
    it('fetches projects without state filter', async () => {
      const mockClusters: ProjectCluster[] = [
        {
          id: 'proj-01',
          name: 'Open Perplexity',
          description: 'AI Search Engine',
          color: '#6366f1',
          workspace_path: '/workspace/open-perplexity',
          git_repo_url: 'https://github.com/myrm-agent/open-perplexity.git',
          sessions: [],
          active_agent_count: 2,
          total_tokens: 45000,
        },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockClusters);

      const result = await fetchSessionMapProjects();
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/session-map/projects');
      expect(result).toEqual(mockClusters);
    });

    it('fetches projects with specific state filter query param', async () => {
      vi.mocked(apiClient.get).mockResolvedValueOnce([]);

      await fetchSessionMapProjects('working');
      expect(apiClient.get).toHaveBeenCalledWith(
        '/api/v1/session-map/projects?state_filter=working',
      );
    });
  });

  describe('fetchFleetCockpitSummary', () => {
    it('fetches fleet summary metrics', async () => {
      const mockSummary: FleetCockpitSummary = {
        total_projects: 3,
        total_sessions: 12,
        total_agents: 12,
        working_agents: 5,
        ready_agents: 6,
        waiting_input_agents: 1,
        error_agents: 0,
        total_tokens_consumed: 154000,
        top_active_sessions: [],
      };

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockSummary);

      const result = await fetchFleetCockpitSummary();
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/session-map/cockpit');
      expect(result).toEqual(mockSummary);
    });
  });

  describe('searchSessionMap', () => {
    it('searches sessions across projects with query', async () => {
      const mockResponse: SessionSearchResponse = {
        query: 'auth',
        total_hits: 1,
        hits: [
          {
            session: {
              id: 'chat-01',
              title: 'OAuth Authentication',
              agent_name: 'AuthAgent',
              state: 'working',
              tokens_used: 12000,
              last_active_at: '2026-10-12T12:00:00Z',
              tags: ['security'],
            },
            project_name: 'Open Perplexity',
            relevance_score: 1.0,
            matched_snippet: 'Title matched: OAuth Authentication',
          },
        ],
      };

      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      const result = await searchSessionMap('auth', 'proj-01', 'working');
      expect(apiClient.post).toHaveBeenCalledWith('/api/v1/session-map/search', {
        query: 'auth',
        project_id: 'proj-01',
        state: 'working',
      });
      expect(result).toEqual(mockResponse);
    });
  });
});
