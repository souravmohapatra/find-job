import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/ui/button';
import { ApiError, request } from '../../lib/api';
import { date, read, useCsrf, type Schemas } from './data';
import { Failure } from './shared';

type Rules = Schemas['SelectorRules'];
type Draft = { base: number; custom: boolean; rules: Rules };
const fields = [
  ['cards', 'Job cards', '.job-card'],
  ['title', 'Job title', 'h2'],
  ['link', 'Job detail link', 'a'],
  ['description', 'Job description', '.description'],
  ['employer', 'Employer name', '.employer'],
  ['location', 'Location', '.location'],
  ['next_page', 'Next-page link', 'a.next'],
  ['empty', 'No-vacancies message', '.no-vacancies'],
  ['closed', 'Closed-job marker', '.closed'],
  ['valid_through', 'Closing date', 'time'],
] as const;
const initial = (source: Schemas['SourceView']): Draft => ({
  base: source.revision,
  custom: Boolean(source.rules),
  rules: source.rules ?? {
    cards: '',
    title: '',
    link: '',
    description: '',
    employer: '',
    employer_scope: 'card',
  },
});

export function SourceRules({ source }: { source: Schemas['SourceView'] }) {
  const csrf = useCsrf();
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [latest, setLatest] = useState<Schemas['SourceView'] | null>(null);
  const current = draft ?? initial(source);
  const preview = useMutation({
    mutationFn: (value: Draft) =>
      request(
        `/sources/${source.id}/rules/preview`,
        {
          method: 'POST',
          headers: { 'If-Match': `"${value.base}"` },
          body: JSON.stringify({ rules: value.custom ? value.rules : null }),
        },
        csrf,
      ) as Promise<Schemas['RulesPreview']>,
  });
  const save = useMutation({
    mutationFn: (value: Draft) =>
      request(
        `/sources/${source.id}/rules`,
        {
          method: 'PUT',
          headers: { 'If-Match': `"${value.base}"` },
          body: JSON.stringify({ rules: value.custom ? value.rules : null }),
        },
        csrf,
      ) as Promise<Schemas['SourceView']>,
    onSuccess: async (saved) => {
      client.setQueryData<Schemas['SourceView'][]>(['sources', source.company_id], (rows) =>
        rows?.map((row) => (row.id === saved.id ? saved : row)),
      );
      setDraft(null);
      setLatest(null);
      preview.reset();
      await Promise.all([
        client.invalidateQueries({ queryKey: ['sources', source.company_id] }),
        client.invalidateQueries({ queryKey: ['company', source.company_id] }),
        client.invalidateQueries({ queryKey: ['companies'] }),
      ]);
    },
  });
  const compare = useMutation({
    mutationFn: () => read<Schemas['SourceView'][]>(`/companies/${source.company_id}/sources`),
    onSuccess: (rows) => {
      const saved = rows.find((row) => row.id === source.id);
      if (saved) setLatest(saved);
    },
  });
  const pending = save.isPending || preview.isPending || compare.isPending;
  const conflict = [save.error, preview.error].some(
    (error) => error instanceof ApiError && error.code === 'revision_conflict',
  );
  const change = (value: Draft) => {
    setDraft(value);
    preview.reset();
    save.reset();
    setLatest(null);
  };
  const input = ([key, label, example]: (typeof fields)[number], required: boolean) => (
    <div className="field" key={key}>
      <label htmlFor={`${source.id}-rule-${key}`}>
        {label}
        {required ? '' : ' (optional)'}
      </label>
      <input
        id={`${source.id}-rule-${key}`}
        required={required}
        maxLength={256}
        autoComplete="off"
        spellCheck={false}
        value={current.rules[key] ?? ''}
        placeholder={`For example: ${example}`}
        onChange={(e) =>
          change({
            ...current,
            rules: { ...current.rules, [key]: e.target.value || (required ? '' : null) },
          })
        }
      />
    </div>
  );
  return (
    <details className="source-rules">
      <summary>Website extraction rules (advanced)</summary>
      <p>
        Use custom rules when automatic extraction cannot read this website. Rules identify elements
        in the page using simple CSS selectors.
      </p>
      <form
        className="inventory-form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(current);
        }}
      >
        <fieldset disabled={pending}>
          <legend>Extraction method</legend>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={current.custom}
              onChange={(e) => change({ ...current, custom: e.target.checked })}
            />
            Use custom extraction rules
          </label>
          {!current.custom && (
            <p>
              Automatic extraction uses structured job data or AI when needed. Save to remove any
              custom rules.
            </p>
          )}
          {current.custom && (
            <>
              <p className="field-help">
                Select repeated job cards, then one title, link, description and employer within
                each card. The employer must match this company. Use :scope when the card itself is
                the link.
              </p>
              {fields.slice(0, 5).map((field) => input(field, true))}
              <div className="field">
                <label htmlFor={`${source.id}-employer-scope`}>Find employer name in</label>
                <select
                  id={`${source.id}-employer-scope`}
                  value={current.rules.employer_scope ?? 'card'}
                  onChange={(e) =>
                    change({
                      ...current,
                      rules: {
                        ...current.rules,
                        employer_scope: e.target.value as 'card' | 'page',
                      },
                    })
                  }
                >
                  <option value="card">Each job card</option>
                  <option value="page">The whole page</option>
                </select>
              </div>
              <details>
                <summary>Optional fields and pagination</summary>
                {fields.slice(5).map((field) => input(field, false))}
                <p className="field-help">
                  Next-page links must stay on this website. A no-vacancies message must contain
                  text. Closing dates must be ISO dates. Empty website checks never close collected
                  roles.
                </p>
              </details>
            </>
          )}
        </fieldset>
        {save.isError && <Failure focus error={save.error} />}
        {preview.isError && <Failure focus error={preview.error} />}
        {compare.isError && <Failure focus error={compare.error} />}
        {conflict && (
          <div role="status">
            <p>
              This source changed. Your edits are retained. Review the saved rules before
              continuing.
            </p>
            <Button
              type="button"
              variant="secondary"
              disabled={pending}
              onClick={() => compare.mutate()}
            >
              Compare saved rules
            </Button>
          </div>
        )}
        {latest && (
          <section aria-label="Saved extraction rules" className="notice">
            <p>
              Saved revision {latest.revision}:{' '}
              {latest.rules ? 'Custom extraction' : 'Automatic extraction'}
            </p>
            {latest.rules && (
              <dl>
                {fields.map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{latest.rules?.[key] || 'Not set'}</dd>
                  </div>
                ))}
                <div>
                  <dt>Employer scope</dt>
                  <dd>{latest.rules.employer_scope ?? 'card'}</dd>
                </div>
              </dl>
            )}
            <p>
              Keeping your draft replaces the saved extraction method and rules when you next save.
              Other source settings are preserved.
            </p>
            <div className="form-actions">
              <Button
                type="button"
                variant="secondary"
                disabled={pending}
                onClick={() => change(initial(latest))}
              >
                Use saved rules
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={pending}
                onClick={() => change({ ...current, base: latest.revision })}
              >
                Keep my draft for review
              </Button>
            </div>
          </section>
        )}
        {preview.data && (
          <section aria-label="Extraction preview" role="status" className="notice">
            <p>
              {preview.data.accepted_jobs} verified{' '}
              {preview.data.accepted_jobs === 1 ? 'job' : 'jobs'} found in the saved page from{' '}
              {date(preview.data.fetched_at)}.
            </p>
            <p>
              {preview.data.complete
                ? 'This page parsed successfully; company coverage may still be partial.'
                : 'Coverage is incomplete. Review the rules and issues below.'}
            </p>
            {preview.data.examples.length > 0 && (
              <ul>
                {preview.data.examples.map((title, index) => (
                  <li key={index}>{title}</li>
                ))}
              </ul>
            )}
            {preview.data.issues.length > 0 && (
              <ul>
                {preview.data.issues.map((issue) => (
                  <li key={issue}>{issue.replaceAll('_', ' ')}</li>
                ))}
              </ul>
            )}
          </section>
        )}
        {save.isSuccess && (
          <p role="status">Extraction rules saved. They apply to the next source check.</p>
        )}
        <p className="field-help">
          Preview reads a recent saved page without fetching the website or calling AI. If no saved
          page is available, run a company check first. Some websites do not allow a reusable saved
          page.
        </p>
        <div className="form-actions">
          {current.custom && (
            <Button
              type="button"
              variant="secondary"
              disabled={pending}
              onClick={(e) => {
                if (e.currentTarget.form?.reportValidity()) {
                  setDraft(current);
                  preview.mutate(current);
                }
              }}
            >
              {preview.isPending ? 'Previewing…' : 'Preview saved page'}
            </Button>
          )}
          <Button disabled={pending}>{save.isPending ? 'Saving…' : 'Save extraction rules'}</Button>
        </div>
      </form>
    </details>
  );
}
