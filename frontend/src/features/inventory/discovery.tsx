import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';
import { date, read, useCsrf, type Schemas } from './data';
import { Failure } from './shared';

const messages: Record<string, string> = {
  search_mock_mode:
    'Web search is in development mode. Add a known website or job board to continue.',
  search_unconfigured:
    'Web search needs a Brave API credential. You can still add a known website.',
  search_budget: 'The configured search allowance has been reached. Your watch is retained.',
  search_rate_limited: 'The search provider asked us to wait before making more requests.',
  search_cooldown: 'Search is waiting for its next request slot.',
  search_candidates_unverified: 'Check which result belongs to the company you want to follow.',
  search_outcome_unknown: 'A search did not finish reliably. It was counted against the allowance.',
  generic_collection_pending:
    'A possible job page was found, but collection from it is not yet supported.',
  discovery_page_limit: 'The page limit was reached. Source coverage may be incomplete.',
  fetcher_unavailable: 'Website fetching is not configured. Existing listings are preserved.',
  isolation_unverified: 'Website fetching is waiting for deployment validation.',
  robots_denied: 'A page does not permit automated fetching.',
  unverified_redirect: 'A page redirected to another site whose company identity needs review.',
};

export function DiscoveryHistory({
  company,
  onOperation,
}: {
  company: Schemas['CompanyView'];
  onOperation: (id: string) => void;
}) {
  const csrf = useCsrf();
  const client = useQueryClient();
  const [selected, setSelected] = useState<{ run: string; revision: number; url: string } | null>(
    null,
  );
  const [confirmed, setConfirmed] = useState(false);
  const history = useInfiniteQuery({
    queryKey: ['discovery', company.id],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      read<Schemas['DiscoveryView'][]>(`/companies/${company.id}/discovery?offset=${pageParam}`),
    getNextPageParam: (last, pages) => (last.length === 20 ? pages.length * 20 : undefined),
    refetchInterval: 5000,
  });
  const choose = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('Choose a company page first.');
      return request(
        `/companies/${company.id}/discovery/${selected.run}/confirm`,
        {
          method: 'POST',
          headers: { 'If-Match': `"${selected.revision}"` },
          body: JSON.stringify({ url: selected.url, confirmed_company: confirmed }),
        },
        csrf,
      ) as Promise<Schemas['OperationAccepted']>;
    },
    onSuccess: async (data) => {
      setSelected(null);
      setConfirmed(false);
      onOperation(data.operation_id);
      await client.invalidateQueries({ queryKey: ['company', company.id] });
      await client.invalidateQueries({ queryKey: ['companies'] });
      await client.invalidateQueries({ queryKey: ['discovery', company.id] });
    },
  });
  const runs = history.data?.pages.flat() ?? [];
  return (
    <section className="panel" aria-labelledby="discovery-title">
      <h2 id="discovery-title">Source discovery</h2>
      <p>
        Discovery finds places to check. It does not guarantee that every vacancy has been
        collected.
      </p>
      {history.isPending && <p role="status">Loading discovery history…</p>}
      {history.isError && <Failure error={history.error} retry={() => void history.refetch()} />}
      {history.isSuccess && runs.length === 0 && <p>No discovery checks recorded yet.</p>}
      <form
        className="inventory-form"
        onSubmit={(event) => {
          event.preventDefault();
          choose.mutate();
        }}
      >
        {runs.map((run, index) => (
          <details key={run.id} open={index === 0}>
            <summary>
              {date(run.started_at)} ·{' '}
              {run.state === 'running'
                ? 'Searching'
                : run.state === 'complete'
                  ? 'Check finished'
                  : 'Needs attention'}
            </summary>
            <p>{run.cursor} discovery steps checked.</p>
            {run.issues.map((issue) => (
              <p key={issue}>
                {messages[issue] ?? `Discovery needs attention: ${issue.replaceAll('_', ' ')}.`}
              </p>
            ))}
            {run.candidates.map((candidate, candidateIndex) => (
              <article className="discovery-candidate" key={`${candidate.url}-${candidateIndex}`}>
                <h3>
                  <a href={candidate.url} target="_blank" rel="noopener noreferrer">
                    {candidate.title || 'Open candidate page'}
                  </a>
                </h3>
                <p className="discovery-url">{candidate.url}</p>
                <p>
                  {candidate.status === 'needs_identity_review'
                    ? 'Search result · company identity unverified'
                    : candidate.status === 'source_collection_queued'
                      ? 'Verified job page · monitoring source saved'
                      : 'Possible job page · employer evidence needs review'}
                </p>
                {candidate.status === 'needs_identity_review' &&
                  run.company_revision === company.revision && (
                    <label className="checkbox-label">
                      <input
                        type="radio"
                        name="company-candidate"
                        checked={selected?.run === run.id && selected.url === candidate.url}
                        disabled={company.paused || choose.isPending}
                        onChange={() => {
                          setSelected({
                            run: run.id,
                            revision: run.company_revision,
                            url: candidate.url,
                          });
                          setConfirmed(false);
                        }}
                      />
                      Use this page for {company.label}
                    </label>
                  )}
              </article>
            ))}
            {run.candidates.length === 0 && run.state !== 'running' && (
              <p>No company candidates to review from this check.</p>
            )}
          </details>
        ))}
        {selected && (
          <>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              I checked that the selected page belongs to {company.label}
            </label>
            <p>This updates the watched website and starts a new source check.</p>
            <Button disabled={!confirmed || choose.isPending || company.paused}>
              {choose.isPending ? 'Confirming…' : 'Confirm company page'}
            </Button>
          </>
        )}
        {choose.isError && <Failure focus error={choose.error} />}
        {choose.isSuccess && (
          <p role="status">Company page confirmed. A new source check is queued.</p>
        )}
      </form>
      {history.hasNextPage && (
        <Button
          variant="secondary"
          disabled={history.isFetchingNextPage}
          onClick={() => void history.fetchNextPage()}
        >
          Older discovery checks
        </Button>
      )}
    </section>
  );
}
