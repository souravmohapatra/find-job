import { BillingHistory } from './billing';
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Button } from '../../components/ui/button';
import { api, errorMessage, request } from '../../lib/api';
import type { components } from '../../lib/api-types';
import { profileApi, type Accepted } from '../profile/api';

type Schemas = components['schemas'];
type Settings = Schemas['AiSettingsView'];
type Task = Schemas['TaskView'];
type Config = Schemas['TaskConfig-Output'];
const names = {
  profile_analysis: 'CV analysis',
  job_extraction: 'Job extraction',
  job_matching: 'Job matching',
};
const descriptions = {
  profile_analysis: 'Turns CV text into an evidence-backed draft for your review.',
  job_extraction: 'Reads unfamiliar career pages when a structured feed is unavailable.',
  job_matching: 'Finds broad, plausible matches using your reviewed profile and preferences.',
};
async function loadSettings() {
  return (await request('/settings/ai')) as Settings;
}
function TaskForm({ task, csrf, live }: { task: Task; csrf: string; live: boolean }) {
  const client = useQueryClient();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const [notice, setNotice] = useState('');
  const [baseRevision, setBaseRevision] = useState(task.revision);
  const [consent, setConsent] = useState(false);
  const [operationId, setOperationId] = useState<string>();
  const form = useForm<Config & { fallbackText: string; providerText: string }>({
    defaultValues: {
      ...task.config,
      fallbackText: (task.config.fallback_models ?? []).join(', '),
      providerText: (task.config.providers ?? []).join(', '),
    },
    mode: 'onBlur',
  });
  const save = useMutation({
    mutationFn: async (values: Config & { fallbackText: string; providerText: string }) => {
      const { fallbackText, providerText, ...config } = values;
      return (await request(
        '/settings/ai',
        {
          method: 'PATCH',
          headers: { 'If-Match': `"${baseRevision}"` },
          body: JSON.stringify({
            task: task.task,
            config: {
              ...config,
              model: config.model?.trim() || null,
              fallback_models: fallbackText
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
              providers: providerText
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
            },
          }),
        },
        csrf,
      )) as Settings;
    },
    onSuccess: (data) => {
      client.setQueryData(['ai-settings'], data);
      const saved = data.tasks.find((item) => item.task === task.task)!;
      setBaseRevision(saved.revision);
      form.reset({
        ...saved.config,
        fallbackText: (saved.config.fallback_models ?? []).join(', '),
        providerText: (saved.config.providers ?? []).join(', '),
      });
      setOperationId(undefined);
      setConsent(false);
      validate.reset();
      setNotice('Model settings saved.');
    },
  });
  const validate = useMutation({
    mutationFn: async () =>
      (await request(
        '/settings/ai/validate',
        { method: 'POST', body: JSON.stringify({ task: task.task, acknowledge_cost: consent }) },
        csrf,
      )) as Accepted,
    onSuccess: (data) => {
      setOperationId(data.operation_id);
      setNotice('Validation queued.');
    },
  });
  const operation = useQuery({
    queryKey: ['operation', operationId],
    queryFn: () => profileApi.operation(operationId!),
    enabled: Boolean(operationId),
    refetchInterval: (query) =>
      query.state.data && ['queued', 'running'].includes(query.state.data.state) ? 2000 : false,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    if (operation.data && ['succeeded', 'blocked', 'failed'].includes(operation.data.state)) {
      void client.invalidateQueries({ queryKey: ['ai-settings'] });
      void client.invalidateQueries({ queryKey: ['ai-usage'] });
    }
  }, [client, operation.data]);
  useEffect(() => {
    if (save.isError || validate.isError) errorRef.current?.focus();
  }, [save.isError, validate.isError]);
  const id = task.task;
  return (
    <section className="panel ai-task">
      <h3>{names[id]}</h3>
      <p className="field-help">{descriptions[id]}</p>
      <p className="field-help">
        {task.config.model
          ? `Revision ${task.revision} · ${task.validation_state.replaceAll('_', ' ')}`
          : 'No model selected'}
      </p>
      <form onSubmit={form.handleSubmit((values) => save.mutate(values))}>
        <div className="field">
          <label htmlFor={`${id}-model`}>Model ID</label>
          <input
            id={`${id}-model`}
            placeholder="author/model"
            {...form.register('model')}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <label className="checkbox-label">
          <input type="checkbox" {...form.register('zdr')} />
          Use only zero data retention endpoints
        </label>
        <details>
          <summary>Advanced model settings</summary>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={`${id}-fallback`}>Fallback model IDs</label>
              <input id={`${id}-fallback`} {...form.register('fallbackText')} />
              <p className="field-help">Optional, comma-separated. The same privacy rules apply.</p>
            </div>
            <div className="field">
              <label htmlFor={`${id}-providers`}>Provider slugs</label>
              <input id={`${id}-providers`} {...form.register('providerText')} />
              <p className="field-help">
                Optional, comma-separated. Leave blank for compatible providers.
              </p>
            </div>
            {(
              [
                { key: 'input_tokens', label: 'Input token limit', min: 1000, max: 200000 },
                { key: 'output_tokens', label: 'Output token limit', min: 256, max: 32000 },
                { key: 'timeout_seconds', label: 'Timeout (seconds)', min: 10, max: 120 },
              ] as const
            ).map((item) => (
              <div className="field" key={item.key}>
                <label htmlFor={`${id}-${item.key}`}>{item.label}</label>
                <input
                  id={`${id}-${item.key}`}
                  type="number"
                  min={item.min}
                  max={item.max}
                  required
                  {...form.register(item.key, {
                    valueAsNumber: true,
                    required: true,
                    min: item.min,
                    max: item.max,
                  })}
                />
              </div>
            ))}
            <div className="field">
              <label htmlFor={`${id}-temperature`}>Temperature (optional)</label>
              <input
                id={`${id}-temperature`}
                type="number"
                min="0"
                max="2"
                step="0.1"
                {...form.register('temperature', {
                  setValueAs: (value) => (value == null || value === '' ? null : Number(value)),
                })}
              />
            </div>
            <div className="field">
              <label htmlFor={`${id}-reasoning`}>Reasoning effort</label>
              <select
                id={`${id}-reasoning`}
                {...form.register('reasoning_effort', {
                  setValueAs: (value) => (value === '' ? null : value),
                })}
              >
                <option value="">Provider default</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            {(
              [
                { key: 'prompt_price', label: 'Input price ceiling (USD / million tokens)' },
                { key: 'completion_price', label: 'Output price ceiling (USD / million tokens)' },
                { key: 'request_price', label: 'Request fee ceiling (USD)' },
              ] as const
            ).map((item) => (
              <div className="field" key={item.key}>
                <label htmlFor={`${id}-${item.key}`}>{item.label}</label>
                <input
                  id={`${id}-${item.key}`}
                  type="number"
                  min="0"
                  step="0.000001"
                  required
                  {...form.register(item.key)}
                />
              </div>
            ))}
          </div>
        </details>
        {(save.isError || validate.isError) && (
          <p ref={errorRef} role="alert" tabIndex={-1}>
            {errorMessage(save.error || validate.error)} Your inputs are preserved.
          </p>
        )}
        {baseRevision !== task.revision && (
          <p role="alert">
            A newer configuration is available. Your edits are preserved.{' '}
            <Button
              variant="quiet"
              type="button"
              onClick={() => {
                form.reset({
                  ...task.config,
                  fallbackText: (task.config.fallback_models ?? []).join(', '),
                  providerText: (task.config.providers ?? []).join(', '),
                });
                setBaseRevision(task.revision);
                save.reset();
              }}
            >
              Replace edits with saved settings
            </Button>
          </p>
        )}
        <div className="button-row">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? 'Saving…' : `Save ${names[id].toLowerCase()}`}
          </Button>
        </div>
      </form>
      {live && (
        <label className="checkbox-label">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          Allow a synthetic validation request that may incur API cost
        </label>
      )}
      <Button
        variant="secondary"
        onClick={() => validate.mutate()}
        disabled={
          !task.config.model ||
          form.formState.isDirty ||
          baseRevision !== task.revision ||
          validate.isPending ||
          (live && !consent) ||
          ['queued', 'running'].includes(operation.data?.state ?? '')
        }
      >
        {live ? 'Validate saved model' : 'Check mock configuration'}
      </Button>
      <p role="status">
        {operation.data
          ? operation.data.state === 'succeeded'
            ? live
              ? 'Synthetic validation passed. This does not verify matching quality.'
              : 'Mock configuration checked. No provider request was made.'
            : operation.data.error_message || operation.data.progress
          : notice}
      </p>
      {operation.isError && <p role="alert">{errorMessage(operation.error)}</p>}
    </section>
  );
}
function LimitsForm({ settings, csrf }: { settings: Settings; csrf: string }) {
  const client = useQueryClient();
  const form = useForm({ defaultValues: settings.limits, mode: 'onBlur' });
  const [revision, setRevision] = useState(settings.limits_revision);
  const save = useMutation({
    mutationFn: (values: Settings['limits']) =>
      request(
        '/settings/ai/limits',
        {
          method: 'PATCH',
          headers: { 'If-Match': `"${revision}"` },
          body: JSON.stringify(values),
        },
        csrf,
      ),
    onSuccess: (data) => {
      const saved = data as Settings;
      client.setQueryData(['ai-settings'], saved);
      setRevision(saved.limits_revision);
      form.reset(saved.limits);
    },
  });
  return (
    <section className="panel">
      <h3>Daily limits</h3>
      <p className="field-help">
        Resets at midnight UTC. Each retry and repair counts. Unresolved charges keep their
        reservation. Set a provider key spending limit as an additional safeguard.
      </p>
      <form onSubmit={form.handleSubmit((values) => save.mutate(values))}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="daily-calls">Calls per day</label>
            <input
              id="daily-calls"
              type="number"
              min="1"
              max="10000"
              required
              {...form.register('daily_calls', { valueAsNumber: true })}
            />
          </div>
          <div className="field">
            <label htmlFor="daily-usd">Estimated spend per day (USD)</label>
            <input
              id="daily-usd"
              type="number"
              min="0.000001"
              max="1000"
              step="0.000001"
              required
              {...form.register('daily_usd')}
            />
          </div>
        </div>
        {save.isError && <p role="alert">{errorMessage(save.error)}</p>}
        <Button disabled={save.isPending}>Save daily limits</Button>
        {save.isSuccess && <p role="status">Daily limits saved.</p>}
      </form>
    </section>
  );
}
type Usage = Schemas['UsageView'];
export function AiSettings() {
  const session = useQuery({ queryKey: ['session'], queryFn: api.session, staleTime: 30000 });
  const settings = useQuery({ queryKey: ['ai-settings'], queryFn: loadSettings });
  const usage = useQuery({
    queryKey: ['ai-usage'],
    queryFn: async () => (await request('/settings/ai/usage')) as Usage,
  });
  if (settings.isPending) return <p role="status">Loading AI settings…</p>;
  if (settings.isError)
    return (
      <section className="panel">
        <h2>AI settings</h2>
        <p role="alert">{errorMessage(settings.error)}</p>
        <Button onClick={() => void settings.refetch()}>Reload AI settings</Button>
      </section>
    );
  return (
    <div className="ai-settings">
      <h2>AI models</h2>
      <p>
        Choose a model independently for each task. Saving a choice does not make a paid request.
      </p>
      <p className="notice">
        {settings.data.integration_mode === 'mock'
          ? 'Mock mode: no requests are sent to OpenRouter.'
          : settings.data.key_configured
            ? 'OpenRouter key configured on the server.'
            : 'OpenRouter key is not configured on the server.'}{' '}
        CV analysis and matching in live mode send professional text to OpenRouter and its routed
        provider. Data-collection providers are excluded by default; this is not a guarantee of
        anonymity.
      </p>
      {settings.data.tasks.map((task) => (
        <TaskForm
          key={task.task}
          task={task}
          csrf={session.data!.csrf_token}
          live={settings.data.integration_mode === 'live'}
        />
      ))}
      <LimitsForm settings={settings.data} csrf={session.data!.csrf_token} />
      <section className="panel">
        <h3>Usage today (UTC)</h3>
        <p className="field-help">Held amounts include unresolved requests from earlier days.</p>
        {usage.isPending ? (
          <p role="status">Loading usage…</p>
        ) : usage.isError ? (
          <>
            <p role="alert">{errorMessage(usage.error)}</p>
            <Button onClick={() => void usage.refetch()}>Reload usage</Button>
          </>
        ) : (
          <dl className="settings-list">
            {usage.data.tasks.map((task) => (
              <div key={task.task}>
                <dt>{names[task.task]}</dt>
                <dd>
                  {task.calls_today} calls · ${Number(task.reported_usd).toFixed(4)} recorded · $
                  {Number(task.held_usd).toFixed(4)} held
                  {task.unresolved_count > 0 && (
                    <p>
                      {task.unresolved_count} unresolved requests. This task is paused pending
                      billing reconciliation.
                    </p>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>
      {usage.data && (
        <BillingHistory
          usage={usage.data}
          names={names}
          csrf={session.data!.csrf_token}
          live={settings.data.integration_mode === 'live'}
        />
      )}
    </div>
  );
}
