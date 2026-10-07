import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';
import { Failure, OperationStatus } from './shared';
import { DiscoveryHistory } from './discovery';
import { CompanyCoverage } from './coverage';
import { JobList } from './jobs';
import { SourceRules } from './source-rules';
import { date, read, useCsrf, type Schemas } from './data';

export function CompaniesPage() {
  const csrf = useCsrf();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [label, setLabel] = useState('');
  const [website, setWebsite] = useState('');
  const [interval, setInterval] = useState(24);
  const companies = useInfiniteQuery({
    queryKey: ['companies'],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => read<Schemas['CompanyPage']>(`/companies?offset=${pageParam}`),
    getNextPageParam: (page) => page.next_offset ?? undefined,
  });
  const create = useMutation({
    mutationFn: () =>
      request(
        '/companies',
        {
          method: 'POST',
          body: JSON.stringify({ label, website: website || null, interval_hours: interval }),
        },
        csrf,
      ) as Promise<Schemas['OperationAccepted']>,
    onSuccess: async (data) => {
      await client.invalidateQueries({ queryKey: ['companies'] });
      navigate(`/companies/${data.resource_id}`, { state: { operationId: data.operation_id } });
    },
  });
  return (
    <>
      <p className="eyebrow">YOUR WATCHLIST</p>
      <h1 tabIndex={-1}>Companies</h1>
      <p className="page-description">
        Choose companies to follow. Every collected role remains available to browse.
      </p>
      <section className="panel">
        <h2>Follow a company</h2>
        <form
          className="inventory-form"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="company-name">Company name</label>
            <input
              id="company-name"
              required
              maxLength={200}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="company-website">Website or careers URL (optional)</label>
            <input
              id="company-website"
              type="url"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </div>
          <Interval value={interval} onChange={setInterval} id="new-interval" />
          {create.isError && <Failure focus error={create.error} />}
          <Button disabled={create.isPending}>
            {create.isPending ? 'Saving…' : 'Follow company'}
          </Button>
        </form>
      </section>
      <section aria-labelledby="watchlist-title">
        <h2 id="watchlist-title">Your companies</h2>
        {companies.isPending && <p role="status">Loading companies…</p>}
        {companies.isError && (
          <Failure error={companies.error} retry={() => void companies.refetch()} />
        )}
        {companies.data?.pages
          .flatMap((page) => page.items)
          .map((company) => (
            <article className="panel inventory-row" key={company.id}>
              <div>
                <h3>
                  <Link to={`/companies/${company.id}`}>{company.label}</Link>
                </h3>
                <p>
                  {company.paused ? 'Paused' : `Every ${company.interval_hours} hours`} ·{' '}
                  {company.resolution === 'unresolved'
                    ? 'Source discovery unresolved'
                    : company.resolution === 'needs_review'
                      ? 'Company identity needs review'
                      : company.resolution.replaceAll('_', ' ')}
                </p>
                <CompanyCoverage company={company} />
              </div>
              <Link to={`/jobs?view=all&availability=all&company_id=${company.id}`}>
                All collected jobs
              </Link>
            </article>
          ))}
        {companies.data?.pages[0].items.length === 0 && (
          <p>No companies followed yet. Add one above to start your watchlist.</p>
        )}
        {companies.hasNextPage && (
          <Button
            variant="secondary"
            disabled={companies.isFetchingNextPage}
            onClick={() => void companies.fetchNextPage()}
          >
            Load more companies
          </Button>
        )}
      </section>
    </>
  );
}
function Interval({
  value,
  onChange,
  id,
}: {
  value: number;
  onChange: (value: number) => void;
  id: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>Check interval (hours)</label>
      <input
        id={id}
        type="number"
        min={1}
        max={720}
        required
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <p className="field-help">
        24 for daily, 12 for twice daily; 1–720 hours. Notifications use a separate schedule.
      </p>
    </div>
  );
}
function CompanyEditor({ company }: { company: Schemas['CompanyView'] }) {
  const csrf = useCsrf();
  const client = useQueryClient();
  const [draft, setDraft] = useState<{
    base: number;
    label: string;
    website: string;
    interval: number;
    paused: boolean;
  } | null>(null);
  const current = draft ?? {
    base: company.revision,
    label: company.label,
    website: company.website ?? '',
    interval: company.interval_hours ?? 24,
    paused: company.paused ?? false,
  };
  const { base, label, website, interval, paused } = current;
  const setLabel = (value: string) => setDraft({ ...current, label: value });
  const setWebsite = (value: string) => setDraft({ ...current, website: value });
  const setInterval = (value: number) => setDraft({ ...current, interval: value });
  const setPaused = (value: boolean) => setDraft({ ...current, paused: value });
  const save = useMutation({
    mutationFn: () =>
      request(
        `/companies/${company.id}`,
        {
          method: 'PATCH',
          headers: { 'If-Match': `"${base}"` },
          body: JSON.stringify({
            label,
            website: website || null,
            interval_hours: interval,
            paused,
          }),
        },
        csrf,
      ),
    onSuccess: async (data) => {
      client.setQueryData(['company', company.id], data);
      setDraft(null);
      await client.invalidateQueries({ queryKey: ['company', company.id] });
      await client.invalidateQueries({ queryKey: ['companies'] });
      await client.invalidateQueries({ queryKey: ['sources', company.id] });
    },
  });
  return (
    <details>
      <summary>Edit company watch</summary>
      <form
        className="inventory-form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="edit-name">Company name</label>
          <input id="edit-name" required value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="edit-url">Website or careers URL</label>
          <input
            id="edit-url"
            type="url"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
        </div>
        <Interval value={interval} onChange={setInterval} id="edit-interval" />
        <p className="field-help">
          This default applies to new sources. Existing source intervals can be edited below.
        </p>
        <label className="checkbox-label">
          <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} />
          Pause monitoring
        </label>
        {save.isError && <Failure focus error={save.error} />}
        {save.isSuccess && <p role="status">Company watch saved.</p>}
        <Button disabled={save.isPending}>Save company</Button>
        {save.isError && (
          <p>Keep your changes here, or reload the page to start from the saved version.</p>
        )}
      </form>
    </details>
  );
}
function SourceCard({ source, paused }: { source: Schemas['SourceView']; paused: boolean }) {
  const csrf = useCsrf();
  const client = useQueryClient();
  const [draft, setDraft] = useState<{ interval: number; enabled: boolean; base: number } | null>(
    null,
  );
  const current = draft ?? {
    interval: source.interval_hours,
    enabled: source.enabled,
    base: source.revision,
  };
  const { interval, enabled, base } = current;
  const setInterval = (value: number) => setDraft({ ...current, interval: value });
  const setEnabled = (value: boolean) => setDraft({ ...current, enabled: value });
  const runs = useQuery({
    queryKey: ['source-runs', source.id],
    queryFn: () => read<Schemas['RunView'][]>(`/sources/${source.id}/runs`),
    refetchInterval: 15000,
  });
  const save = useMutation({
    mutationFn: () =>
      request(
        `/sources/${source.id}`,
        {
          method: 'PATCH',
          headers: { 'If-Match': `"${base}"` },
          body: JSON.stringify({ interval_hours: interval, enabled }),
        },
        csrf,
      ),
    onSuccess: (data) => {
      const saved = data as Schemas['SourceView'];
      client.setQueryData<Schemas['SourceView'][]>(['sources', source.company_id], (rows) =>
        rows?.map((row) => (row.id === saved.id ? saved : row)),
      );
      setDraft(null);
      return client.invalidateQueries({ queryKey: ['sources', source.company_id] });
    },
  });
  return (
    <article className="panel">
      <h3>{source.adapter === 'generic_http' ? 'Website' : source.adapter} source</h3>
      {!source.authoritative && (
        <p>Partial site coverage. Missing listings alone will not close roles.</p>
      )}
      <a href={source.url} target="_blank" rel="noopener noreferrer">
        Open source
      </a>
      <p>{source.enabled ? 'Monitoring enabled' : 'Monitoring disabled'}</p>
      <p>Last successful check: {date(source.last_success_at)}</p>
      <p>
        {paused
          ? 'Source checks paused with this company.'
          : !source.enabled
            ? 'No scheduled check while this source is disabled.'
            : `Next scheduled check: ${date(
                source.cooldown_until &&
                  new Date(source.cooldown_until) > new Date(source.next_due_at)
                  ? source.cooldown_until
                  : source.next_due_at,
              )}`}
      </p>
      {source.last_error && (
        <p role="status">
          Check needs attention: {source.last_error.replaceAll('_', ' ')}. Existing listings are
          preserved.
        </p>
      )}
      <details>
        <summary>Source settings and recent checks</summary>
        <form
          className="inventory-form"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Interval value={interval} onChange={setInterval} id={`interval-${source.id}`} />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Enable this source
          </label>
          {save.isError && <Failure focus error={save.error} />}
          {save.isSuccess && <p role="status">Source settings saved.</p>}
          <Button disabled={save.isPending}>Save source</Button>
        </form>
        {source.adapter === 'generic_http' && !source.authoritative && (
          <SourceRules source={source} />
        )}
        {runs.isError && <Failure error={runs.error} />}
        {runs.data?.map((run) => (
          <p key={run.id}>
            {date(run.started_at)} · {run.state} · {run.pages} pages
            {run.issues.length > 0 ? ` · ${run.issues.join(', ').replaceAll('_', ' ')}` : ''}
          </p>
        ))}
        {runs.data?.length === 0 && <p>No checks completed yet.</p>}
      </details>
    </article>
  );
}
export function CompanyPage() {
  const { id } = useParams();
  const csrf = useCsrf();
  const client = useQueryClient();
  const location = useLocation();
  const [operation, setOperation] = useState<string | undefined>(location.state?.operationId);
  const company = useQuery({
    queryKey: ['company', id],
    queryFn: () => read<Schemas['CompanyView']>(`/companies/${id}`),
    refetchInterval: 5000,
  });
  const sources = useQuery({
    queryKey: ['sources', id],
    queryFn: () => read<Schemas['SourceView'][]>(`/companies/${id}/sources`),
    refetchInterval: 15000,
  });
  const action = useMutation({
    mutationFn: (kind: string) =>
      request(`/companies/${id}/${kind}`, { method: 'POST' }, csrf) as Promise<
        Schemas['OperationAccepted']
      >,
    onSuccess: (data) => setOperation(data.operation_id),
  });
  const [adapter, setAdapter] = useState('greenhouse');
  const [board, setBoard] = useState('');
  const [region, setRegion] = useState('global');
  const [confirmed, setConfirmed] = useState(false);
  const add = useMutation({
    mutationFn: () =>
      request(
        `/companies/${id}/sources`,
        {
          method: 'POST',
          body: JSON.stringify({
            adapter,
            board,
            region: adapter === 'lever' ? region : 'global',
            confirmed_company: confirmed,
          }),
        },
        csrf,
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['sources', id] });
      await client.invalidateQueries({ queryKey: ['company', id] });
      await client.invalidateQueries({ queryKey: ['companies'] });
      setBoard('');
      setConfirmed(false);
    },
  });
  if (company.isPending)
    return (
      <>
        <h1 tabIndex={-1}>Company</h1>
        <p role="status">Loading company…</p>
      </>
    );
  if (company.isError)
    return (
      <>
        <h1 tabIndex={-1}>Company</h1>
        <Failure error={company.error} retry={() => void company.refetch()} />
      </>
    );
  return (
    <>
      <Link to="/companies">Back to companies</Link>
      <h1 tabIndex={-1}>{company.data.label}</h1>
      <p>{company.data.paused ? 'Monitoring paused' : 'Company watch saved'}</p>
      <div className="inventory-actions">
        <Button
          disabled={action.isPending || company.data.paused}
          onClick={() => action.mutate('check')}
        >
          Check now
        </Button>
        <Button
          variant="secondary"
          disabled={action.isPending || company.data.paused}
          onClick={() => action.mutate('discover')}
        >
          Find job sources
        </Button>
        <Link to={`/jobs?view=all&availability=all&company_id=${id}`}>All collected jobs</Link>
      </div>
      <section className="panel" aria-labelledby="coverage-title">
        <h2 id="coverage-title">Collected jobs and coverage</h2>
        <CompanyCoverage company={company.data} />
      </section>
      {action.isError && <Failure focus error={action.error} />}
      <OperationStatus id={operation} />
      <section className="company-jobs" aria-labelledby="company-jobs-title">
        <h2 id="company-jobs-title">Jobs at {company.data.label}</h2>
        <JobList companyId={company.data.id} />
      </section>
      <section className="panel">
        <h2>Company settings</h2>
        <CompanyEditor key={company.data.id} company={company.data} />
      </section>
      <section aria-labelledby="sources-title">
        <h2 id="sources-title">Job sources</h2>
        <p>
          Coverage depends on the sources below. A missing or failed source does not mean there are
          no vacancies.
        </p>
        {sources.isError && <Failure error={sources.error} retry={() => void sources.refetch()} />}
        {sources.data?.length === 0 && (
          <p>No source configured yet. Your company watch is retained.</p>
        )}
        {sources.data?.map((source) => (
          <SourceCard key={source.id} source={source} paused={company.data.paused ?? false} />
        ))}
      </section>
      <DiscoveryHistory company={company.data} onOperation={setOperation} />
      <section className="panel">
        <h2>Add a known job board</h2>
        <p>
          Add a Greenhouse, Lever or Ashby board you have checked yourself. Its first successful
          collection will establish the available listings.
        </p>
        <form
          className="inventory-form"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="source-type">Job board provider</label>
            <select id="source-type" value={adapter} onChange={(e) => setAdapter(e.target.value)}>
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="ashby">Ashby</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="source-board">Board identifier</label>
            <input
              id="source-board"
              required
              pattern="[A-Za-z0-9_-]{1,200}"
              value={board}
              onChange={(e) => setBoard(e.target.value)}
            />
            <p className="field-help">
              The company segment in the hosted board URL, such as “example” in
              jobs.lever.co/example.
            </p>
          </div>
          {adapter === 'lever' && (
            <div className="field">
              <label htmlFor="source-region">Lever region</label>
              <select id="source-region" value={region} onChange={(e) => setRegion(e.target.value)}>
                <option value="global">Global</option>
                <option value="eu">EU</option>
              </select>
            </div>
          )}
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I checked that this board belongs to this company
          </label>
          {add.isError && <Failure focus error={add.error} />}
          {add.isSuccess && (
            <p role="status">Source saved. Its first successful check will confirm coverage.</p>
          )}
          <Button disabled={!confirmed || add.isPending}>Add source</Button>
        </form>
      </section>
    </>
  );
}
