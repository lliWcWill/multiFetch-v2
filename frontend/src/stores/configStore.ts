/**
 * Configuration store for MultiFetch v2.
 * Manages API key, language, and API tier settings.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ConfigState {
  // API Configuration
  apiKey: string;
  language: string;
  isDevTier: boolean;

  // Validation state
  isApiKeyValid: boolean | null;
  isValidating: boolean;
  validationError: string | null;

  // Actions
  setApiKey: (key: string) => void;
  setLanguage: (lang: string) => void;
  setIsDevTier: (isDev: boolean) => void;
  setApiKeyValidation: (valid: boolean | null, error?: string | null) => void;
  setValidating: (validating: boolean) => void;
  reset: () => void;
}

const initialState = {
  apiKey: '',
  language: 'en',
  isDevTier: false,
  isApiKeyValid: null,
  isValidating: false,
  validationError: null,
};

export const useConfigStore = create<ConfigState>()(
  persist(
    (set) => ({
      ...initialState,

      setApiKey: (key: string) =>
        set({
          apiKey: key,
          isApiKeyValid: null,
          validationError: null,
        }),

      setLanguage: (lang: string) =>
        set({ language: lang }),

      setIsDevTier: (isDev: boolean) =>
        set({ isDevTier: isDev }),

      setApiKeyValidation: (valid: boolean | null, error?: string | null) =>
        set({
          isApiKeyValid: valid,
          validationError: error ?? null,
          isValidating: false,
        }),

      setValidating: (validating: boolean) =>
        set({ isValidating: validating }),

      reset: () =>
        set(initialState),
    }),
    {
      name: 'multifetch-config',
      partialize: (state) => ({
        apiKey: state.apiKey,
        language: state.language,
        isDevTier: state.isDevTier,
      }),
    }
  )
);

// Supported languages
export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'zh', name: 'Chinese' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'it', name: 'Italian' },
  { code: 'ru', name: 'Russian' },
  { code: 'ar', name: 'Arabic' },
  { code: 'hi', name: 'Hindi' },
] as const;
