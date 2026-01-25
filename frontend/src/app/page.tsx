'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useConfigStore, SUPPORTED_LANGUAGES } from '@/stores/configStore';
import { useJobStore, type JobItem, type Platform } from '@/stores/jobStore';
import { validateUrls, createJob, startJob, validateApiKey, ApiError } from '@/lib/api';
import { useJobSSE } from '@/hooks/useSSE';

// Icons as inline SVGs for simplicity
const Icons = {
  YouTube: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
    </svg>
  ),
  Instagram: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
    </svg>
  ),
  TikTok: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
      <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/>
    </svg>
  ),
  Key: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
    </svg>
  ),
  Globe: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <circle cx="12" cy="12" r="10"/>
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  ),
  Zap: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  Play: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
  ),
  Download: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
    </svg>
  ),
  FileText: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  Check: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  Loader: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 animate-spin">
      <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
      <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round"/>
    </svg>
  ),
  Terminal: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
      <polyline points="4 17 10 11 4 5"/>
      <line x1="12" y1="19" x2="20" y2="19"/>
    </svg>
  ),
  AlertCircle: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  ),
};

// Platform icon component
function PlatformIcon({ platform }: { platform: Platform | null }) {
  if (platform === 'youtube') return <Icons.YouTube />;
  if (platform === 'instagram') return <Icons.Instagram />;
  if (platform === 'tiktok') return <Icons.TikTok />;
  return <Icons.AlertCircle />;
}

// Sidebar Config Panel
function ConfigPanel() {
  const {
    apiKey,
    language,
    isDevTier,
    isApiKeyValid,
    isValidating,
    validationError,
    setApiKey,
    setLanguage,
    setIsDevTier,
    setApiKeyValidation,
    setValidating,
  } = useConfigStore();

  // Debounced API key validation
  useEffect(() => {
    if (!apiKey) {
      setApiKeyValidation(null);
      return;
    }

    // Basic format check immediately
    if (!apiKey.startsWith('gsk_') || apiKey.length < 20) {
      setApiKeyValidation(false, 'Invalid API key format');
      return;
    }

    // Debounce API validation call
    setValidating(true);
    const timer = setTimeout(async () => {
      try {
        const result = await validateApiKey(apiKey);
        setApiKeyValidation(result.valid, result.error);
      } catch (error) {
        if (error instanceof ApiError) {
          setApiKeyValidation(false, error.message);
        } else {
          setApiKeyValidation(false, 'Failed to validate API key');
        }
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [apiKey, setApiKeyValidation, setValidating]);

  return (
    <aside className="w-72 bg-[var(--bg-secondary)] border-r border-[var(--border-subtle)] flex flex-col">
      {/* Logo */}
      <div className="p-5 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--accent-cyan)] to-[var(--accent-green)] flex items-center justify-center">
            <Icons.Terminal />
          </div>
          <div>
            <h1 className="font-mono font-bold text-lg tracking-tight">MultiFetch</h1>
            <p className="text-xs text-[var(--text-muted)] font-mono">v2.0.0</p>
          </div>
        </div>
      </div>

      {/* Config */}
      <div className="flex-1 p-5 space-y-6 overflow-y-auto">
        {/* API Key */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
            <Icons.Key />
            Groq API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="gsk_..."
            className={`input-terminal w-full px-3 py-2.5 rounded-md text-sm ${
              validationError ? 'border-[var(--accent-red)]' : ''
            }`}
          />
          {isValidating && (
            <p className="text-xs text-[var(--text-muted)] flex items-center gap-1">
              <Icons.Loader /> Validating...
            </p>
          )}
          {validationError && (
            <p className="text-xs text-[var(--accent-red)]">{validationError}</p>
          )}
          {!apiKey && (
            <p className="text-xs text-[var(--text-muted)]">
              Get key at{' '}
              <a href="https://console.groq.com" target="_blank" className="text-[var(--accent-cyan)] hover:underline">
                console.groq.com
              </a>
            </p>
          )}
        </div>

        {/* Language */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
            <Icons.Globe />
            Language
          </label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="input-terminal w-full px-3 py-2.5 rounded-md text-sm cursor-pointer"
          >
            {SUPPORTED_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.name}
              </option>
            ))}
          </select>
        </div>

        {/* Dev Tier Toggle */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
            <Icons.Zap />
            API Tier
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => setIsDevTier(false)}
              className={`flex-1 px-3 py-2 rounded-md text-sm font-mono transition-all ${
                !isDevTier
                  ? 'bg-[var(--accent-cyan)] text-[var(--bg-primary)]'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]'
              }`}
            >
              Free (25MB)
            </button>
            <button
              onClick={() => setIsDevTier(true)}
              className={`flex-1 px-3 py-2 rounded-md text-sm font-mono transition-all ${
                isDevTier
                  ? 'bg-[var(--accent-cyan)] text-[var(--bg-primary)]'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]'
              }`}
            >
              Dev (100MB)
            </button>
          </div>
        </div>

        {/* Supported Platforms */}
        <div className="pt-4 border-t border-[var(--border-subtle)]">
          <p className="text-xs font-medium text-[var(--text-muted)] mb-3 uppercase tracking-wider">
            Supported Platforms
          </p>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="w-6 h-6 rounded flex items-center justify-center bg-[var(--youtube)] text-white">
                <Icons.YouTube />
              </span>
              <span className="text-[var(--text-secondary)]">YouTube</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="w-6 h-6 rounded flex items-center justify-center bg-[var(--instagram)] text-white">
                <Icons.Instagram />
              </span>
              <span className="text-[var(--text-secondary)]">Instagram</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="w-6 h-6 rounded flex items-center justify-center bg-[var(--tiktok)] text-[var(--bg-primary)]">
                <Icons.TikTok />
              </span>
              <span className="text-[var(--text-secondary)]">TikTok</span>
            </div>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-tertiary)]">
        <div className="flex items-center gap-2">
          <span className={`status-dot ${isApiKeyValid ? 'status-success' : apiKey ? 'status-pending' : 'status-pending'}`} />
          <span className="text-xs text-[var(--text-muted)] font-mono">
            {isApiKeyValid ? 'API Connected' : apiKey ? 'Validating...' : 'API Key Required'}
          </span>
        </div>
      </div>
    </aside>
  );
}

// URL Input Component
function UrlInput() {
  const {
    urlInput,
    validatedUrls,
    isValidating,
    isProcessing,
    setUrlInput,
    setValidatedUrls,
    setIsValidating,
  } = useJobStore();

  const { isApiKeyValid, language } = useConfigStore();
  const { setCurrentJob, setProcessing, updateJobItem } = useJobStore();

  // Parse URLs from input
  const urlLines = useMemo(() =>
    urlInput.split('\n').filter((line) => line.trim()),
    [urlInput]
  );

  // Debounced URL validation
  useEffect(() => {
    if (urlLines.length === 0) {
      setValidatedUrls([]);
      return;
    }

    setIsValidating(true);
    const timer = setTimeout(async () => {
      try {
        const results = await validateUrls(urlLines);
        setValidatedUrls(results);
      } catch (error) {
        console.error('URL validation failed:', error);
        setIsValidating(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [urlLines, setValidatedUrls, setIsValidating]);

  const validUrls = useMemo(() =>
    validatedUrls.filter((u) => u.valid),
    [validatedUrls]
  );

  // SSE connection for real-time updates
  const { currentJob } = useJobStore();

  useJobSSE(currentJob?.id ?? null, {
    onUpdate: (job) => {
      setCurrentJob(job);
    },
    onItemUpdate: (data) => {
      updateJobItem(data.url, {
        progress: data.progress,
        status: data.status as JobItem['status'],
        title: data.title ?? undefined,
        transcript: data.transcript ?? undefined,
        error: data.error ?? undefined,
      });
    },
    onComplete: (job) => {
      setCurrentJob(job);
      setProcessing(false);
    },
    onError: (error) => {
      setProcessing(false, error);
    },
  });

  const handleProcess = useCallback(async () => {
    if (!isApiKeyValid || validUrls.length === 0) return;

    setProcessing(true);

    try {
      // Create the job
      const job = await createJob(
        validUrls.map((u) => u.url),
        'full',
        language
      );
      setCurrentJob(job);

      // Start processing
      await startJob(job.id);
    } catch (error) {
      console.error('Failed to create job:', error);
      setProcessing(false, error instanceof Error ? error.message : 'Failed to create job');
    }
  }, [isApiKeyValid, validUrls, language, setCurrentJob, setProcessing]);

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-mono font-semibold text-lg flex items-center gap-2">
          <span className="text-[var(--accent-cyan)]">&gt;</span>
          Input URLs
        </h2>
        {urlLines.length > 0 && (
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {isValidating ? (
              <span className="flex items-center gap-1">
                <Icons.Loader /> Validating...
              </span>
            ) : (
              `${validUrls.length}/${urlLines.length} valid`
            )}
          </span>
        )}
      </div>

      <textarea
        value={urlInput}
        onChange={(e) => setUrlInput(e.target.value)}
        placeholder="Paste URLs here (one per line)&#10;&#10;https://www.youtube.com/watch?v=...&#10;https://www.instagram.com/reel/...&#10;https://www.tiktok.com/@user/video/..."
        className="input-terminal w-full h-48 px-4 py-3 rounded-lg text-sm resize-none"
        spellCheck={false}
        disabled={isProcessing}
      />

      {/* URL Preview */}
      {validatedUrls.length > 0 && (
        <div className="space-y-2">
          {validatedUrls.slice(0, 5).map((result, i) => (
            <div
              key={i}
              className="flex items-center gap-2 text-xs font-mono bg-[var(--bg-tertiary)] px-3 py-2 rounded"
            >
              {result.valid ? (
                <span className={`${
                  result.platform === 'youtube' ? 'text-[var(--youtube)]' :
                  result.platform === 'instagram' ? 'text-[var(--instagram)]' :
                  'text-[var(--tiktok)]'
                }`}>
                  <PlatformIcon platform={result.platform} />
                </span>
              ) : (
                <span className="text-[var(--accent-red)]">
                  <Icons.AlertCircle />
                </span>
              )}
              <span className="truncate text-[var(--text-secondary)]">{result.url}</span>
              {!result.valid && result.error && (
                <span className="text-[var(--accent-red)] ml-auto text-[10px]">{result.error}</span>
              )}
              {result.is_collection && (
                <span className="text-[var(--accent-cyan)] ml-auto text-[10px]">Collection</span>
              )}
            </div>
          ))}
          {validatedUrls.length > 5 && (
            <p className="text-xs text-[var(--text-muted)] font-mono">
              +{validatedUrls.length - 5} more URLs
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleProcess}
        disabled={isProcessing || validUrls.length === 0 || !isApiKeyValid}
        className="btn-primary w-full py-3 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isProcessing ? (
          <>
            <Icons.Loader />
            Processing...
          </>
        ) : (
          <>
            <Icons.Play />
            Process {validUrls.length} URL{validUrls.length !== 1 ? 's' : ''}
          </>
        )}
      </button>

      {!isApiKeyValid && validUrls.length > 0 && (
        <p className="text-xs text-[var(--accent-red)] text-center">
          Please enter a valid API key to process URLs
        </p>
      )}
    </div>
  );
}

// Result Card Component
function ResultCard({ item }: { item: JobItem }) {
  const [expanded, setExpanded] = useState(false);

  const statusClass = item.status === 'completed' ? 'status-success' :
                      item.status === 'failed' ? 'status-error' :
                      item.status === 'running' ? 'status-processing' :
                      'status-pending';

  return (
    <div className="card-elevated p-4 space-y-3 animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`w-8 h-8 rounded flex items-center justify-center flex-shrink-0 ${
              item.platform === 'youtube'
                ? 'bg-[var(--youtube)]'
                : item.platform === 'instagram'
                ? 'bg-[var(--instagram)]'
                : 'bg-[var(--tiktok)]'
            } text-white`}
          >
            <PlatformIcon platform={item.platform} />
          </span>
          <div className="min-w-0">
            <h3 className="font-medium text-sm truncate">
              {item.title || `Video ${item.video_id || '...'}`}
            </h3>
            <p className="text-xs text-[var(--text-muted)] font-mono truncate">
              {item.url}
            </p>
          </div>
        </div>
        <span className={`status-dot flex-shrink-0 ${statusClass}`} />
      </div>

      {item.status === 'running' && (
        <div className="progress-bar h-1.5 rounded-full overflow-hidden">
          <div
            className="progress-fill h-full rounded-full transition-all duration-300"
            style={{ width: `${item.progress}%` }}
          />
        </div>
      )}

      {item.status === 'failed' && item.error && (
        <div className="text-sm text-[var(--accent-red)] bg-[var(--bg-primary)] p-3 rounded font-mono">
          Error: {item.error}
        </div>
      )}

      {item.status === 'completed' && item.transcript && (
        <>
          <div
            className={`text-sm text-[var(--text-secondary)] bg-[var(--bg-primary)] p-3 rounded font-mono leading-relaxed ${
              expanded ? '' : 'line-clamp-3'
            }`}
          >
            {item.transcript}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="btn-secondary px-3 py-1.5 rounded text-xs"
            >
              {expanded ? 'Show Less' : 'Show More'}
            </button>
            <button className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5">
              <Icons.Download />
              MP3
            </button>
            <button className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5">
              <Icons.FileText />
              TXT
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// Main Page
export default function Home() {
  const { currentJob, isProcessing, processingError } = useJobStore();

  const results = currentJob?.items ?? [];
  const completedCount = currentJob?.completed_count ?? 0;
  const hasCompletedItems = completedCount > 0;

  return (
    <div className="flex h-screen overflow-hidden">
      <ConfigPanel />

      <main className="flex-1 overflow-y-auto grid-bg">
        <div className="max-w-4xl mx-auto p-8 space-y-8">
          {/* Header */}
          <header>
            <h1 className="text-3xl font-bold font-mono tracking-tight">
              Media <span className="text-[var(--accent-cyan)]">Transcription</span>
            </h1>
            <p className="text-[var(--text-secondary)] mt-2">
              Download and transcribe audio from YouTube, Instagram, and TikTok
            </p>
          </header>

          {/* URL Input */}
          <UrlInput />

          {/* Processing Error */}
          {processingError && (
            <div className="card p-4 border-[var(--accent-red)] bg-[var(--bg-secondary)]">
              <div className="flex items-center gap-2 text-[var(--accent-red)]">
                <Icons.AlertCircle />
                <span className="font-medium">Processing Error</span>
              </div>
              <p className="text-sm text-[var(--text-secondary)] mt-2">{processingError}</p>
            </div>
          )}

          {/* Results */}
          {results.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-mono font-semibold text-lg flex items-center gap-2">
                  <span className="text-[var(--accent-green)]">&gt;</span>
                  Results
                  <span className="text-xs text-[var(--text-muted)] font-normal">
                    ({completedCount}/{results.length})
                  </span>
                </h2>
                {hasCompletedItems && (
                  <div className="flex gap-2">
                    <button className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5">
                      <Icons.Download />
                      Export ZIP
                    </button>
                    <button className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5">
                      <Icons.FileText />
                      Export JSON
                    </button>
                  </div>
                )}
              </div>

              {/* Overall Progress */}
              {isProcessing && currentJob && (
                <div className="card p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-[var(--text-secondary)]">Overall Progress</span>
                    <span className="text-sm font-mono text-[var(--text-muted)]">
                      {currentJob.progress}%
                    </span>
                  </div>
                  <div className="progress-bar h-2 rounded-full overflow-hidden">
                    <div
                      className="progress-fill h-full rounded-full transition-all duration-300"
                      style={{ width: `${currentJob.progress}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="space-y-3">
                {results.map((item, i) => (
                  <ResultCard key={item.url || i} item={item} />
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {results.length === 0 && !isProcessing && (
            <div className="card p-12 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-xl bg-[var(--bg-tertiary)] flex items-center justify-center text-[var(--text-muted)]">
                <Icons.Terminal />
              </div>
              <h3 className="font-mono font-medium text-lg mb-2">Ready to Process</h3>
              <p className="text-[var(--text-muted)] text-sm max-w-md mx-auto">
                Paste video URLs above to download audio and generate transcriptions using Groq Whisper AI
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
