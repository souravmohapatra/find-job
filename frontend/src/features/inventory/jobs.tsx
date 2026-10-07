import { assessmentLabel } from './assessment-label';
import { useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '../../components/ui/button';
import { Failure } from './shared';
import { AssessmentPanel, FeedbackPanel } from './assessment';
import { date, read, type Schemas } from './data';

export function JobsPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const view = params.get('view') === 'all' ? 'all' : 'recommended';
  const availability = params.get('availability') ?? 'active';
  const company = params.get('company_id') ?? '';
  const [search, setSearch] = useState(params.get('q') ?? '');
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
    enabled: Boolean(company),
  });
  function filter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }
  return (
    <>
      <p className="eyebrow">YOUR OPPORTUNITIES</p>
      <h1 tabIndex={-1}>Jobs</h1>
      <p className="page-description">Browse roles from your companies, with room to explore.</p>
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
        <h2>Filter jobs</h2>
        {company && (
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
            <option value="active">Active</option>
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
      {jobs.isError && <Failure error={jobs.error} retry={() => void jobs.refetch()} />}
      {view === 'all' && (
        <p className="field-help">
          All successfully collected roles, regardless of fit. Missing or failed sources can leave
          gaps.
        </p>
      )}
      {jobs.data?.pages
        .flatMap((page) => page.items)
        .map((job) => (
          <article className="panel inventory-row" key={job.id}>
            <div>
              <h2>
                <Link to={`/jobs/${job.id}`} state={{ from: location.pathname + location.search }}>
                  {job.posting.title}
                </Link>
              </h2>
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
      {jobs.data?.pages[0].items.length === 0 && (
        <section className="empty-state">
          <h2>
            {view === 'recommended'
              ? 'No current shortlist entries in this view'
              : 'No collected jobs in this view'}
          </h2>
          <p>
            Check filters, company sources and assessment status in All jobs. Pending or failed
            assessments are not rejections, and this does not establish that a company has no
            vacancies.
          </p>
          <Link to="/companies">View company watches</Link>
        </section>
      )}
      {jobs.hasNextPage && (
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
    typeof location.state?.from === 'string' && location.state.from.startsWith('/jobs?')
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
      <Link to={from}>Back to jobs</Link>
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
