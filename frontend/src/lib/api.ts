/**
 * API client for MultiFetch v2 Flask backend.
 * Provides typed fetch wrappers for all API endpoints.
 */

import type { Job, UrlValidationResult, JobType } from '@/stores/jobStore';

// API base URL from environment variable, defaulting to localhost
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

// Generic fetch wrapper with error handling
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new ApiError(
      data.error || `Request failed with status ${response.status}`,
      response.status,
      data
    );
  }

  return data;
}

// Custom error class for API errors
export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

// ============================================================================
// URL Validation API
// ============================================================================

interface ValidateUrlsResponse {
  results: UrlValidationResult[];
}

/**
 * Validate a single URL.
 */
export async function validateUrl(url: string): Promise<UrlValidationResult> {
  return fetchApi<UrlValidationResult>('/api/urls/validate', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Validate multiple URLs in batch.
 */
export async function validateUrls(urls: string[]): Promise<UrlValidationResult[]> {
  const response = await fetchApi<ValidateUrlsResponse>('/api/urls/validate', {
    method: 'POST',
    body: JSON.stringify({ urls }),
  });
  return response.results;
}

// ============================================================================
// Config Validation API
// ============================================================================

interface ApiKeyValidation {
  valid: boolean;
  error: string | null;
}

interface CookiesValidation {
  valid: boolean;
  cookie_count: number;
  domains: string[];
  error: string | null;
  platforms?: Record<string, { detected: boolean; cookies_found: string[] }>;
}

interface ValidateConfigResponse {
  api_key?: ApiKeyValidation;
  cookies?: CookiesValidation;
}

/**
 * Validate API key (format only, no test connection).
 */
export async function validateApiKey(apiKey: string): Promise<ApiKeyValidation> {
  const response = await fetchApi<ValidateConfigResponse>('/api/config/validate', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  });
  return response.api_key!;
}

/**
 * Validate API key with test connection.
 */
export async function validateApiKeyWithTest(apiKey: string): Promise<ApiKeyValidation> {
  const response = await fetchApi<ValidateConfigResponse>('/api/config/validate', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey, test_connection: true }),
  });
  return response.api_key!;
}

/**
 * Validate cookies content.
 */
export async function validateCookies(cookies: string): Promise<CookiesValidation> {
  const response = await fetchApi<ValidateConfigResponse>('/api/config/validate', {
    method: 'POST',
    body: JSON.stringify({ cookies }),
  });
  return response.cookies!;
}

// ============================================================================
// Jobs API
// ============================================================================

interface CreateJobResponse extends Job {
  invalid_urls?: Array<{ url: string; error: string }>;
}

interface ListJobsResponse {
  jobs: Job[];
}

/**
 * Create a new processing job.
 */
export async function createJob(
  urls: string[],
  jobType: JobType = 'full',
  language: string = 'en'
): Promise<CreateJobResponse> {
  return fetchApi<CreateJobResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify({
      urls,
      job_type: jobType,
      language,
    }),
  });
}

/**
 * Get a job by ID.
 */
export async function getJob(jobId: string): Promise<Job> {
  return fetchApi<Job>(`/api/jobs/${jobId}`);
}

/**
 * List recent jobs.
 */
export async function listJobs(limit: number = 50): Promise<Job[]> {
  const response = await fetchApi<ListJobsResponse>(`/api/jobs?limit=${limit}`);
  return response.jobs;
}

/**
 * Delete a job.
 */
export async function deleteJob(jobId: string): Promise<boolean> {
  const response = await fetchApi<{ deleted: boolean }>(`/api/jobs/${jobId}`, {
    method: 'DELETE',
  });
  return response.deleted;
}

/**
 * Cancel a running job.
 */
export async function cancelJob(jobId: string): Promise<Job> {
  return fetchApi<Job>(`/api/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
}

/**
 * Start processing a pending job.
 */
export async function startJob(jobId: string): Promise<Job> {
  return fetchApi<Job>(`/api/jobs/${jobId}/start`, {
    method: 'POST',
  });
}

// ============================================================================
// SSE URL Helper
// ============================================================================

/**
 * Get the SSE stream URL for a job.
 */
export function getJobStreamUrl(jobId: string): string {
  return `${API_BASE_URL}/api/sse/jobs/${jobId}/stream`;
}
