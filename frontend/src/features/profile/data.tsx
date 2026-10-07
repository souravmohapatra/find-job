import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/ui/button';
import { errorMessage, request } from '../../lib/api';
import type { components } from '../../lib/api-types';
type Page = components['schemas']['DocumentPage'];

export function ProfileData({ csrf, onPurged }: { csrf: string; onPurged: () => void }) {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [retention, setRetention] = useState<Record<string, boolean>>({});
  const [confirmation, setConfirmation] = useState('');
  const [deleteId, setDeleteId] = useState<string>();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const documents = useQuery({
    queryKey: ['profile-documents', offset],
    queryFn: async () => (await request(`/profile/documents?offset=${offset}`)) as Page,
  });
  const change = useMutation({
    mutationFn: ({ id, retain }: { id: string; retain?: boolean }) =>
      request(
        `/profile/documents/${id}${retain === undefined ? '' : '/retention'}`,
        {
          method: retain === undefined ? 'DELETE' : 'PATCH',
          ...(retain === undefined ? {} : { body: JSON.stringify({ retain_original: retain }) }),
        },
        csrf,
      ),
    onSuccess: async () => {
      setDeleteId(undefined);
      client.removeQueries({ queryKey: ['profile-draft'] });
      await client.invalidateQueries({ queryKey: ['profile-documents'] });
      await client.invalidateQueries({ queryKey: ['profile'] });
    },
    onSettled: (_data, _error, variables) =>
      setRetention((current) => {
        const next = { ...current };
        delete next[variables.id];
        return next;
      }),
  });
  const purge = useMutation({
    mutationFn: () =>
      request('/profile/purge', { method: 'POST', body: JSON.stringify({ confirmation }) }, csrf),
    onSuccess: async () => {
      client.removeQueries({
        predicate: (query) =>
          [
            'profile',
            'profile-documents',
            'profile-draft',
            'operation',
            'job',
            'jobs',
            'notification-history',
          ].includes(String(query.queryKey[0])),
      });
      client.getMutationCache().clear();
      await client.invalidateQueries({ queryKey: ['status'] });
      setConfirmation('');
      setDeleteId(undefined);
      setOffset(0);
      onPurged();
    },
  });
  return (
    <section className="panel profile-data">
      <details>
        <summary>CV storage and profile data</summary>
        <p>
          Original files and raw extracted text are removed 30 days after approval unless you choose
          to keep them. Pending drafts are retained. Reviewed facts and their evidence stay until
          you delete the profile.
        </p>
        {documents.isPending ? (
          <p role="status">Loading stored CVs…</p>
        ) : documents.isError ? (
          <>
            <p role="alert">{errorMessage(documents.error)}</p>
            <Button onClick={() => void documents.refetch()}>Reload stored CVs</Button>
          </>
        ) : (
          <>
            {documents.data.documents.length === 0 && <p>No CV documents stored.</p>}
            <ul className="document-list">
              {documents.data.documents.map((doc) => (
                <li key={doc.id}>
                  <h3>CV uploaded {new Date(doc.created_at).toLocaleString()}</h3>
                  {doc.deleted_at ? (
                    <p>Original file and raw text removed.</p>
                  ) : (
                    <>
                      <p>
                        {doc.media_type === 'application/pdf'
                          ? 'PDF'
                          : doc.media_type === 'text/plain'
                            ? 'TXT'
                            : 'DOCX'}{' '}
                        · {Math.ceil(doc.size / 1024)} KB
                        {doc.approved_at ? ' · Approved' : ' · Not yet approved'}
                      </p>
                      <label className="storage-choice">
                        <input
                          type="checkbox"
                          checked={retention[doc.id] ?? doc.retain_original}
                          disabled={change.isPending}
                          onChange={(e) => {
                            const retain = e.currentTarget.checked;
                            setRetention((current) => ({ ...current, [doc.id]: retain }));
                            change.mutate({ id: doc.id, retain });
                          }}
                        />
                        Keep this original until I delete it
                      </label>
                      <div className="button-row">
                        <Button asChild variant="secondary">
                          <a href={`/api/v1/profile/documents/${doc.id}/download`}>
                            Download original
                          </a>
                        </Button>
                        <Button
                          variant="quiet"
                          disabled={change.isPending}
                          onClick={() => setDeleteId(doc.id)}
                        >
                          Remove original
                        </Button>
                      </div>
                      {deleteId === doc.id && (
                        <div className="notice">
                          <p>
                            Remove this original file and raw text? Saved draft and reviewed facts
                            remain. Pending analysis of this file will be cancelled. An external
                            request already underway cannot be recalled.
                          </p>
                          <div className="button-row">
                            <Button
                              disabled={change.isPending}
                              onClick={() => change.mutate({ id: doc.id })}
                            >
                              Confirm removal
                            </Button>
                            <Button variant="quiet" onClick={() => setDeleteId(undefined)}>
                              Keep original
                            </Button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
            <div className="button-row">
              {offset > 0 && (
                <Button variant="secondary" onClick={() => setOffset(Math.max(0, offset - 20))}>
                  Previous CVs
                </Button>
              )}
              {documents.data.next_offset !== null && (
                <Button variant="secondary" onClick={() => setOffset(documents.data.next_offset!)}>
                  Older CVs
                </Button>
              )}
            </div>
          </>
        )}
        {change.isError && <p role="alert">{errorMessage(change.error)}</p>}
        <details className="purge-panel">
          <summary>Delete profile and all CV data</summary>
          <p>
            This removes the active profile, its history, drafts, original CVs, job assessments and
            feedback notes and notification summary contents. Existing backups follow their separate
            retention policy. Billing metadata is retained without CV content.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              purge.mutate();
            }}
          >
            <div className="field">
              <label htmlFor="purge-confirmation">Type DELETE PROFILE to confirm</label>
              <input
                id="purge-confirmation"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
              />
            </div>
            <Button disabled={confirmation !== 'DELETE PROFILE' || purge.isPending}>
              {purge.isPending ? 'Deleting…' : 'Delete profile and CVs'}
            </Button>
          </form>
          {purge.isError && (
            <p ref={errorRef} role="alert">
              {errorMessage(purge.error)}
            </p>
          )}
        </details>
        {purge.isSuccess && <p role="status">Profile and CV data deleted.</p>}
      </details>
    </section>
  );
}
