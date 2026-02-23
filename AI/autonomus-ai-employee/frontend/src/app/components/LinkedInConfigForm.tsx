/**
 * LinkedInConfigForm.tsx
 *
 * React component for configurable LinkedIn post generation with profile defaults.
 *
 * Features:
 * - Fetches configuration options from GET /linkedin/config
 * - Displays user profile info from GET /linkedin/profile-summary
 * - Builds sparse PostGenerationRequest with only overridden fields
 * - Submits to POST /linkedin/generate with optional overrides
 * - Connects to WebSocket for real-time pipeline updates
 *
 * Usage:
 *   <LinkedInConfigForm onPostGenerated={(threadId) => handleThreadId(threadId)} />
 */

import React, { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

type OptionValue = string | { value?: string; label?: string; description?: string };

interface ConfigurationOptions {
  tone_options?: OptionValue[];
  format_options?: OptionValue[];
  audience_options?: OptionValue[];
  goal_options?: OptionValue[];
  cta_style_options?: OptionValue[];
  storytelling_frequency_options?: OptionValue[];
  current_defaults: {
    tone: string;
    format: string;
    audience: string;
    goal: string;
    include_emojis: boolean;
    use_technical_jargon: boolean;
    cta_style: string;
    storytelling_frequency: string;
  };
  user_profile?: {
    name?: string;
    role?: string;
    organization?: string;
    industries?: string[];
    experience_years?: number;
    tech_stack?: string[];
  };
}

interface UserProfile {
  name: string;
  role: string;
  organization: string;
  industries: string[];
  experience_years: number;
  tech_stack: string[];
}

interface PostGenerationRequest {
  topic: string;
  tone?: string;
  format?: string;
  audience?: string;
  goal?: string;
  include_emojis?: boolean;
  use_technical_jargon?: boolean;
  cta_style?: string;
  storytelling_frequency?: string;
}

interface FormState {
  topic: string;
  tone?: string;
  format?: string;
  audience?: string;
  goal?: string;
  include_emojis?: boolean;
  use_technical_jargon?: boolean;
  cta_style?: string;
  storytelling_frequency?: string;
}

interface LinkedInConfigFormProps {
  onPostGenerated?: (threadId: string) => void;
  onError?: (error: string) => void;
  baseUrl?: string;
  minimized?: boolean;
}

export const LinkedInConfigForm: React.FC<LinkedInConfigFormProps> = ({
  onPostGenerated,
  onError,
  baseUrl = 'http://localhost:8000',
  minimized = false,
}) => {
  const [config, setConfig] = useState<ConfigurationOptions | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [customize, setCustomize] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  // Form state - only store values that differ from defaults
  const [formState, setFormState] = useState<FormState>({
    topic: '',
    tone: undefined,
    format: undefined,
    audience: undefined,
    goal: undefined,
    include_emojis: undefined,
    use_technical_jargon: undefined,
    cta_style: undefined,
    storytelling_frequency: undefined,
  });

  // Fetch configuration and profile on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setLoading(true);
        const [configRes, profileRes] = await Promise.all([
          fetch(`${baseUrl}/linkedin/config`),
          fetch(`${baseUrl}/linkedin/profile-summary`),
        ]);

        if (!configRes.ok || !profileRes.ok) {
          throw new Error('Failed to load configuration');
        }

        const configData = await configRes.json();
        const profileData = await profileRes.json();

        const normalizedProfile = normalizeProfile(profileData, configData?.user_profile);

        setConfig(configData);
        setProfile(normalizedProfile);
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMsg);
        onError?.(errorMsg);
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, [baseUrl]);

  useEffect(() => {
    if (minimized) {
      setIsExpanded(false);
    }
  }, [minimized]);

  const handleInputChange = (field: keyof FormState, value: any) => {
    setFormState(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleCustomizeToggle = (value: boolean) => {
    setCustomize(value);
    if (!value) {
      setShowAdvanced(false);
      setFormState(prev => ({
        ...prev,
        tone: undefined,
        format: undefined,
        audience: undefined,
        goal: undefined,
        include_emojis: undefined,
        use_technical_jargon: undefined,
        cta_style: undefined,
        storytelling_frequency: undefined,
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formState.topic.trim()) {
      setError('Please enter a topic');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      // Build sparse request - only include overridden fields
      const request: PostGenerationRequest = {
        topic: formState.topic.trim(),
      };

      // Add any overridden fields (non-undefined values)
      if (formState.tone !== undefined) request.tone = formState.tone;
      if (formState.format !== undefined) request.format = formState.format;
      if (formState.audience !== undefined) request.audience = formState.audience;
      if (formState.goal !== undefined) request.goal = formState.goal;
      if (formState.include_emojis !== undefined) request.include_emojis = formState.include_emojis;
      if (formState.use_technical_jargon !== undefined) request.use_technical_jargon = formState.use_technical_jargon;
      if (formState.cta_style !== undefined) request.cta_style = formState.cta_style;
      if (formState.storytelling_frequency !== undefined) {
        request.storytelling_frequency = formState.storytelling_frequency;
      }

      const response = await fetch(`${baseUrl}/linkedin/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start post generation');
      }

      const data = await response.json();
      onPostGenerated?.(data.thread_id);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  const getDefaultValue = (field: keyof ConfigurationOptions['current_defaults']): string | boolean | undefined => {
    return config?.current_defaults[field];
  };

  const getDisplayValue = (field: keyof FormState): string | boolean | undefined => {
    const value = formState[field];
    return value !== undefined ? value : getDefaultValue(field as any);
  };

  const getSelectValue = (field: keyof FormState): string => {
    const value = getDisplayValue(field);
    return typeof value === 'string' ? value : '';
  };

  const formatOptionLabel = (value: unknown): string => {
    const text = typeof value === 'string' ? value : String(value ?? '');
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
  };

  const normalizeOptions = (options?: OptionValue[]) => {
    return (options ?? []).map((opt) => {
      if (typeof opt === 'string') {
        return { value: opt, label: formatOptionLabel(opt) };
      }
      const value = typeof opt?.value === 'string' ? opt.value : String(opt ?? '');
      const label = typeof opt?.label === 'string' ? opt.label : formatOptionLabel(value);
      return { value, label };
    });
  };

  const toneOptions = normalizeOptions(config?.tone_options);
  const formatOptions = normalizeOptions(config?.format_options);
  const audienceOptions = normalizeOptions(config?.audience_options);
  const goalOptions = normalizeOptions(config?.goal_options);
  const ctaStyleOptions = normalizeOptions(config?.cta_style_options);
  const storytellingOptions = normalizeOptions(config?.storytelling_frequency_options);

  if (loading) {
    return <div className="glass-card p-4 muted-text">Loading configuration...</div>;
  }

  if (!config || !profile) {
    return <div className="glass-card p-4 text-red-500">Failed to load configuration</div>;
  }

  return (
    <div className="glass-card w-full p-5 md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Post Configuration</h3>
          <p className="muted-text text-xs">
            {isExpanded ? 'Use defaults or customize this generation.' : 'Configuration minimized while pipeline is running.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="ghost-button px-3 py-2 text-xs"
            aria-label={isExpanded ? 'Minimize configuration' : 'Expand configuration'}
            title={isExpanded ? 'Minimize' : 'Expand'}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              {isExpanded ? 'unfold_less' : 'unfold_more'}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setShowProfileModal(true)}
            className="ghost-button px-3 py-2 text-xs"
            aria-label="Open user profile"
            title="User Profile"
          >
            <span className="material-symbols-outlined" aria-hidden="true">person</span>
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {isExpanded ? (
      <motion.div
        key="expanded-config"
        initial={{ opacity: 0, height: 0, y: -6 }}
        animate={{ opacity: 1, height: 'auto', y: 0 }}
        exit={{ opacity: 0, height: 0, y: -4 }}
        transition={{ duration: 0.24, ease: 'easeOut' }}
        className="overflow-hidden"
      >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-start justify-between gap-4 rounded-xl border border-[var(--glass-border)] bg-[var(--panel)] p-3.5">
          <div>
            <p className="text-sm font-medium">Use profile defaults</p>
            <p className="muted-text text-xs">Enable customize to override defaults for this post.</p>
          </div>
          <label className="inline-flex items-center gap-2 text-sm muted-text">
            <input
              type="checkbox"
              checked={customize}
              onChange={(e) => handleCustomizeToggle(e.target.checked)}
              className="h-4 w-4 accent-blue-500"
            />
            Customize
          </label>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">
            Topic *
          </label>
          <input
            type="text"
            value={formState.topic}
            onChange={(e) => handleInputChange('topic', e.target.value)}
            placeholder="e.g., AI in healthcare, Kubernetes best practices"
            className="glass-input w-full text-sm"
            required
          />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Tone
              <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('tone')})</span>
            </label>
            <select
              value={getSelectValue('tone')}
              onChange={(e) => handleInputChange('tone', e.target.value || undefined)}
              disabled={!customize}
              className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Use default</option>
              {toneOptions.map((opt, idx) => (
                <option key={`${opt.value}-${idx}`} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Post Length
              <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('format')})</span>
            </label>
            <select
              value={getSelectValue('format')}
              onChange={(e) => handleInputChange('format', e.target.value || undefined)}
              disabled={!customize}
              className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Use default</option>
              {formatOptions.map((opt, idx) => {
                const suffix = opt.label.includes('(') ? '' : ` (${getFormatLength(String(opt.value))})`;
                return (
                  <option key={`${opt.value}-${idx}`} value={opt.value}>
                    {opt.label}{suffix}
                  </option>
                );
              })}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Target Audience
              <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('audience')})</span>
            </label>
            <select
              value={getSelectValue('audience')}
              onChange={(e) => handleInputChange('audience', e.target.value || undefined)}
              disabled={!customize}
              className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Use default</option>
              {audienceOptions.map((opt, idx) => (
                <option key={`${opt.value}-${idx}`} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Post Goal
              <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('goal')})</span>
            </label>
            <select
              value={getSelectValue('goal')}
              onChange={(e) => handleInputChange('goal', e.target.value || undefined)}
              disabled={!customize}
              className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Use default</option>
              {goalOptions.map((opt, idx) => (
                <option key={`${opt.value}-${idx}`} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          disabled={!customize}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] transition-colors hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
            {showAdvanced ? 'expand_more' : 'chevron_right'}
          </span>
          Advanced Options
        </button>

        <AnimatePresence initial={false}>
        {showAdvanced && (
          <motion.div
            key="advanced-options"
            initial={{ opacity: 0, height: 0, y: -4 }}
            animate={{ opacity: 1, height: 'auto', y: 0 }}
            exit={{ opacity: 0, height: 0, y: -4 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden"
          >
          <div className="grid grid-cols-1 gap-4 rounded-xl border border-[var(--glass-border)] bg-[var(--panel)] p-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Call-to-Action Style
                <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('cta_style')})</span>
              </label>
              <select
                value={getSelectValue('cta_style')}
                onChange={(e) => handleInputChange('cta_style', e.target.value || undefined)}
                disabled={!customize}
                className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="">Use default</option>
                {ctaStyleOptions.map((opt, idx) => (
                  <option key={`${opt.value}-${idx}`} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">
                Storytelling Frequency
                <span className="muted-text ml-1 text-xs">(default: {getDefaultValue('storytelling_frequency')})</span>
              </label>
              <select
                value={getSelectValue('storytelling_frequency')}
                onChange={(e) => handleInputChange('storytelling_frequency', e.target.value || undefined)}
                disabled={!customize}
                className="glass-input w-full text-sm disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="">Use default</option>
                {storytellingOptions.map((opt, idx) => (
                  <option key={`${opt.value}-${idx}`} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <label className="inline-flex items-center gap-2 text-sm muted-text">
              <input
                type="checkbox"
                id="include_emojis"
                checked={Boolean(getDisplayValue('include_emojis'))}
                onChange={(e) => handleInputChange('include_emojis', e.target.checked ? true : undefined)}
                disabled={!customize}
                className="h-4 w-4 accent-blue-500"
              />
              Include Emojis
            </label>

            <label className="inline-flex items-center gap-2 text-sm muted-text">
              <input
                type="checkbox"
                id="use_technical_jargon"
                checked={Boolean(getDisplayValue('use_technical_jargon'))}
                onChange={(e) => handleInputChange('use_technical_jargon', e.target.checked ? true : undefined)}
                disabled={!customize}
                className="h-4 w-4 accent-blue-500"
              />
              Use Technical Jargon
            </label>
          </div>
          </motion.div>
        )}
        </AnimatePresence>

        {error && (
          <div className="rounded-xl border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-500">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !formState.topic.trim()}
          className="primary-button w-full"
        >
          {submitting ? 'Generating...' : 'Generate Post'}
        </button>
      </form>

      <p className="muted-text mt-3 text-xs">
        Fields left blank use your profile defaults.
      </p>
      </motion.div>
      ) : (
        <motion.div
          key="collapsed-config"
          initial={{ opacity: 0, height: 0, y: -6 }}
          animate={{ opacity: 1, height: 'auto', y: 0 }}
          exit={{ opacity: 0, height: 0, y: -4 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="overflow-hidden"
        >
        <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--panel)] p-3">
          <p className="text-sm font-medium">Current Topic</p>
          <p className="muted-text mt-1 text-sm">{formState.topic?.trim() || 'No topic entered yet.'}</p>
        </div>
        </motion.div>
      )}
      </AnimatePresence>

      {showProfileModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          onClick={() => setShowProfileModal(false)}
        >
          <div className="glass-card w-full max-w-2xl p-5 md:p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Your Profile</h3>
              <button
                type="button"
                onClick={() => setShowProfileModal(false)}
                className="ghost-button px-3 py-1.5 text-xs"
              >
                Close
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
              <div>
                <p className="muted-text text-xs">Name</p>
                <p className="font-medium">{profile.name}</p>
              </div>
              <div>
                <p className="muted-text text-xs">Role</p>
                <p className="font-medium">{profile.role}</p>
              </div>
              <div>
                <p className="muted-text text-xs">Organization</p>
                <p className="font-medium">{profile.organization}</p>
              </div>
              <div>
                <p className="muted-text text-xs">Experience</p>
                <p className="font-medium">{profile.experience_years} years</p>
              </div>
              <div className="md:col-span-2">
                <p className="muted-text mb-2 text-xs">Industries</p>
                <div className="flex flex-wrap gap-2">
                  {(profile.industries ?? []).length > 0 ? (
                    (profile.industries ?? []).map((industry, idx) => (
                      <span key={idx} className="status-pill text-xs">
                        {industry}
                      </span>
                    ))
                  ) : (
                    <span className="muted-text text-xs">Not specified</span>
                  )}
                </div>
              </div>
              <div className="md:col-span-2">
                <p className="muted-text mb-2 text-xs">Tech Stack</p>
                <div className="flex flex-wrap gap-2">
                  {(profile.tech_stack ?? []).length > 0 ? (
                    (profile.tech_stack ?? []).map((tech, idx) => (
                      <span key={idx} className="status-pill text-xs">
                        {tech}
                      </span>
                    ))
                  ) : (
                    <span className="muted-text text-xs">Not specified</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Helper function to display format word ranges
 */
function getFormatLength(format: string): string {
  const formatLengths: Record<string, string> = {
    short: '80-150 words',
    medium: '150-280 words',
    long: '280-400 words',
    article: '400-600 words',
  };
  return formatLengths[format] || '~150 words';
}

export default LinkedInConfigForm;

function normalizeProfile(rawProfile: any, configProfile?: ConfigurationOptions['user_profile']): UserProfile {
  const identity = rawProfile?.identity ?? {};
  const technical = rawProfile?.technical ?? {};

  const name = rawProfile?.name ?? configProfile?.name ?? identity.name ?? 'Author';
  const role = rawProfile?.role ?? configProfile?.role ?? identity.job_role ?? 'Tech Professional';
  const organization = rawProfile?.organization ?? configProfile?.organization ?? identity.organization ?? 'Tech Company';
  const experienceYears = rawProfile?.experience_years ?? configProfile?.experience_years ?? identity.years_experience ?? 0;

  const industriesRaw =
    rawProfile?.industries ??
    configProfile?.industries ??
    (typeof identity.industry === 'string' ? identity.industry.split(',') : []);
  const industries = Array.isArray(industriesRaw)
    ? industriesRaw.map((item) => String(item).trim()).filter(Boolean)
    : [];

  const techStackRaw = rawProfile?.tech_stack ?? configProfile?.tech_stack ?? technical.tech_stack ?? [];
  const techStack = Array.isArray(techStackRaw)
    ? techStackRaw.map((item) => String(item).trim()).filter(Boolean)
    : [];

  return {
    name,
    role,
    organization,
    industries,
    experience_years: Number(experienceYears) || 0,
    tech_stack: techStack,
  };
}
