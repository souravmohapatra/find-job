import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/ui/button';
import { errorMessage, request } from '../../lib/api';
import type { components } from '../../lib/api-types';
import { profileApi, type Accepted } from '../profile/api';

type Call = components['schemas']['CallView'];
type Usage = components['schemas']['UsageView'];
const sourceLabels: Record<string, string> = {
  provider: 'Provider reported',
  owner_verified: 'Owner verified',
  rejected: 'Rejected before generation',
  legacy_reported: 'Earlier accounting record',
};
function Recovery({
  call,
  title,
  csrf,
  live,
  onResolved,
}: {
  call: Call;
  title: string;
  csrf: string;
  live: boolean;
  onResolved: () => void;
}) {
  const client = useQueryClient();
  const [cost, setCost] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [operationId, setOperationId] = useState<string>();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const processed = useRef<string | undefined>(undefined);
  const lookup = useMutation({
    mutationFn: async () =>
      (await request(
        `/settings/ai/usage/${call.id}/reconcile`,
        { method: 'POST' },
        csrf,
      )) as Accepted,
    onSuccess: (data) => setOperationId(data.operation_id),
  });
  const operation = useQuery({
    queryKey: ['billing-operation', operationId],
    queryFn: () => profileApi.operation(operationId!),
    enabled: Boolean(operationId),
    refetchInterval: (query) =>
      query.state.data && ['queued', 'running'].includes(query.state.data.state) ? 2000 : false,
    refetchIntervalInBackground: false,
  });
  const verify = useMutation({
    mutationFn: () =>
      request(
        `/settings/ai/usage/${call.id}/verify`,
        {
          method: 'POST',
          body: JSON.stringify({
            cost_usd: cost,
            confirmation: confirmed ? 'I VERIFIED THE PROVIDER BILLING' : '',
          }),
        },
        csrf,
      ),
    onSuccess: async () => {
      onResolved();
      await client.invalidateQueries({ queryKey: ['ai-usage'] });
    },
  });
  useEffect(() => {
    if (operation.data?.state === 'succeeded' && processed.current !== operation.data.id) {
      processed.current = operation.data.id;
      void client.invalidateQueries({ queryKey: ['ai-usage'] });
    }
  }, [client, operation.data]);
  useEffect(() => {
    if (lookup.isError || verify.isError) errorRef.current?.focus();
  }, [lookup.isError, verify.isError]);
  const busy =
    lookup.isPending ||
    verify.isPending ||
    ['queued', 'running'].includes(operation.data?.state ?? '');
  return (
    <article className="billing-call">
      <h4>
        {title} · {new Date(call.created_at).toLocaleString()}
      </h4>
      <p>
        {call.model} · ${Number(call.reserved_usd).toFixed(4)} held
      </p>
      <p className="field-help">
        The charge is unresolved. Its reservation stays in the budget until the actual cost is
        recorded.
      </p>
      {call.generation_id ? (
        <>
          <p className="field-help">Generation: {call.generation_id}</p>
          <Button variant="secondary" disabled={!live || busy} onClick={() => lookup.mutate()}>
            Fetch provider charge
          </Button>
          {!live && <p className="field-help">Provider lookup is disabled in mock mode.</p>}
        </>
      ) : (
        <p className="field-help">
          No generation ID was received, so automatic lookup is unavailable.
        </p>
      )}
      {operation.data && (
        <p role="status">
          {operation.data.state === 'succeeded'
            ? 'Provider charge recorded.'
            : operation.data.error_message || operation.data.progress}
        </p>
      )}
      {operation.isError && <p role="alert">{errorMessage(operation.error)}</p>}
      <details>
        <summary>Record a charge you verified</summary>
        <p>
          Check this request in your provider billing first. Enter zero only if you verified that it
          was not charged. This updates local accounting; it does not change provider billing or
          retry the AI request.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            verify.mutate();
          }}
        >
          <div className="field">
            <label htmlFor={`cost-${call.id}`}>Verified cost (USD)</label>
            <input
              id={`cost-${call.id}`}
              type="number"
              min="0"
              max="100000"
              step="0.00000001"
              required
              value={cost}
              disabled={busy}
              onChange={(e) => setCost(e.target.value)}
            />
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I checked this request in provider billing
          </label>
          <Button disabled={busy || !confirmed || cost === ''}>Record verified cost</Button>
        </form>
      </details>
      {(lookup.isError || verify.isError) && (
        <p ref={errorRef} role="alert" tabIndex={-1}>
          {errorMessage(lookup.error || verify.error)}
        </p>
      )}
    </article>
  );
}
export function BillingHistory({
  usage,
  names,
  csrf,
  live,
}: {
  usage: Usage;
  names: Record<string, string>;
  csrf: string;
  live: boolean;
}) {
  const [notice, setNotice] = useState('');
  return (
    <section className="panel">
      <h3>Request history and recovery</h3>
      {notice && <p role="status">{notice}</p>}
      {usage.unresolved.map((call) => (
        <Recovery
          key={call.id}
          call={call}
          title={names[call.task]}
          csrf={csrf}
          live={live}
          onResolved={() =>
            setNotice(
              'Verified charge recorded. No AI retry was started. Return to the affected task to retry when ready.',
            )
          }
        />
      ))}
      <details>
        <summary>Recent request accounting</summary>
        {usage.recent.length === 0 ? (
          <p>No AI requests recorded.</p>
        ) : (
          <ul className="billing-history">
            {usage.recent.map((call) => (
              <li key={call.id}>
                <strong>{names[call.task]}</strong>
                <p>
                  {call.model} · {new Date(call.created_at).toLocaleString()}
                </p>
                <p>
                  {call.reported_usd === null
                    ? `$${Number(call.reserved_usd).toFixed(4)} held`
                    : `$${Number(call.reported_usd).toFixed(4)} recorded · ${sourceLabels[call.cost_source ?? ''] ?? 'Source not recorded'}`}
                </p>
                <span className="field-help">{call.state.replaceAll('_', ' ')}</span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
