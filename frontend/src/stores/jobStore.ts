/**
 * Job store for MultiFetch v2.
 * Manages job state, URL input, and processing results.
 */

import { create } from 'zustand';

// Types matching backend API responses
export type Platform = 'youtube' | 'instagram' | 'tiktok';
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type JobType = 'download' | 'transcribe' | 'full';

export interface UrlValidationResult {
  valid: boolean;
  url: string;
  platform: Platform | null;
  video_id: string | null;
  is_collection: boolean;
  collection_type: string | null;
  error: string | null;
}

export interface JobItem {
  url: string;
  platform: Platform | null;
  video_id: string | null;
  status: JobStatus;
  progress: number;
  title: string | null;
  transcript: string | null;
  error: string | null;
}

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  progress: number;
  item_count: number;
  completed_count: number;
  failed_count: number;
  language: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  items: JobItem[];
}

interface JobState {
  // URL Input
  urlInput: string;
  validatedUrls: UrlValidationResult[];
  isValidating: boolean;

  // Current job
  currentJob: Job | null;
  isProcessing: boolean;
  processingError: string | null;

  // Job history
  jobs: Job[];

  // Actions - URL Input
  setUrlInput: (input: string) => void;
  setValidatedUrls: (urls: UrlValidationResult[]) => void;
  setIsValidating: (validating: boolean) => void;
  clearUrls: () => void;

  // Actions - Job Management
  setCurrentJob: (job: Job | null) => void;
  updateJobItem: (url: string, updates: Partial<JobItem>) => void;
  updateJobProgress: (progress: number) => void;
  updateJobStatus: (status: JobStatus, error?: string | null) => void;
  setProcessing: (processing: boolean, error?: string | null) => void;

  // Actions - Job History
  addJob: (job: Job) => void;
  removeJob: (jobId: string) => void;
  clearJobs: () => void;

  // Actions - Reset
  reset: () => void;
}

const initialState = {
  urlInput: '',
  validatedUrls: [],
  isValidating: false,
  currentJob: null,
  isProcessing: false,
  processingError: null,
  jobs: [],
};

export const useJobStore = create<JobState>()((set) => ({
  ...initialState,

  // URL Input actions
  setUrlInput: (input: string) =>
    set({ urlInput: input }),

  setValidatedUrls: (urls: UrlValidationResult[]) =>
    set({ validatedUrls: urls, isValidating: false }),

  setIsValidating: (validating: boolean) =>
    set({ isValidating: validating }),

  clearUrls: () =>
    set({ urlInput: '', validatedUrls: [] }),

  // Job Management actions
  setCurrentJob: (job: Job | null) =>
    set({ currentJob: job }),

  updateJobItem: (url: string, updates: Partial<JobItem>) =>
    set((state) => {
      if (!state.currentJob) return state;

      const updatedItems = state.currentJob.items.map((item) =>
        item.url === url ? { ...item, ...updates } : item
      );

      // Recalculate progress
      const totalProgress = updatedItems.reduce((sum, item) => sum + item.progress, 0);
      const progress = Math.floor(totalProgress / updatedItems.length);

      // Calculate counts
      const completedCount = updatedItems.filter((item) => item.status === 'completed').length;
      const failedCount = updatedItems.filter((item) => item.status === 'failed').length;

      return {
        currentJob: {
          ...state.currentJob,
          items: updatedItems,
          progress,
          completed_count: completedCount,
          failed_count: failedCount,
        },
      };
    }),

  updateJobProgress: (progress: number) =>
    set((state) => ({
      currentJob: state.currentJob
        ? { ...state.currentJob, progress }
        : null,
    })),

  updateJobStatus: (status: JobStatus, error?: string | null) =>
    set((state) => ({
      currentJob: state.currentJob
        ? { ...state.currentJob, status, error: error ?? state.currentJob.error }
        : null,
      isProcessing: status === 'running',
    })),

  setProcessing: (processing: boolean, error?: string | null) =>
    set({ isProcessing: processing, processingError: error ?? null }),

  // Job History actions
  addJob: (job: Job) =>
    set((state) => ({
      jobs: [job, ...state.jobs].slice(0, 50), // Keep last 50 jobs
    })),

  removeJob: (jobId: string) =>
    set((state) => ({
      jobs: state.jobs.filter((job) => job.id !== jobId),
    })),

  clearJobs: () =>
    set({ jobs: [] }),

  // Reset
  reset: () =>
    set(initialState),
}));

// Selector helpers
export const selectValidUrls = (state: JobState): UrlValidationResult[] =>
  state.validatedUrls.filter((url) => url.valid);

export const selectInvalidUrls = (state: JobState): UrlValidationResult[] =>
  state.validatedUrls.filter((url) => !url.valid);

export const selectCompletedItems = (state: JobState): JobItem[] =>
  state.currentJob?.items.filter((item) => item.status === 'completed') ?? [];

export const selectFailedItems = (state: JobState): JobItem[] =>
  state.currentJob?.items.filter((item) => item.status === 'failed') ?? [];
