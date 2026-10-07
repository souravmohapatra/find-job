import type { components } from '../../lib/api-types';
import { request } from '../../lib/api';
type Schemas = components['schemas'];
export type Profile = Schemas['ProfileView'];
export type Snapshot = Schemas['ProfileSnapshot'];
export type Draft = Schemas['DraftView'];
export type Facts = Schemas['Facts'];
export type Preferences = Schemas['Preferences'];
export type ProfileInput = Schemas['ProfileInput'];
export type Operation = Schemas['OperationView'];
export type Accepted = Schemas['OperationAccepted'];
export const profileApi = {
  async profile() {
    return (await request('/profile')) as Profile;
  },
  async draft(id: string) {
    return (await request(`/profile/drafts/${id}`)) as Draft;
  },
  async operation(id: string) {
    return (await request(`/operations/${id}`)) as Operation;
  },
  async retry(id: string, csrf: string) {
    return request(`/operations/${id}/retry`, { method: 'POST' }, csrf);
  },
  async upload(file: File, consent: boolean, retain: boolean, key: string, csrf: string) {
    const body = new FormData();
    body.set('file', file);
    body.set('consent', String(consent));
    body.set('retain_original', String(retain));
    return (await request(
      '/profile/documents',
      { method: 'POST', headers: { 'Idempotency-Key': key }, body },
      csrf,
    )) as Accepted;
  },
  async saveDraft(id: string, version: number, body: ProfileInput, csrf: string) {
    return (await request(
      `/profile/drafts/${id}`,
      { method: 'PATCH', headers: { 'If-Match': `"${version}"` }, body: JSON.stringify(body) },
      csrf,
    )) as Draft;
  },
  async activate(id: string, version: number, baseRevision: number, csrf: string) {
    return (await request(
      `/profile/drafts/${id}/activate`,
      {
        method: 'POST',
        headers: { 'If-Match': `"${baseRevision}"` },
        body: JSON.stringify({ draft_version: version, reviewed: true }),
      },
      csrf,
    )) as Snapshot;
  },
  async reconcile(id: string, version: number, revision: number, body: ProfileInput, csrf: string) {
    return (await request(
      `/profile/drafts/${id}/reconcile`,
      {
        method: 'POST',
        headers: { 'If-Match': `"${revision}"` },
        body: JSON.stringify({ draft_version: version, reviewed: true, profile: body }),
      },
      csrf,
    )) as Draft;
  },
  async save(revision: number, body: ProfileInput, csrf: string) {
    return (await request(
      '/profile',
      { method: 'PATCH', headers: { 'If-Match': `"${revision}"` }, body: JSON.stringify(body) },
      csrf,
    )) as Snapshot;
  },
};
