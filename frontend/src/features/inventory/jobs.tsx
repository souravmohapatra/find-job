import { assessmentLabel } from './assessment-label';
import { useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigationType, useParams, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Failure } from './shared';
import { AssessmentPanel, FeedbackPanel } from './assessment';
import { date, read, type Schemas } from './data';

export function JobsPage() {
  return (
    <>
      <p className="eyebrow">YOUR OPPORTUNITIES</p>
      <h1 tabIndex={-1}>Jobs</h1>
      <p className="page-description">Browse roles from your companies, with room to explore.</p>
      <JobList />
    </>
  );
}

export function JobList({ companyId }: { companyId?: string }) {
  const client = useQueryClient();
  const navigation = useNavigationType();
  const restored = useRef<string | undefined>(undefined);
  const Heading = companyId ? 'h3' : 'h2';
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const view = params.get('view') === 'all' ? 'all' : 'recommended';
  const availability = params.get('availability') ?? 'open';
  const company = companyId ?? params.get('company_id') ?? '';
  const savedSearch = params.get('q') ?? '';
  const [search, setSearch] = useState(savedSearch);
  useEffect(() => setSearch(savedSearch), [savedSearch]);
  const query = new URLSearchParams({ view, availability });
  if (company) query.set('company_id', company);
  if (params.get('q')) query.set('q', params.get('q')!);
  const jobs = useInfiniteQuery({
    queryKey: ['jobs', query.toString()],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      read<Schemas['JobPage']>(
        `/jobs?${query}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ''}`,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const companyInfo = useQuery({
    queryKey: ['company', company],
    queryFn: () => read<Schemas['CompanyView']>(`/companies/${company}`),
    enabled: Boolean(company) && !companyId,
  });
  const unavailable = jobs.error instanceof ApiError && jobs.error.code === 'matching_unavailable';
  useEffect(() => {
    if (
      unavailable ||
      restored.current === location.key ||
      !jobs.data ||
      jobs.isFetching ||
      !(location.state?.restoreJobs || navigation === 'POP')
    )
      return;
    const scroll = client.getQueryData<{ top: number; jobId: string }>([
      'job-scroll',
      location.pathname,
      location.search,
    ]);
    if (scroll === undefined) return;
    const frame = requestAnimationFrame(() => {
      document
        .querySelector<HTMLAnchorElement>(`a[href="/jobs/${scroll.jobId}"]`)
        ?.focus({ preventScroll: true });
      window.scrollTo({ top: scroll.top, behavior: 'instant' });
      restored.current = location.key;
    });
    return () => cancelAnimationFrame(frame);
  }, [
    client,
    jobs.data,
    jobs.isFetching,
    location.key,
    location.pathname,
    location.search,
    location.state,
    navigation,
    unavailable,
  ]);
  const displayed = unavailable ? undefined : jobs.data;
  function filter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }
  return (
    <>
      <div className="inventory-actions" aria-label="Job views">
        <Button
          variant={view === 'recommended' ? 'primary' : 'secondary'}
          aria-pressed={view === 'recommended'}
          onClick={() => filter('view', 'recommended')}
        >
          Shortlist
        </Button>
        <Button
          variant={view === 'all' ? 'primary' : 'secondary'}
          aria-pressed={view === 'all'}
          onClick={() => filter('view', 'all')}
        >
          All jobs
        </Button>
      </div>
      <section className="panel">
        <Heading>Filter jobs</Heading>
        {company && !companyId && (
          <p>
            Company: {companyInfo.data?.label ?? 'Selected company'} ·{' '}
            <Link to={`/companies/${company}`}>Company details</Link>
          </p>
        )}
        <form
          className="inventory-filters"
          onSubmit={(e) => {
            e.preventDefault();
            filter('q', search);
          }}
        >
          <div className="field">
            <label htmlFor="job-search">Search collected jobs</label>
            <input
              id="job-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              maxLength={200}
            />
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
        <div className="field">
          <label htmlFor="availability">Availability</label>
          <select
            id="availability"
            value={availability}
            onChange={(e) => filter('availability', e.target.value)}
          >
            <option value="open">Active or unknown</option>
            <option value="active">Active only</option>
            <option value="unknown">Unknown</option>
            <option value="closed">Closed</option>
            <option value="all">All statuses</option>
          </select>
        </div>
        <Button
          variant="quiet"
          onClick={() => {
            setSearch('');
            setParams({ view });
          }}
        >
          Clear filters
        </Button>
      </section>
      {jobs.isPending && <p role="status">Loading jobs…</p>}
      {unavailable ? (
        <div className="notice job-list-notice" role="status">
          <p>
            Shortlisting is unavailable. Review your <Link to="/profile">profile</Link> and choose a
            matching model in <Link to="/settings">Settings</Link>. All collected jobs remain
            available.
          </p>
          <Button variant="secondary" onClick={() => filter('view', 'all')}>
            Browse all collected jobs
          </Button>
        </div>
      ) : (
        jobs.isError && <Failure error={jobs.error} retry={() => void jobs.refetch()} />
      )}
      {displayed && (
        <Button variant="secondary" disabled={jobs.isFetching} onClick={() => void jobs.refetch()}>
          {jobs.isFetching ? 'Refreshing…' : 'Refresh jobs'}
        </Button>
      )}
      {view === 'all' && (
        <p className="field-help">
          All successfully collected roles, regardless of fit. Missing or failed sources can leave
          gaps.
        </p>
      )}
      {displayed?.pages
        .flatMap((page) => page.items)
        .map((job) => (
          <article className="panel inventory-row" key={job.id}>
            <div>
              <Heading>
                <Link
                  to={`/jobs/${job.id}`}
                  state={{ from: location.pathname + location.search }}
                  onClick={() =>
                    client.setQueryData(['job-scroll', location.pathname, location.search], {
                      top: window.scrollY,
                      jobId: job.id,
                    })
                  }
                >
                  {job.posting.title}
                </Link>
              </Heading>
              <p>
                {job.company_label} ·{' '}
                {(job.posting.locations ?? []).join(' · ') || 'Location not specified'}
              </p>
              <p className="field-help">
                First seen {date(job.first_seen_at)} · {job.availability} · {assessmentLabel(job)}
              </p>
            </div>
            <span className="badge">{job.baseline ? 'Initial inventory' : 'New listing'}</span>
          </article>
        ))}
      {displayed?.pages[0].items.length === 0 && (
        <section className="empty-state">
          <Heading>
            {view === 'recommended'
              ? 'No current shortlist entries in this view'
              : 'No collected jobs in this view'}
          </Heading>
          <p>
            Check filters, company sources and assessment status in All jobs. Pending or failed
            assessments are not rejections, and this does not establish that a company has no
            vacancies.
          </p>
          <Link to="/companies">View company watches</Link>
        </section>
      )}
      {!unavailable && jobs.hasNextPage && (
        <Button
          variant="secondary"
          disabled={jobs.isFetchingNextPage}
          onClick={() => void jobs.fetchNextPage()}
        >
          Load more jobs
        </Button>
      )}
    </>
  );
}
export function JobPage() {
  const { id } = useParams();
  const location = useLocation();
  const from =
    typeof location.state?.from === 'string' &&
    /^\/(?:jobs(?:\?|$)|companies\/[0-9a-f-]{36}(?:\?|$))/i.test(location.state.from)
      ? location.state.from
      : '/jobs?view=all';
  const job = useQuery({
    queryKey: ['job', id],
    queryFn: () => read<Schemas['JobDetail']>(`/jobs/${id}`),
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.assessment_operation?.state ?? '')
        ? 2000
        : false,
  });
  if (job.isPending)
    return (
      <>
        <h1 tabIndex={-1}>Job details</h1>
        <p role="status">Loading job…</p>
      </>
    );
  if (job.isError)
    return (
      <>
        <h1 tabIndex={-1}>Job details</h1>
        <Failure error={job.error} retry={() => void job.refetch()} />
      </>
    );
  const data = job.data;
  return (
    <>
      <Link to={from} state={{ restoreJobs: true }}>
        Back to jobs
      </Link>
      <h1 tabIndex={-1}>{data.posting.title}</h1>
      <p>
        <Link to={`/companies/${data.company_id}`}>{data.company_label}</Link> · {data.availability}
      </p>
      <p>{(data.posting.locations ?? []).join(' · ') || 'Location not specified'}</p>
      <div className="inventory-actions">
        <a href={data.posting.url} target="_blank" rel="noopener noreferrer">
          Original listing ↗
        </a>
        <a href={data.posting.apply_url} target="_blank" rel="noopener noreferrer">
          Application page ↗
        </a>
      </div>
      <section className="panel">
        <h2>About the role</h2>
        <p className="job-description">{data.posting.description}</p>
        {data.posting.workplace && <p>Workplace: {data.posting.workplace}</p>}
        {data.posting.employment_type && <p>Employment: {data.posting.employment_type}</p>}
      </section>
      <AssessmentPanel job={data} />
      <FeedbackPanel key={data.id} job={data} />
      <section className="panel">
        <h2>Listing history</h2>
        <p>
          Advertised publication:{' '}
          {data.posting.published_at ? date(data.posting.published_at) : 'Not provided'}
        </p>
        <p>First seen: {date(data.first_seen_at)}</p>
        <p>Last seen: {date(data.last_seen_at)}</p>
        <p>{data.revision_count} recorded content versions</p>
        {data.sources.map((source) => (
          <p key={source.id}>
            {source.adapter} · Last successful check: {date(source.last_success_at)}
            {source.last_error && ` · ${source.last_error.replaceAll('_', ' ')}`}
          </p>
        ))}
      </section>
    </>
  );
}
