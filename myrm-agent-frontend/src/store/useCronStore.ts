import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { CronJob, CronRun, CreateCronJobRequest, UpdateCronJobRequest } from '@/services/cron';
import {
  listCronJobs,
  createCronJob as apiCreate,
  updateCronJob as apiUpdate,
  deleteCronJob as apiDelete,
  pauseCronJob as apiPause,
  resumeCronJob as apiResume,
  triggerCronJob as apiTrigger,
  listCronRuns as apiListRuns,
  listAllCronRuns as apiListAllRuns,
} from '@/services/cron';

const PAGE_SIZE = 20;

interface CronState {
  jobs: CronJob[];
  loading: boolean;
  error: string | null;

  runs: CronRun[];
  runsTotal: number;
  runsHasMore: boolean;
  runsLoading: boolean;
  runsStatusFilter: string | null;

  allRuns: CronRun[];
  allRunsTotal: number;
  allRunsHasMore: boolean;
  allRunsLoading: boolean;
  allRunsStatusFilter: string | null;

  fetchJobs: (force?: boolean) => Promise<void>;
  createJob: (data: CreateCronJobRequest) => Promise<CronJob>;
  updateJob: (id: string, data: UpdateCronJobRequest) => Promise<CronJob>;
  deleteJob: (id: string) => Promise<void>;
  pauseJob: (id: string) => Promise<void>;
  resumeJob: (id: string) => Promise<void>;
  triggerJob: (id: string) => Promise<void>;
  fetchRuns: (jobId: string, opts?: { append?: boolean; status?: string }) => Promise<void>;
  setRunsStatusFilter: (status: string | null) => void;
  fetchAllRuns: (opts?: { append?: boolean; status?: string }) => Promise<void>;
  setAllRunsStatusFilter: (status: string | null) => void;
}

const useCronStore = create<CronState>()(
  immer((set, get) => ({
    jobs: [],
    loading: false,
    error: null,

    runs: [],
    runsTotal: 0,
    runsHasMore: false,
    runsLoading: false,
    runsStatusFilter: null,

    allRuns: [],
    allRunsTotal: 0,
    allRunsHasMore: false,
    allRunsLoading: false,
    allRunsStatusFilter: null,

    fetchJobs: async (force = false) => {
      const { loading, jobs } = get();
      if (!force && (loading || jobs.length > 0)) return;
      set({ loading: true, error: null });
      try {
        const res = await listCronJobs();
        set({ jobs: res.items, loading: false });
      } catch (e) {
        set({ error: e instanceof Error ? e.message : 'Failed to load jobs', loading: false });
      }
    },

    createJob: async (data) => {
      const job = await apiCreate(data);
      set((s) => {
        s.jobs.unshift(job);
      });
      return job;
    },

    updateJob: async (id, data) => {
      const job = await apiUpdate(id, data);
      set((s) => {
        const idx = s.jobs.findIndex((j) => j.id === id);
        if (idx >= 0) s.jobs[idx] = job;
      });
      return job;
    },

    deleteJob: async (id) => {
      await apiDelete(id);
      set((s) => {
        s.jobs = s.jobs.filter((j) => j.id !== id);
      });
    },

    pauseJob: async (id) => {
      const job = await apiPause(id);
      set((s) => {
        const idx = s.jobs.findIndex((j) => j.id === id);
        if (idx >= 0) s.jobs[idx] = job;
      });
    },

    resumeJob: async (id) => {
      const job = await apiResume(id);
      set((s) => {
        const idx = s.jobs.findIndex((j) => j.id === id);
        if (idx >= 0) s.jobs[idx] = job;
      });
    },

    triggerJob: async (id) => {
      await apiTrigger(id);
    },

    fetchRuns: async (jobId, opts) => {
      const { runs: existing, runsStatusFilter } = get();
      const append = opts?.append ?? false;
      const status = opts?.status ?? runsStatusFilter;
      const offset = append ? existing.length : 0;

      set({ runsLoading: true });
      try {
        const res = await apiListRuns(jobId, {
          limit: PAGE_SIZE,
          offset,
          status: status ?? undefined,
        });
        set((s) => {
          s.runs = append ? [...existing, ...res.items] : res.items;
          s.runsTotal = res.total;
          s.runsHasMore = res.has_more;
          s.runsLoading = false;
        });
      } catch {
        set({ runs: [], runsTotal: 0, runsHasMore: false, runsLoading: false });
      }
    },

    setRunsStatusFilter: (status) => {
      set({ runsStatusFilter: status });
    },

    fetchAllRuns: async (opts) => {
      const { allRuns: existing, allRunsStatusFilter } = get();
      const append = opts?.append ?? false;
      const status = opts?.status ?? allRunsStatusFilter;
      const offset = append ? existing.length : 0;

      set({ allRunsLoading: true });
      try {
        const res = await apiListAllRuns({ limit: PAGE_SIZE, offset, status: status ?? undefined });
        set((s) => {
          s.allRuns = append ? [...existing, ...res.items] : res.items;
          s.allRunsTotal = res.total;
          s.allRunsHasMore = res.has_more;
          s.allRunsLoading = false;
        });
      } catch {
        set({ allRuns: [], allRunsTotal: 0, allRunsHasMore: false, allRunsLoading: false });
      }
    },

    setAllRunsStatusFilter: (status) => {
      set({ allRunsStatusFilter: status });
    },
  })),
);

export default useCronStore;
