import { z } from 'zod';
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
const errorSchema = z.object({ code: z.string(), message: z.string() });
export const sessionSchema = z.object({ username: z.string(), csrf_token: z.string() });
export type Session = z.infer<typeof sessionSchema>;
export const statusSchema = z.object({
  environment: z.enum(['development', 'test', 'production']),
  integration_mode: z.enum(['mock', 'live']),
  profile_configured: z.boolean(),
  phase: z.string(),
});
export async function request(
  path: string,
  options: RequestInit = {},
  csrf?: string,
): Promise<unknown> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  if (csrf) headers.set('X-CSRF-Token', csrf);
  let response: Response;
  try {
    response = await fetch('/api/v1' + path, { ...options, headers, credentials: 'same-origin' });
  } catch {
    throw new ApiError(
      0,
      'network_error',
      'Cannot reach Job Finder. Check your connection and try again.',
    );
  }
  if (!response.ok) {
    const error = errorSchema.safeParse(await response.json().catch(() => null));
    throw new ApiError(
      response.status,
      error.success ? error.data.code : 'request_failed',
      error.success ? error.data.message : 'The request could not be completed. Please try again.',
    );
  }
  if (response.status === 204) return undefined;
  try {
    return await response.json();
  } catch {
    throw new ApiError(
      502,
      'invalid_response',
      'Job Finder returned an unreadable response. Please try again.',
    );
  }
}
export const api = {
  async session(): Promise<Session | null> {
    try {
      return sessionSchema.parse(await request('/auth/me'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  async login(values: { username: string; password: string }) {
    return sessionSchema.parse(
      await request('/auth/login', { method: 'POST', body: JSON.stringify(values) }),
    );
  },
  async logout(csrf: string) {
    await request('/auth/logout', { method: 'POST' }, csrf);
  },
  async status() {
    return statusSchema.parse(await request('/status'));
  },
};
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.';
}
