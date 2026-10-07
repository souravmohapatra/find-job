import { useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Eye, EyeOff, BriefcaseBusiness } from 'lucide-react';
import { api, errorMessage } from '../../lib/api';
import { Button } from '../../components/ui/button';
const schema = z.object({
  username: z.string().trim().min(1, 'Enter your username.').max(100),
  password: z.string().min(1, 'Enter your password.').max(1024),
});
type Credentials = z.infer<typeof schema>;
export function Login() {
  const client = useQueryClient();
  const [visible, setVisible] = useState(false);
  const alert = useRef<HTMLDivElement>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Credentials>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });
  const mutation = useMutation({
    mutationFn: api.login,
    gcTime: 0,
    onSuccess: (session) => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'session' });
      client.setQueryData(['session'], session);
    },
    onError: () => requestAnimationFrame(() => alert.current?.focus()),
  });
  return (
    <main id="main" className="login-layout">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand">
          <BriefcaseBusiness aria-hidden="true" size={24} />
          <span>Job Finder</span>
        </div>
        <h1 id="login-title">A little closer to your next role.</h1>
        <p className="muted">Sign in to your private workspace.</p>
        <form
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          noValidate
          aria-busy={mutation.isPending}
        >
          {mutation.isError && (
            <div ref={alert} className="error" role="alert" tabIndex={-1}>
              {errorMessage(mutation.error)}
            </div>
          )}
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              aria-invalid={!!errors.username}
              aria-describedby={errors.username ? 'username-error' : undefined}
              {...register('username')}
            />
            {errors.username && (
              <p id="username-error" className="field-error">
                {errors.username.message}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-field">
              <input
                id="password"
                type={visible ? 'text' : 'password'}
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? 'password-error' : undefined}
                {...register('password')}
              />
              <Button
                type="button"
                variant="quiet"
                onClick={() => setVisible(!visible)}
                aria-label={visible ? 'Hide password' : 'Show password'}
                aria-pressed={visible}
              >
                {visible ? (
                  <EyeOff size={18} aria-hidden="true" />
                ) : (
                  <Eye size={18} aria-hidden="true" />
                )}
              </Button>
            </div>
            {errors.password && (
              <p id="password-error" className="field-error">
                {errors.password.message}
              </p>
            )}
          </div>
          <Button type="submit" className="full-width" disabled={mutation.isPending}>
            {mutation.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
        <p className="login-note">Access is managed by the owner of this installation.</p>
      </section>
      <p className="login-footer">Your companies. Your preferences. A wider view.</p>
    </main>
  );
}
