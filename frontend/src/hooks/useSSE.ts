/**
 * SSE (Server-Sent Events) hook for real-time job progress updates.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { getJobStreamUrl } from '@/lib/api';
import type { Job } from '@/stores/jobStore';

// SSE item update data structure
export interface SSEItemUpdateData {
  url: string;
  progress: number;
  status: string;
  title?: string;
  transcript?: string;
  error?: string;
  job_progress: number;
  completed_count?: number;
  failed_count?: number;
}

// SSE error data structure
interface SSEErrorData {
  error: string;
}

interface UseSSEOptions {
  onUpdate?: (job: Job) => void;
  onItemUpdate?: (data: SSEItemUpdateData) => void;
  onComplete?: (job: Job) => void;
  onError?: (error: string) => void;
  onConnectionError?: (error: Event) => void;
}

interface UseSSEReturn {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  connect: (jobId: string) => void;
  disconnect: () => void;
}

/**
 * Hook for subscribing to real-time job progress via SSE.
 *
 * @example
 * ```tsx
 * const { connect, disconnect, isConnected } = useSSE({
 *   onItemUpdate: (data) => updateJobItem(data.url, { progress: data.progress }),
 *   onComplete: (job) => setCurrentJob(job),
 * });
 *
 * // Connect when job starts
 * useEffect(() => {
 *   if (jobId) {
 *     connect(jobId);
 *     return () => disconnect();
 *   }
 * }, [jobId]);
 * ```
 */
export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
  const { onUpdate, onItemUpdate, onComplete, onError, onConnectionError } = options;

  const eventSourceRef = useRef<EventSource | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Store callbacks in refs to avoid reconnection on callback changes
  const callbacksRef = useRef({ onUpdate, onItemUpdate, onComplete, onError, onConnectionError });

  // Update callbacks ref in effect to avoid issues during render
  useEffect(() => {
    callbacksRef.current = { onUpdate, onItemUpdate, onComplete, onError, onConnectionError };
  });

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsConnected(false);
      setIsConnecting(false);
    }
  }, []);

  const connect = useCallback((jobId: string) => {
    // Close any existing connection
    disconnect();

    setIsConnecting(true);
    setError(null);

    const url = getJobStreamUrl(jobId);
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setIsConnecting(false);
      setError(null);
    };

    eventSource.onerror = (event) => {
      setError('Connection error');
      setIsConnected(false);
      setIsConnecting(false);
      callbacksRef.current.onConnectionError?.(event);

      // Auto-reconnect is handled by browser, but we track state
      if (eventSource.readyState === EventSource.CLOSED) {
        eventSourceRef.current = null;
      }
    };

    // Handle 'update' events (general job status)
    eventSource.addEventListener('update', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as Job;
        callbacksRef.current.onUpdate?.(data);
      } catch (e) {
        console.error('Failed to parse SSE update event:', e);
      }
    });

    // Handle 'item_update' events (progress for specific items)
    eventSource.addEventListener('item_update', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as SSEItemUpdateData;
        callbacksRef.current.onItemUpdate?.(data);
      } catch (err) {
        console.error('Failed to parse SSE item_update event:', err);
      }
    });

    // Handle 'complete' events (job finished)
    eventSource.addEventListener('complete', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as Job;
        callbacksRef.current.onComplete?.(data);
        // Close connection on complete
        disconnect();
      } catch (e) {
        console.error('Failed to parse SSE complete event:', e);
      }
    });

    // Handle 'error' events (job failed)
    eventSource.addEventListener('error', (event: MessageEvent) => {
      // Check if this is a custom error event from the server
      if (event.data) {
        try {
          const data = JSON.parse(event.data) as SSEErrorData;
          setError(data.error);
          callbacksRef.current.onError?.(data.error);
          disconnect();
        } catch {
          // This was a connection error, not a server error event
        }
      }
    });
  }, [disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    isConnecting,
    error,
    connect,
    disconnect,
  };
}

/**
 * Simplified hook that automatically manages SSE connection for a job.
 * Connects when jobId is provided, disconnects when it changes or component unmounts.
 */
export function useJobSSE(
  jobId: string | null,
  options: UseSSEOptions = {}
): UseSSEReturn {
  const sse = useSSE(options);

  useEffect(() => {
    if (jobId) {
      sse.connect(jobId);
    } else {
      sse.disconnect();
    }

    return () => {
      sse.disconnect();
    };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  return sse;
}
