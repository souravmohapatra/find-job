import { useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Button } from '../../components/ui/button';
import { api, ApiError, errorMessage, request } from '../../lib/api';
import type { components } from '../../lib/api-types';

type S = components['schemas'];
type Settings = S['NotificationSettingsView'];
type Delivery = S['DeliveryView'];
type Digest = S['DigestView'];
type History = S['DigestHistory'];
type Accepted = S['OperationAccepted'];
type Preferences = {
  enabled: boolean;
  timezone: string;
  local_time: string;
  include_empty: boolean;
};
const active = (item?: Delivery | null) =>
  !!item && (['pending', 'sending'].includes(item.state) || item.retryable);
const defaults = (data: Settings): Preferences => ({
  enabled: data.enabled ?? false,
  timezone: data.timezone ?? 'Europe/London',
  local_time: data.local_time ?? '19:00',
  include_empty: data.include_empty ?? true,
});
function localTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone,
  }).format(new Date(value));
}
function DeliveryStatus({ item }: { item: Delivery }) {
  const labels = {
    pending: 'Queued',
    sending: 'Sending',
    sent: 'Accepted by ntfy',
    failed: item.retryable ? 'Retry scheduled' : 'Not sent',
    unknown: 'Delivery unknown',
  };
  const reasons: Record<string, string> = {
    notification_mock_mode: 'Development mode: no message was sent.',
    notification_configuration_required: 'Configure the notification publisher on the server.',
    notification_token_required: 'The publisher credential is missing.',
    notification_token_invalid: 'The publisher credential needs correction.',
    notification_destination_changed:
      'The publisher configuration changed. Review it before retrying.',
    notification_window_expired:
      'The delivery window ended. Unsent roles remain eligible for a later summary.',
    ntfy_rate_limited: 'The notification server requested a cooldown.',
    notifications_disabled: 'Scheduled notifications were disabled.',
    profile_purged: 'Profile data was removed; this request was stopped.',
  };
  return (
    <div className="notification-status">
      <p>
        <strong>{labels[item.state]}</strong> · Attempt {item.batch_attempt}
        {item.manual ? ' · Requested by you' : ''}
      </p>
      {item.state === 'unknown' ? (
        <p className="field-help">
          The message may have arrived. It will not be resent automatically.
        </p>
      ) : (
        item.error_code && (
          <p className="field-help">
            {reasons[item.error_code] ??
              'The notification could not be confirmed. Review the publisher configuration and connection.'}
          </p>
        )
      )}
      {item.state === 'sent' && (
        <p className="field-help">
          Server acceptance is confirmed. This does not confirm delivery to your phone.
        </p>
      )}
    </div>
  );
}
function ScheduleForm({ data, csrf }: { data: Settings; csrf: string }) {
  const client = useQueryClient();
  const [revision, setRevision] = useState(data.revision);
  const [notice, setNotice] = useState('');
  const errorRef = useRef<HTMLParagraphElement>(null);
  const form = useForm<Preferences>({ defaultValues: defaults(data), mode: 'onBlur' });
  const save = useMutation({
    mutationFn: async (values: Preferences) =>
      (await request(
        '/settings/notifications',
        { method: 'PATCH', headers: { 'If-Match': `"${revision}"` }, body: JSON.stringify(values) },
        csrf,
      )) as Settings,
    onSuccess: (saved) => {
      client.setQueryData(['notification-settings'], saved);
      form.reset(defaults(saved));
      setRevision(saved.revision);
      setNotice('Notification schedule saved.');
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ['notification-settings'] });
    },
  });
  useEffect(() => {
    if (save.isError) errorRef.current?.focus();
  }, [save.isError]);
  return (
    <form
      onSubmit={form.handleSubmit((values) => save.mutate(values))}
      className="notification-form"
    >
      <fieldset disabled={save.isPending}>
        <legend className="sr-only">Daily notification schedule</legend>
        <label className="checkbox-label">
          <input type="checkbox" {...form.register('enabled')} />
          Send a daily summary
        </label>
        <div className="notification-fields">
          <div className="field">
            <label htmlFor="notification-time">Daily summary time</label>
            <input
              id="notification-time"
              type="time"
              step="60"
              required
              {...form.register('local_time')}
            />
          </div>
          <div className="field">
            <label htmlFor="notification-timezone">Timezone</label>
            <input
              id="notification-timezone"
              list="notification-timezones"
              required
              aria-invalid={!!form.formState.errors.timezone}
              aria-describedby="notification-timezone-help"
              {...form.register('timezone', {
                validate: (value) => {
                  try {
                    new Intl.DateTimeFormat('en', { timeZone: value });
                    return true;
                  } catch {
                    return 'Enter an IANA timezone, such as Europe/London.';
                  }
                },
              })}
            />
            <datalist id="notification-timezones">
              {[
                'Europe/London',
                'UTC',
                'Asia/Kolkata',
                'America/New_York',
                'America/Los_Angeles',
                'Australia/Sydney',
              ].map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
            <p id="notification-timezone-help" className="field-help">
              {form.formState.errors.timezone?.message ??
                'The summary follows this local time through daylight-saving changes.'}
            </p>
          </div>
        </div>
        <label className="checkbox-label">
          <input type="checkbox" {...form.register('include_empty')} />
          Send a summary even when there are no new roles
        </label>
        <p className="field-help">
          Collection runs on each company’s own schedule. Problems and pending checks stay visible
          in summaries.
        </p>
        {data.revision !== revision && (
          <div className="notice">
            <p>A newer schedule is available. Your edits are preserved.</p>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                form.reset(defaults(data));
                setRevision(data.revision);
                save.reset();
                setNotice('');
              }}
            >
              Discard edits and reload schedule
            </Button>
          </div>
        )}
        {save.isError && (
          <p className="form-error" role="alert" tabIndex={-1} ref={errorRef}>
            {errorMessage(save.error)}
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" disabled={save.isPending || !csrf}>
            {save.isPending ? 'Saving…' : 'Save notification schedule'}
          </Button>
          <span role="status">{notice}</span>
        </div>
        <p className="field-help">
          {data.enabled && data.next_due_at
            ? `Next scheduled summary: ${localTime(data.next_due_at, data.timezone ?? 'Europe/London')} (${data.timezone}).`
            : 'Scheduled summaries are off.'}
        </p>
      </fieldset>
    </form>
  );
}
function Resend({ digest, csrf }: { digest: Digest; csrf: string }) {
  const client = useQueryClient();
  const [acknowledged, setAcknowledged] = useState(false);
  const [notice, setNotice] = useState('');
  const retained = useRef<{ key: string; body: S['ResendRequest'] } | undefined>(undefined);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      retained.current ??= {
        key: crypto.randomUUID(),
        body: {
          expected_delivery_id: digest.delivery?.id ?? null,
          accept_possible_duplicate: acknowledged,
        },
      };
      return (await request(
        `/notifications/${digest.id}/resend`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': retained.current.key },
          body: JSON.stringify(retained.current.body),
        },
        csrf,
      )) as Accepted;
    },
    onSuccess: () => {
      retained.current = undefined;
      setAcknowledged(false);
      setNotice('Resend queued.');
      void client.invalidateQueries({ queryKey: ['notification-history'] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500)
        retained.current = undefined;
      void client.invalidateQueries({ queryKey: ['notification-history'] });
    },
  });
  useEffect(() => {
    if (mutation.isError) errorRef.current?.focus();
  }, [mutation.isError]);
  const allowed = ['failed', 'unknown'].includes(digest.state);
  return (
    <div className="notification-resend">
      {(allowed || (mutation.isError && retained.current)) && (
        <>
          <p className="field-help">
            Resends the original dated summary. It may include roles that have since changed.
          </p>
          {digest.state === 'unknown' && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              I understand that resending may deliver this summary twice.
            </label>
          )}
          <Button
            variant="secondary"
            disabled={
              mutation.isPending ||
              !csrf ||
              (digest.state === 'unknown' && !acknowledged && !retained.current)
            }
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending
              ? 'Requesting…'
              : mutation.isError && retained.current
                ? 'Retry resend request'
                : 'Resend summary'}
          </Button>
        </>
      )}
      {mutation.isError && (
        <p role="alert" className="form-error" tabIndex={-1} ref={errorRef}>
          {errorMessage(mutation.error)}
        </p>
      )}
      <p role="status">{notice}</p>
    </div>
  );
}
export function NotificationSettings() {
  const client = useQueryClient();
  const session = useQuery({ queryKey: ['session'], queryFn: api.session, staleTime: 30000 });
  const settings = useQuery({
    queryKey: ['notification-settings'],
    queryFn: async () => (await request('/settings/notifications')) as Settings,
  });
  const tests = useQuery({
    queryKey: ['notification-tests'],
    queryFn: async () => (await request('/settings/notifications/tests')) as Delivery[],
    refetchInterval: (query) => (query.state.data?.some(active) ? 2000 : 30000),
    refetchIntervalInBackground: false,
  });
  const history = useInfiniteQuery({
    queryKey: ['notification-history'],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      (await request(
        '/notifications' + (pageParam ? `?before=${encodeURIComponent(pageParam)}` : ''),
      )) as History,
    getNextPageParam: (page) => page.next_before ?? undefined,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some((item) => ['pending', 'sending'].includes(item.state)),
      )
        ? 2000
        : 30000,
    refetchIntervalInBackground: false,
  });
  const retained = useRef<string | undefined>(undefined);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const test = useMutation({
    mutationFn: async () => {
      retained.current ??= crypto.randomUUID();
      return (await request(
        '/settings/notifications/test',
        { method: 'POST', headers: { 'Idempotency-Key': retained.current } },
        session.data!.csrf_token,
      )) as Accepted;
    },
    onSuccess: () => {
      retained.current = undefined;
      void client.invalidateQueries({ queryKey: ['notification-tests'] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500)
        retained.current = undefined;
    },
  });
  useEffect(() => {
    if (test.isError) errorRef.current?.focus();
  }, [test.isError]);
  const csrf = session.data?.csrf_token ?? '';
  return (
    <section className="panel notification-settings" aria-labelledby="notification-heading">
      <h2 id="notification-heading">Notifications</h2>
      <p>
        A daily summary of Relevant and Possible roles, with baseline and reassessment results
        labelled separately.
      </p>
      {settings.isPending ? (
        <p role="status">Loading notification settings…</p>
      ) : settings.isError ? (
        <>
          <p role="alert">{errorMessage(settings.error)}</p>
          <Button onClick={() => void settings.refetch()}>Reload notification settings</Button>
        </>
      ) : (
        <>
          <p className="notice">
            {settings.data.delivery_mode === 'mock'
              ? 'Development mode: no notification will be sent.'
              : settings.data.publisher_configured
                ? 'The local publisher is configured. Send a test to check server acceptance.'
                : 'Configure the notification publisher on the server before sending messages.'}
          </p>
          <ScheduleForm data={settings.data} csrf={csrf} />
        </>
      )}
      <div className="notification-test">
        <h3>Test the connection</h3>
        <p className="field-help">
          Sends a generic message without consuming job alerts or changing your daily schedule. Your
          device must be connected to the local network or tailnet; background delivery depends on
          its client.
        </p>
        <Button
          variant="secondary"
          disabled={test.isPending || !csrf}
          onClick={() => test.mutate()}
        >
          {test.isPending
            ? 'Requesting test…'
            : test.isError && retained.current
              ? 'Retry test request'
              : 'Test notification'}
        </Button>
        {test.isSuccess && <p role="status">Test queued. Its result appears below.</p>}
        {test.isError && (
          <p role="alert" className="form-error" tabIndex={-1} ref={errorRef}>
            {errorMessage(test.error)}
          </p>
        )}
        {tests.isError && (
          <>
            <p role="alert">{errorMessage(tests.error)}</p>
            <Button variant="secondary" onClick={() => void tests.refetch()}>
              Reload test results
            </Button>
          </>
        )}
        {tests.data?.[0] && (
          <div aria-live="polite">
            <DeliveryStatus item={tests.data[0]} />
          </div>
        )}
      </div>
      <details className="notification-history">
        <summary>Delivery history</summary>
        <p className="field-help">
          “Accepted by ntfy” confirms the server receipt, not that a phone displayed the message.
        </p>
        {history.isPending && <p role="status">Loading delivery history…</p>}
        {history.isError && (
          <>
            <p role="alert">{errorMessage(history.error)}</p>
            <Button onClick={() => void history.refetch()}>Reload delivery history</Button>
          </>
        )}
        {history.data && history.data.pages[0].items.length === 0 && <p>No daily summaries yet.</p>}
        {history.data?.pages
          .flatMap((page) => page.items)
          .map((digest) => (
            <article key={digest.id} className="notification-digest">
              <h3>
                {digest.local_date} · {digest.local_time} {digest.timezone}
              </h3>
              {digest.content_removed ? (
                <p>Summary content removed with profile data.</p>
              ) : (
                <p>
                  {digest.snapshot.counts?.new ?? 0} new roles ·{' '}
                  {digest.snapshot.counts?.baseline ?? 0} baseline ·{' '}
                  {digest.snapshot.counts?.reassessment ?? 0} newly suitable after reassessment
                </p>
              )}
              {digest.integration_mode === 'mock' && (
                <p className="field-help">Synthetic assessment results.</p>
              )}
              {digest.state === 'unknown' && digest.delivery?.state !== 'unknown' && (
                <p className="notice">
                  Delivery unknown: an earlier send may have arrived. The latest attempt did not
                  resolve that uncertainty.
                </p>
              )}
              {digest.delivery ? (
                <DeliveryStatus item={digest.delivery} />
              ) : (
                <p>
                  {digest.state === 'skipped'
                    ? 'Summary skipped or content removed.'
                    : digest.state === 'failed'
                      ? 'The delivery window ended before a send.'
                      : 'Waiting for delivery.'}
                </p>
              )}
              {!digest.content_removed &&
              (digest.snapshot.source_errors ||
                digest.snapshot.assessment_errors ||
                digest.snapshot.unresolved_companies ||
                digest.snapshot.pending_operations ||
                !digest.snapshot.matching_available) ? (
                <p className="notice">
                  Coverage at cutoff: {digest.snapshot.source_errors ?? 0} sources needing
                  attention, {digest.snapshot.assessment_errors ?? 0} assessment errors,{' '}
                  {digest.snapshot.unresolved_companies ?? 0} unresolved companies and{' '}
                  {digest.snapshot.pending_operations ?? 0} pending tasks.
                  {!digest.snapshot.matching_available && ' Matching was unavailable.'}
                </p>
              ) : null}
              {digest.snapshot.examples?.length ? (
                <ul>
                  {digest.snapshot.examples.map((item) => (
                    <li key={item.job_id}>
                      {item.company}: {item.title}
                    </li>
                  ))}
                </ul>
              ) : null}
              {!digest.content_removed && <Resend digest={digest} csrf={csrf} />}
            </article>
          ))}
        {history.hasNextPage && (
          <Button
            variant="secondary"
            disabled={history.isFetchingNextPage}
            onClick={() => void history.fetchNextPage()}
          >
            {history.isFetchingNextPage ? 'Loading…' : 'Load older summaries'}
          </Button>
        )}
      </details>
    </section>
  );
}
