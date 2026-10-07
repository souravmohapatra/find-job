import { ProfileData } from './data';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, ArrowLeft } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { api, errorMessage, type Session } from '../../lib/api';
import { profileApi, type Accepted, type Draft } from './api';
import { ProfileEditor } from './editor';
function UploadCv({
  csrf,
  mock,
  onUploaded,
}: {
  csrf: string;
  mock: boolean;
  onUploaded: (result: Accepted) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [retain, setRetain] = useState(false);
  const [localError, setLocalError] = useState('');
  const key = useRef(crypto.randomUUID());
  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a CV.');
      return profileApi.upload(file, consent, retain, key.current, csrf);
    },
    onSuccess: onUploaded,
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setLocalError('Choose a PDF, DOCX or TXT file.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setLocalError('Choose a file of at most 10 MiB.');
      return;
    }
    setLocalError('');
    upload.mutate();
  }
  return (
    <section className="panel upload-panel">
      <h2>
        <Upload size={20} aria-hidden="true" />
        Start with your CV
      </h2>
      <p className="section-intro">
        Upload a text PDF, DOCX or TXT file (up to 10 MiB; PDF up to 50 pages). You’ll review and
        correct the extracted profile before it is used for matching.
      </p>
      <form onSubmit={submit}>
        <label className="file-label" htmlFor="cv-file">
          CV file
        </label>
        <input
          id="cv-file"
          type="file"
          accept=".pdf,.docx,.txt"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            key.current = crypto.randomUUID();
          }}
        />
        <p className="field-help">
          Original files are parsed locally. In live mode, extracted CV text is sent to OpenRouter
          and its routed provider. Unnecessary contact details are removed where possible; this is
          not anonymization.
        </p>
        {mock ? (
          <p className="notice">
            Development mode: local parsing with mock analysis. No AI request will be made.
          </p>
        ) : (
          <label className="check-label">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            I agree to send extracted CV text to OpenRouter and its provider.
          </label>
        )}
        <label className="check-label">
          <input
            type="checkbox"
            checked={retain}
            onChange={(e) => {
              setRetain(e.target.checked);
              key.current = crypto.randomUUID();
            }}
          />
          Keep my original CV after approval
        </label>
        <p className="field-help">
          Otherwise the original and raw extracted text are scheduled for removal 30 days after
          approval. Reviewed facts and minimal evidence are retained until you delete your profile.
        </p>
        {(localError || upload.isError) && (
          <p role="alert" className="error">
            {localError || errorMessage(upload.error)}
          </p>
        )}
        <Button type="submit" disabled={upload.isPending || (!mock && !consent)}>
          {upload.isPending ? 'Uploading…' : 'Upload and analyse'}
        </Button>
      </form>
    </section>
  );
}
function DraftReview({
  id,
  csrf,
  onBack,
  onSaved,
}: {
  id: string;
  csrf: string;
  onBack: () => void;
  onSaved: () => void;
}) {
  const client = useQueryClient();
  const draft = useQuery({
    queryKey: ['profile-draft', id],
    queryFn: () => profileApi.draft(id),
    refetchInterval: (q) => (q.state.data?.status === 'processing' ? 2000 : false),
    refetchIntervalInBackground: false,
  });
  const operationId = draft.data?.operation_id;
  const operation = useQuery({
    queryKey: ['operation', operationId],
    queryFn: () => profileApi.operation(operationId!),
    enabled: !!operationId,
    refetchInterval: (q) =>
      ['queued', 'running'].includes(q.state.data?.state ?? 'queued') ? 2000 : false,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    if (operation.data?.state === 'succeeded')
      void client.invalidateQueries({ queryKey: ['profile-draft', id] });
  }, [client, id, operation.data?.state]);
  const retry = useMutation({
    mutationFn: () => profileApi.retry(operationId!, csrf),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['operation', operationId] });
      await client.invalidateQueries({ queryKey: ['profile-draft', id] });
    },
  });
  return (
    <>
      <Button variant="quiet" onClick={onBack}>
        <ArrowLeft size={16} aria-hidden="true" />
        Back to profile
      </Button>
      {draft.isPending ? (
        <p role="status" className="panel">
          Opening your draft…
        </p>
      ) : draft.isError ? (
        <div className="error" role="alert">
          {errorMessage(draft.error)}
          <Button variant="secondary" onClick={() => void draft.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          {draft.data.status === 'review' ? (
            <ProfileEditor
              key={draft.data.id}
              initial={draft.data}
              draft={draft.data}
              csrf={csrf}
              onSaved={onSaved}
            />
          ) : (
            <section className="panel">
              <h2>
                {operation.data?.state === 'cancelled'
                  ? 'Analysis cancelled'
                  : operation.data?.state === 'failed' || operation.data?.state === 'blocked'
                    ? 'Your CV needs attention'
                    : 'Preparing your profile'}
              </h2>
              <p role="status">
                {operation.data?.progress ??
                  'Waiting for processing. You can leave this page and return later.'}
              </p>
              {operation.isError && (
                <p className="field-error" role="alert">
                  {errorMessage(operation.error)}
                </p>
              )}
              {operation.data && ['failed', 'blocked'].includes(operation.data.state) && (
                <Button
                  variant="secondary"
                  disabled={retry.isPending}
                  onClick={() => retry.mutate()}
                >
                  Retry processing
                </Button>
              )}
              {retry.isError && (
                <p role="alert" className="field-error">
                  {errorMessage(retry.error)}
                </p>
              )}
            </section>
          )}
          {draft.data.document_available && (
            <p className="document-link">
              <a href={`/api/v1/profile/documents/${draft.data.document_id}/download`}>
                Download original CV
              </a>
            </p>
          )}
        </>
      )}
    </>
  );
}
export function ProfilePage() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');
  const profile = useQuery({ queryKey: ['profile'], queryFn: profileApi.profile });
  const status = useQuery({ queryKey: ['status'], queryFn: api.status });
  const session = client.getQueryData<Session>(['session']);
  const csrf = session?.csrf_token ?? '';
  async function uploaded(result: Accepted) {
    await client.invalidateQueries({ queryKey: ['profile'] });
    const current = client.getQueryData<Awaited<ReturnType<typeof profileApi.profile>>>([
      'profile',
    ]);
    const found = current?.drafts.find((d) => d.document_id === result.resource_id);
    if (found) setSelected(found.id);
    setEditing(false);
  }
  async function purged() {
    setNotice('Profile and CV data deleted. You can upload a new CV when ready.');
    setSelected(null);
    setEditing(false);
    await client.invalidateQueries({ queryKey: ['profile'] });
    await client.invalidateQueries({ queryKey: ['status'] });
  }
  async function saved() {
    setNotice('Profile saved. Future matching will use your reviewed experience and preferences.');
    setSelected(null);
    setEditing(false);
    await client.invalidateQueries({ queryKey: ['profile'] });
    await client.invalidateQueries({ queryKey: ['status'] });
  }
  return (
    <>
      <p className="eyebrow">YOUR DIRECTION</p>
      <h1 tabIndex={-1}>Profile</h1>
      <p className="page-description">
        Your experience is the starting point. Your preferences set the direction.
      </p>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {selected ? (
        <DraftReview
          id={selected}
          csrf={csrf}
          onBack={() => setSelected(null)}
          onSaved={() => void saved()}
        />
      ) : profile.isPending ? (
        <p className="panel" role="status">
          Loading your profile…
        </p>
      ) : profile.isError ? (
        <div className="error" role="alert">
          {errorMessage(profile.error)}
          <Button variant="secondary" onClick={() => void profile.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          {editing ? (
            <>
              <Button variant="quiet" onClick={() => setEditing(false)}>
                <ArrowLeft size={16} aria-hidden="true" />
                Back to saved profile
              </Button>
              <ProfileEditor initial={profile.data} csrf={csrf} onSaved={() => void saved()} />
            </>
          ) : (
            <>
              {profile.data.revision_id != null && (
                <section className="panel">
                  <div className="section-heading">
                    <h2>Your reviewed profile</h2>
                    <Button variant="secondary" onClick={() => setEditing(true)}>
                      Edit profile
                    </Button>
                  </div>
                  <p className="preserve-lines">{profile.data.facts.summary}</p>
                  <dl className="profile-summary">
                    <div>
                      <dt>Desired roles</dt>
                      <dd>{profile.data.preferences.desired_roles?.join(', ')}</dd>
                    </div>
                    <div>
                      <dt>Domains</dt>
                      <dd>
                        {profile.data.preferences.domain_mode === 'open'
                          ? 'Open to any domain'
                          : `${profile.data.preferences.domain_mode === 'expand' ? 'Prefer' : 'Focus on'} ${profile.data.preferences.domains?.join(', ')}`}
                      </dd>
                    </div>
                    <div>
                      <dt>Experience</dt>
                      <dd>
                        {profile.data.experience?.maximum_years == null
                          ? 'Not enough dated information'
                          : `${profile.data.experience.minimum_years}–${profile.data.experience.maximum_years} years`}
                        {profile.data.experience?.basis === 'user_override'
                          ? ' (your estimate)'
                          : ''}
                      </dd>
                    </div>
                  </dl>
                  <p className="field-help">
                    Reviewed revision {profile.data.revision}. Changes create a new revision and
                    queue matching updates.
                  </p>
                </section>
              )}
              {profile.data.drafts.length > 0 && (
                <section className="panel">
                  <h2>CV drafts</h2>
                  <ul className="draft-list">
                    {profile.data.drafts.map(
                      (draft: Pick<Draft, 'id' | 'status'> & { created_at: string }) => (
                        <li key={draft.id}>
                          <FileText size={20} aria-hidden="true" />
                          <span>
                            {draft.status === 'review'
                              ? 'Ready for review'
                              : draft.status === 'processing'
                                ? 'Processing'
                                : draft.status === 'cancelled'
                                  ? 'Analysis cancelled'
                                  : draft.status === 'failed'
                                    ? 'Processing failed'
                                    : 'Needs attention'}
                            <small>{new Date(draft.created_at).toLocaleString()}</small>
                          </span>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              setNotice('');
                              setSelected(draft.id);
                            }}
                          >
                            Open draft
                          </Button>
                        </li>
                      ),
                    )}
                  </ul>
                </section>
              )}
              <ProfileData csrf={csrf} onPurged={() => void purged()} />
              <UploadCv
                csrf={csrf}
                mock={status.data?.integration_mode === 'mock'}
                onUploaded={uploaded}
              />
            </>
          )}
        </>
      )}
    </>
  );
}
