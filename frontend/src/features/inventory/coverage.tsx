import type { Schemas } from './data';
import { date } from './data';

export function CompanyCoverage({ company }: { company: Schemas['CompanyView'] }) {
  const value = company.coverage;
  return (
    <div className="company-coverage">
      <p>
        <strong>
          {value.collected_jobs} collected {value.collected_jobs === 1 ? 'role' : 'roles'}
        </strong>{' '}
        · {value.active_jobs} active · {value.unknown_jobs} availability unknown ·{' '}
        {value.closed_jobs} closed
      </p>
      <p className="field-help">
        Counts cover collected listings, not all vacancies at the company.
      </p>
      {value.sources === 0 ? (
        <p>No job source yet. Zero collected roles does not mean there are no vacancies.</p>
      ) : value.enabled_sources === 0 ? (
        <p>All job sources are disabled. Existing listings remain available.</p>
      ) : (
        <>
          <p>
            {value.enabled_sources} enabled {value.enabled_sources === 1 ? 'source' : 'sources'} ·{' '}
            {value.partial_sources} with partial site coverage
          </p>
          {!!value.sources_needing_attention && (
            <p>
              {value.sources_needing_attention}{' '}
              {value.sources_needing_attention === 1 ? 'source needs' : 'sources need'} attention;
              listings are preserved.
            </p>
          )}
          {!!value.sources_without_success && (
            <p>
              {value.sources_without_success}{' '}
              {value.sources_without_success === 1 ? 'source has' : 'sources have'} no complete
              successful check yet.
            </p>
          )}
        </>
      )}
      <p className="field-help">
        Most recent successful source check: {date(value.last_success_at ?? null)}
        <br />
        Latest source attempt: {date(value.last_attempt_at ?? null)}
      </p>
      {company.paused ? (
        <p>Checks are paused.</p>
      ) : (
        <p className="field-help">
          {value.next_check_at && (
            <>
              Next source check: {date(value.next_check_at)}
              <br />
            </>
          )}
          {value.next_discovery_at && <>Next source discovery: {date(value.next_discovery_at)}</>}
        </p>
      )}
    </div>
  );
}
