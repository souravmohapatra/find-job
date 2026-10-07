import { useQuery } from '@tanstack/react-query';
import { api, request } from '../../lib/api';
import type { components } from '../../lib/api-types';
export type Schemas = components['schemas'];
export async function read<T>(path: string): Promise<T> {
  return (await request(path)) as T;
}
export function useCsrf() {
  const session = useQuery({ queryKey: ['session'], queryFn: api.session });
  return session.data?.csrf_token ?? '';
}
export function date(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not yet';
}
