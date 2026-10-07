import { useRef, useState, type ReactNode } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { z } from 'zod';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { errorMessage } from '../../lib/api';
import { profileApi, type Draft, type Facts, type Preferences, type Snapshot } from './api';
const criterion = z.object({
  id: z.string().uuid(),
  kind: z.enum([
    'capability',
    'seniority',
    'employment',
    'location',
    'remote',
    'compensation',
    'other',
  ]),
  description: z.string().trim().min(1, 'Describe this preference.'),
  strength: z.enum(['preferred', 'required']),
});
const employment = z.object({
  employer: z.string(),
  title: z.string(),
  start: z.string(),
  end: z.string(),
  ongoing: z.boolean(),
  responsibilities: z.string(),
});
const schema = z
  .object({
    summary: z.string().trim().min(1, 'Add a reviewed professional summary.').max(5000),
    desiredRoles: z.string().trim().min(1, 'Choose at least one desired role.'),
    domainMode: z.enum(['open', 'expand', 'focus']),
    domains: z.string(),
    skills: z.string(),
    industries: z.string(),
    qualifications: z.string(),
    languages: z.string(),
    employment: z.array(employment),
    criteria: z.array(criterion),
    excludedFunctions: z.string(),
    goals: z.string(),
    threshold: z.number().int().min(0).max(100),
    experienceOverride: z
      .string()
      .refine(
        (v) => v === '' || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 100),
        'Enter a number between 0 and 100, or leave blank.',
      ),
  })
  .superRefine((data, ctx) => {
    if (data.domainMode !== 'open' && !data.domains.trim())
      ctx.addIssue({
        code: 'custom',
        path: ['domains'],
        message: 'Choose domains, or select Open to any domain.',
      });
  });
type Values = z.infer<typeof schema>;
const split = (value: string) =>
  value
    .split('\n')
    .map((v) => v.trim())
    .filter(Boolean);
const factText = (values: Facts['skills']) => (values ?? []).map((v) => v.value).join('\n');
function defaults(facts: Facts, prefs: Preferences): Values {
  return {
    summary: facts.summary ?? '',
    desiredRoles: (prefs.desired_roles ?? []).join('\n'),
    domainMode: prefs.domain_mode ?? 'open',
    domains: (prefs.domains ?? []).join('\n'),
    skills: factText(facts.skills),
    industries: factText(facts.industries),
    qualifications: factText(facts.qualifications),
    languages: factText(facts.languages),
    employment: (facts.employment ?? []).map((e) => ({
      employer: e.employer,
      title: e.title,
      start: e.start ?? '',
      end: e.end ?? '',
      ongoing: e.ongoing ?? false,
      responsibilities: factText(e.responsibilities),
    })),
    criteria: (prefs.criteria ?? []).map((c) => ({ ...c, strength: c.strength ?? 'preferred' })),
    excludedFunctions: (prefs.excluded_functions ?? []).join('\n'),
    goals: prefs.goals ?? '',
    threshold: prefs.relevance_threshold ?? 30,
    experienceOverride:
      facts.experience_years_override == null ? '' : String(facts.experience_years_override),
  };
}
function factsFrom(values: Values, old: Facts): Facts {
  const facts = (text: string, previous: Facts['skills']) =>
    split(text).map(
      (value) =>
        previous?.find((f) => f.value === value) ?? {
          value,
          origin: 'user' as const,
          evidence: [],
        },
    );
  return {
    ...old,
    summary: values.summary,
    summary_evidence: values.summary === old.summary ? old.summary_evidence : [],
    skills: facts(values.skills, old.skills),
    industries: facts(values.industries, old.industries),
    qualifications: facts(values.qualifications, old.qualifications),
    languages: facts(values.languages, old.languages),
    experience_years_override:
      values.experienceOverride === '' ? null : Number(values.experienceOverride),
    employment: values.employment.map((role, index) => {
      const previous = old.employment?.[index];
      const candidate = {
        ...role,
        start: role.start || null,
        end: role.ongoing ? null : role.end || null,
        responsibilities: facts(role.responsibilities, previous?.responsibilities),
      };
      const unchanged =
        previous &&
        previous.employer === role.employer &&
        previous.title === role.title &&
        previous.start === candidate.start &&
        previous.end === candidate.end &&
        (previous.ongoing ?? false) === role.ongoing &&
        factText(previous.responsibilities) === role.responsibilities;
      return {
        ...candidate,
        origin: unchanged ? previous.origin : 'user',
        evidence: unchanged ? previous.evidence : [],
      };
    }),
  };
}
function Field({
  id,
  label,
  error,
  help,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {help && (
        <p className="field-help" id={`${id}-help`}>
          {help}
        </p>
      )}
      {error && (
        <p className="field-error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}
export function ProfileEditor({
  initial,
  draft,
  csrf,
  onSaved,
}: {
  initial: Snapshot | Draft;
  draft?: Draft;
  csrf: string;
  onSaved: () => void;
}) {
  const [draftVersion, setDraftVersion] = useState(draft?.version ?? 0);
  const [message, setMessage] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const alert = useRef<HTMLDivElement>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: defaults(initial.facts, initial.preferences),
  });
  const roles = useFieldArray({ control: form.control, name: 'employment' });
  const criteria = useFieldArray({ control: form.control, name: 'criteria', keyName: 'formKey' });
  const {
    register,
    formState: { errors },
  } = form;
  const save = useMutation({
    mutationFn: async ({ values, activate }: { values: Values; activate: boolean }) => {
      const body = {
        facts: factsFrom(values, initial.facts),
        preferences: {
          ...initial.preferences,
          desired_roles: split(values.desiredRoles),
          domain_mode: values.domainMode,
          domains: split(values.domains),
          criteria: values.criteria,
          excluded_functions: split(values.excludedFunctions),
          goals: values.goals,
          relevance_threshold: values.threshold,
        },
      };
      if (draft) {
        const saved = await profileApi.saveDraft(draft.id, draftVersion, body, csrf);
        setDraftVersion(saved.version);
        if (activate) {
          await profileApi.activate(draft.id, saved.version, draft.base_revision, csrf);
          return true;
        }
        return false;
      }
      await profileApi.save((initial as Snapshot).revision, body, csrf);
      return true;
    },
    onSuccess: (active) => {
      setMessage(
        active
          ? 'Profile saved. Matching will update as processing completes.'
          : 'Draft saved. Your active profile is unchanged.',
      );
      if (active) onSaved();
    },
    onError: () => requestAnimationFrame(() => alert.current?.focus()),
  });
  const submit = (activate: boolean) =>
    form.handleSubmit((values) => {
      setMessage('');
      save.mutate({ values, activate });
    });
  const comparison = draft?.base_profile;
  return (
    <form className="profile-form" onSubmit={submit(true)} noValidate>
      {save.isError && (
        <div role="alert" tabIndex={-1} ref={alert} className="error">
          {errorMessage(save.error)} Your edits are still here. If another tab saved changes, open
          the current profile in a new tab to compare before starting a fresh review.
        </div>
      )}
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {draft && comparison && comparison.revision > 0 && (
        <section className="panel">
          <h2>Review the changes</h2>
          <p className="muted">
            This CV creates a new draft. Your saved preferences are preserved. Keep individual
            sections from the current profile where needed.
          </p>
          <details className="comparison">
            <summary>Compare with profile revision {comparison.revision}</summary>
            {(
              [
                'summary',
                'employment',
                'skills',
                'industries',
                'qualifications',
                'languages',
              ] as const
            ).map((key) => {
              const previous = defaults(comparison.facts, comparison.preferences);
              const value = previous[key];
              return (
                <div key={key} className="comparison-row">
                  <h3>
                    {key === 'employment'
                      ? 'Work history'
                      : key.charAt(0).toUpperCase() + key.slice(1)}
                  </h3>
                  <p className="preserve-lines">
                    {typeof value === 'string'
                      ? value || 'Not specified'
                      : value
                          .map(
                            (e) =>
                              `${e.title} · ${e.employer} (${e.start || '?'} – ${e.ongoing ? 'present' : e.end || '?'})`,
                          )
                          .join('\n') || 'Not specified'}
                  </p>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => form.setValue(key, previous[key], { shouldDirty: true })}
                  >
                    Keep saved {key === 'employment' ? 'work history' : key}
                  </Button>
                </div>
              );
            })}
          </details>
        </section>
      )}
      <section className="panel">
        <h2>Experience</h2>
        <p className="section-intro">
          Review what the CV says about your past work. Correct anything missing or uncertain.
        </p>
        <Field id="profile-summary" label="Professional summary" error={errors.summary?.message}>
          <textarea
            id="profile-summary"
            rows={4}
            aria-invalid={!!errors.summary}
            aria-describedby={errors.summary ? 'profile-summary-error' : undefined}
            {...register('summary')}
          />
        </Field>
        <fieldset className="work-history">
          <legend>Work history</legend>
          {roles.fields.map((role, index) => (
            <div className="role-editor" key={role.id}>
              <div className="form-grid">
                <Field id={`employer-${index}`} label="Company or organisation">
                  <input id={`employer-${index}`} {...register(`employment.${index}.employer`)} />
                </Field>
                <Field id={`title-${index}`} label="Role title">
                  <input id={`title-${index}`} {...register(`employment.${index}.title`)} />
                </Field>
                <Field
                  id={`start-${index}`}
                  label="Start date"
                  help="Use YYYY, YYYY-MM, or YYYY-MM-DD."
                >
                  <input
                    id={`start-${index}`}
                    placeholder="2020-03"
                    {...register(`employment.${index}.start`)}
                  />
                </Field>
                <Field id={`end-${index}`} label="End date" help="Leave unknown dates blank.">
                  <input
                    id={`end-${index}`}
                    disabled={form.watch(`employment.${index}.ongoing`)}
                    {...register(`employment.${index}.end`)}
                  />
                </Field>
              </div>
              <label className="check-label">
                <input type="checkbox" {...register(`employment.${index}.ongoing`)} />I currently
                work here
              </label>
              <Field id={`responsibilities-${index}`} label="Responsibilities — one per line">
                <textarea
                  id={`responsibilities-${index}`}
                  rows={3}
                  {...register(`employment.${index}.responsibilities`)}
                />
              </Field>
              <Button type="button" variant="quiet" onClick={() => roles.remove(index)}>
                <Trash2 size={16} aria-hidden="true" />
                Remove role {index + 1}
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              roles.append({
                employer: '',
                title: '',
                start: '',
                end: '',
                ongoing: false,
                responsibilities: '',
              })
            }
          >
            <Plus size={16} aria-hidden="true" />
            Add role
          </Button>
        </fieldset>
        <div className="form-grid">
          {(['skills', 'industries', 'qualifications', 'languages'] as const).map((key) => (
            <Field
              key={key}
              id={`profile-${key}`}
              label={`${key.charAt(0).toUpperCase() + key.slice(1)} — one per line`}
            >
              <textarea id={`profile-${key}`} rows={3} {...register(key)} />
            </Field>
          ))}
        </div>
        <details>
          <summary>Experience estimate</summary>
          <p className="field-help">
            Experience is calculated from the union of dated roles, so overlapping roles are not
            counted twice. Imprecise or missing dates remain uncertain.
          </p>
          <Field
            id="experience-override"
            label="Your own years-of-experience estimate (optional)"
            error={errors.experienceOverride?.message}
          >
            <input
              id="experience-override"
              type="number"
              min="0"
              max="100"
              step="0.1"
              {...register('experienceOverride')}
            />
          </Field>
        </details>
      </section>
      <section className="panel">
        <h2>Preferences</h2>
        <p className="section-intro">
          Describe what you want next. These choices can extend beyond your CV.
        </p>
        <Field
          id="desired-roles"
          label="Desired roles or functions — one per line"
          error={errors.desiredRoles?.message}
        >
          <textarea
            id="desired-roles"
            rows={3}
            aria-invalid={!!errors.desiredRoles}
            aria-describedby={errors.desiredRoles ? 'desired-roles-error' : undefined}
            {...register('desiredRoles')}
          />
        </Field>
        <fieldset className="domain-choices">
          <legend>Which domains would you like to explore?</legend>
          {[
            {
              value: 'open',
              label: 'Open to any domain',
              help: 'Explore any industry where your experience can transfer.',
            },
            {
              value: 'expand',
              label: 'Prefer selected domains, explore others',
              help: 'Keep familiar industries in view while considering new ones.',
            },
            {
              value: 'focus',
              label: 'Focus on selected domains',
              help: 'Treat your selected domains as a requirement.',
            },
          ].map((item) => (
            <label className="radio-option" key={item.value}>
              <input
                type="radio"
                value={item.value}
                aria-labelledby={`domain-${item.value}-label`}
                aria-describedby={`domain-${item.value}-help`}
                {...register('domainMode')}
              />
              <span>
                <strong id={`domain-${item.value}-label`}>{item.label}</strong>
                <span className="field-help" id={`domain-${item.value}-help`}>
                  {item.help}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
        {form.watch('domainMode') !== 'open' && (
          <Field
            id="target-domains"
            label="Selected domains — one per line"
            error={errors.domains?.message}
          >
            <textarea id="target-domains" rows={3} {...register('domains')} />
          </Field>
        )}
        <details>
          <summary>Location, seniority and other criteria</summary>
          <p className="field-help">
            Preferences cast a wider net. Select Required only for a firm constraint; unknown
            details remain visible.
          </p>
          {criteria.fields.map((item, index) => (
            <div className="criterion-editor" key={item.formKey}>
              <Field id={`criterion-kind-${index}`} label="Preference type">
                <select id={`criterion-kind-${index}`} {...register(`criteria.${index}.kind`)}>
                  {[
                    'capability',
                    'seniority',
                    'employment',
                    'location',
                    'remote',
                    'compensation',
                    'other',
                  ].map((kind) => (
                    <option key={kind} value={kind}>
                      {kind.charAt(0).toUpperCase() + kind.slice(1)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                id={`criterion-description-${index}`}
                label="What would you like?"
                error={errors.criteria?.[index]?.description?.message}
              >
                <input
                  id={`criterion-description-${index}`}
                  {...register(`criteria.${index}.description`)}
                />
              </Field>
              <Field id={`criterion-strength-${index}`} label="Importance">
                <select
                  id={`criterion-strength-${index}`}
                  {...register(`criteria.${index}.strength`)}
                >
                  <option value="preferred">Preferred</option>
                  <option value="required">Required</option>
                </select>
              </Field>
              <Button type="button" variant="quiet" onClick={() => criteria.remove(index)}>
                Remove preference {index + 1}
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              criteria.append({
                id: crypto.randomUUID(),
                kind: 'location',
                description: '',
                strength: 'preferred',
              })
            }
          >
            Add preference
          </Button>
        </details>
        <Field id="excluded-functions" label="Functions you want to exclude — one per line">
          <textarea id="excluded-functions" rows={2} {...register('excludedFunctions')} />
        </Field>
        <Field id="career-goals" label="Anything else about your next role?">
          <textarea id="career-goals" rows={3} {...register('goals')} />
        </Field>
        <details>
          <summary>Broad shortlist threshold</summary>
          <p className="field-help">
            The default of 30 casts a wide net. This is approximate relevance, not a probability of
            success. Clearly unrelated functions remain excluded.
          </p>
          <Field
            id="relevance-threshold"
            label="Minimum relevance (0–100)"
            error={errors.threshold?.message}
          >
            <input
              id="relevance-threshold"
              type="number"
              min="0"
              max="100"
              {...register('threshold', { valueAsNumber: true })}
            />
          </Field>
        </details>
      </section>
      <div className="form-actions">
        <label className="check-label">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I have reviewed my experience and preferences.
        </label>
        <div className="button-row">
          {draft && (
            <Button
              variant="secondary"
              type="button"
              disabled={save.isPending}
              onClick={submit(false)}
            >
              Save draft
            </Button>
          )}
          <Button type="submit" disabled={!confirmed || save.isPending}>
            {save.isPending ? 'Saving…' : draft ? 'Approve profile' : 'Save profile'}
          </Button>
        </div>
      </div>
      {draft?.spans && (
        <details className="panel">
          <summary>Extracted source text</summary>
          <p className="field-help">
            Use this to check missing details or reading order. The parser may read complex layouts
            differently from their visual order.
          </p>
          {draft.spans.map((span) => (
            <div key={span.id} className="source-span">
              <h3>{span.page ? `Page ${span.page}` : `Paragraph ${span.paragraph ?? span.id}`}</h3>
              <p className="preserve-lines">{span.text}</p>
            </div>
          ))}
        </details>
      )}
    </form>
  );
}
