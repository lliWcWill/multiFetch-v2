'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import JSZip from 'jszip';
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
  ChevronLeft: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  ChevronRight: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  Pin: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M12 17v5M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>
    </svg>
  ),
  PinOff: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M12 17v5M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>
      <line x1="2" y1="2" x2="22" y2="22"/>
    </svg>
  ),
  Copy: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  ),
  Eye: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  ),
  EyeOff: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
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
    sidebarCollapsed,
    sidebarPinned,
    setApiKey,
    setLanguage,
    setIsDevTier,
    setApiKeyValidation,
    setValidating,
    setSidebarCollapsed,
    setSidebarPinned,
  } = useConfigStore();

  const [isHovering, setIsHovering] = useState(false);
  const [wasJustValidated, setWasJustValidated] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);

  // Auto-collapse when API key is validated (but not if pinned)
  useEffect(() => {
    if (isApiKeyValid && !sidebarPinned && wasJustValidated) {
      const timer = setTimeout(() => {
        setSidebarCollapsed(true);
      }, 2000); // 2 second delay so user sees the success state
      return () => clearTimeout(timer);
    }
  }, [isApiKeyValid, sidebarPinned, wasJustValidated, setSidebarCollapsed]);

  // Debounced API key validation
  useEffect(() => {
    if (!apiKey) {
      setApiKeyValidation(null);
      setWasJustValidated(false);
      return;
    }

    // Basic format check immediately
    if (!apiKey.startsWith('gsk_') || apiKey.length < 20) {
      setApiKeyValidation(false, 'Invalid API key format');
      setWasJustValidated(false);
      return;
    }

    // Debounce API validation call
    setValidating(true);
    const timer = setTimeout(async () => {
      try {
        const result = await validateApiKey(apiKey);
        setApiKeyValidation(result.valid, result.error);
        if (result.valid) {
          setWasJustValidated(true);
        }
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

  // Handle mouse leave - collapse if not pinned
  const handleMouseLeave = useCallback(() => {
    setIsHovering(false);
    if (!sidebarPinned && !sidebarCollapsed) {
      // Small delay before collapsing
      setTimeout(() => {
        setSidebarCollapsed(true);
      }, 300);
    }
  }, [sidebarPinned, sidebarCollapsed, setSidebarCollapsed]);

  // Handle mouse enter on hover zone
  const handleHoverZoneEnter = useCallback(() => {
    if (sidebarCollapsed) {
      setIsHovering(true);
      setSidebarCollapsed(false);
    }
  }, [sidebarCollapsed, setSidebarCollapsed]);

  // Determine if sidebar should be shown expanded
  const isExpanded = !sidebarCollapsed;

  return (
    <>
      {/* Hover zone when collapsed - triggers expand on hover */}
      {sidebarCollapsed && (
        <div
          className="fixed left-14 top-0 w-2 h-full z-30 cursor-pointer"
          onMouseEnter={handleHoverZoneEnter}
        />
      )}

      {/* Single sidebar - transitions between collapsed (w-14) and expanded (w-72) */}
      <aside
        className={`bg-[var(--bg-secondary)] border-r border-[var(--border-subtle)] flex flex-col transition-all duration-300 ease-in-out flex-shrink-0 ${
          isExpanded ? 'w-72' : 'w-14'
        }`}
        onMouseLeave={!sidebarPinned && isExpanded ? handleMouseLeave : undefined}
      >
        {/* Logo + Controls */}
        <div className={`border-b border-[var(--border-subtle)] ${isExpanded ? 'p-5' : 'p-2 flex flex-col items-center'}`}>
          {isExpanded ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--accent-cyan)] to-[var(--accent-green)] flex items-center justify-center flex-shrink-0">
                  <Icons.Terminal />
                </div>
                <div>
                  <h1 className="font-mono font-bold text-lg tracking-tight">MultiFetch</h1>
                  <p className="text-xs text-[var(--text-muted)] font-mono">v2.0.0</p>
                </div>
              </div>

              {/* Collapse + Pin buttons */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setSidebarPinned(!sidebarPinned)}
                  className={`w-7 h-7 rounded-md flex items-center justify-center transition-colors ${
                    sidebarPinned
                      ? 'bg-[var(--accent-cyan)] text-[var(--bg-primary)]'
                      : 'bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  }`}
                  title={sidebarPinned ? 'Unpin sidebar' : 'Pin sidebar open'}
                >
                  {sidebarPinned ? <Icons.Pin /> : <Icons.PinOff />}
                </button>
                <button
                  onClick={() => setSidebarCollapsed(true)}
                  className="w-7 h-7 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                  title="Collapse sidebar"
                >
                  <Icons.ChevronLeft />
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--accent-cyan)] to-[var(--accent-green)] flex items-center justify-center mb-2">
                <Icons.Terminal />
              </div>
              <button
                onClick={() => setSidebarCollapsed(false)}
                className="w-8 h-8 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                title="Expand sidebar"
              >
                <Icons.ChevronRight />
              </button>
            </>
          )}
        </div>

        {/* Config - only show when expanded */}
        <div className={`flex-1 overflow-y-auto transition-opacity duration-200 ${isExpanded ? 'p-5 space-y-6 opacity-100' : 'opacity-0 hidden'}`}>
          {/* API Key */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
              <Icons.Key />
              Groq API Key
            </label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="gsk_..."
                className={`input-terminal w-full px-3 py-2.5 pr-10 rounded-md text-sm ${
                  validationError ? 'border-[var(--accent-red)]' : ''
                }`}
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                title={showApiKey ? 'Hide API key' : 'Show API key'}
              >
                {showApiKey ? <Icons.EyeOff /> : <Icons.Eye />}
              </button>
            </div>
            {isValidating && (
              <p className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                <Icons.Loader /> Validating...
              </p>
            )}
            {validationError && (
              <p className="text-xs text-[var(--accent-red)]">{validationError}</p>
            )}
            {isApiKeyValid && (
              <p className="text-xs text-[var(--accent-green)] flex items-center gap-1">
                <Icons.Check /> API key validated
              </p>
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
        <div className={`border-t border-[var(--border-subtle)] bg-[var(--bg-tertiary)] ${isExpanded ? 'p-4' : 'p-2 flex justify-center'}`}>
          <div className={`flex items-center ${isExpanded ? 'gap-2' : ''}`}>
            <span className={`status-dot ${isApiKeyValid ? 'status-success' : apiKey ? 'status-pending' : 'status-pending'}`} />
            {isExpanded && (
              <span className="text-xs text-[var(--text-muted)] font-mono">
                {isApiKeyValid ? 'API Connected' : apiKey ? 'Validating...' : 'API Key Required'}
              </span>
            )}
          </div>
        </div>
      </aside>
    </>
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

  const { apiKey, isApiKeyValid, language, isDevTier } = useConfigStore();
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
    if (!isApiKeyValid || !apiKey || validUrls.length === 0) return;

    setProcessing(true);

    try {
      // Create the job
      const job = await createJob(
        validUrls.map((u) => u.url),
        'full',
        language
      );
      setCurrentJob(job);

      // Start processing with API key
      await startJob(job.id, apiKey, { isDevTier });
    } catch (error) {
      console.error('Failed to create job:', error);
      setProcessing(false, error instanceof Error ? error.message : 'Failed to create job');
    }
  }, [isApiKeyValid, apiKey, validUrls, language, isDevTier, setCurrentJob, setProcessing]);

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
  const [copied, setCopied] = useState(false);

  const statusClass = item.status === 'completed' ? 'status-success' :
                      item.status === 'failed' ? 'status-error' :
                      item.status === 'running' ? 'status-processing' :
                      'status-pending';

  const handleCopy = useCallback(async () => {
    if (item.transcript) {
      await navigator.clipboard.writeText(item.transcript);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [item.transcript]);

  const handleDownloadTxt = useCallback(() => {
    if (item.transcript) {
      const blob = new Blob([item.transcript], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${item.title || item.video_id || 'transcript'}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }, [item.transcript, item.title, item.video_id]);

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
        <div className="flex items-center gap-2 flex-shrink-0">
          {item.status === 'completed' && item.transcript && (
            <button
              onClick={handleCopy}
              className="w-7 h-7 rounded-md bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              title={copied ? 'Copied!' : 'Copy transcript'}
            >
              {copied ? <Icons.Check /> : <Icons.Copy />}
            </button>
          )}
          <span className={`status-dot ${statusClass}`} />
        </div>
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
            <button
              onClick={handleDownloadTxt}
              className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5"
            >
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

  const completedItems = useMemo(() => {
    const items = results.filter((item) => item.status === 'completed' && item.transcript);
    console.log('completedItems computed:', items.length, 'from', results.length, 'results');
    return items;
  }, [results]);

  const handleExportJSON = useCallback(() => {
    console.log('Export JSON clicked', { completedItems, results });
    if (completedItems.length === 0) {
      console.log('No completed items to export');
      return;
    }

    const exportData = completedItems.map((item) => ({
      url: item.url,
      title: item.title || item.video_id || 'Untitled',
      platform: item.platform,
      video_id: item.video_id,
      transcript: item.transcript,
    }));

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcripts-${new Date().toISOString().slice(0, 10)}.json`;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log('JSON export completed');
  }, [completedItems]);

  const handleExportZIP = useCallback(async () => {
    console.log('Export ZIP clicked', { completedItems, results });
    if (completedItems.length === 0) {
      console.log('No completed items to export');
      return;
    }

    const zip = new JSZip();

    completedItems.forEach((item, index) => {
      const filename = `${item.title || item.video_id || `transcript-${index + 1}`}.txt`
        .replace(/[/\\?%*:|"<>]/g, '-'); // Sanitize filename
      zip.file(filename, item.transcript || '');
    });

    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcripts-${new Date().toISOString().slice(0, 10)}.zip`;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log('ZIP export completed');
  }, [completedItems]);

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
                    <button
                      onClick={handleExportZIP}
                      className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5"
                    >
                      <Icons.Download />
                      Export ZIP
                    </button>
                    <button
                      onClick={handleExportJSON}
                      className="btn-secondary px-3 py-1.5 rounded text-xs flex items-center gap-1.5"
                    >
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
