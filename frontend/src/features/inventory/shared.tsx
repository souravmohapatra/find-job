import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '../../lib/api';
import { read, type Schemas } from './data';
import { Button } from '../../components/ui/button';
export function Failure({
  error,
  retry,
  focus = false,
}: {
  error: unknown;
  retry?: () => void;
  focus?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focus) ref.current?.focus();
  }, [error, focus]);
  return (
    <div role="alert" tabIndex={-1} ref={ref}>
      <p>{errorMessage(error)}</p>
      {retry && (
        <Button variant="secondary" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}
export function OperationStatus({ id }: { id?: string }) {
  const client = useQueryClient();
  const processed = useRef<string | undefined>(undefined);
  const operation = useQuery({
    queryKey: ['inventory-operation', id],
    queryFn: () => read<Schemas['OperationView']>(`/operations/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.state ?? 'queued') ? 2000 : false,
  });
  useEffect(() => {
    if (
      operation.data &&
      !['queued', 'running'].includes(operation.data.state) &&
      processed.current !== id
    ) {
      processed.current = id;
      void client.invalidateQueries({ queryKey: ['sources'] });
      void client.invalidateQueries({ queryKey: ['company'] });
    }
  }, [client, id, operation.data]);
  if (!id) return null;
  if (operation.isError)
    return <Failure error={operation.error} retry={() => void operation.refetch()} />;
  return (
    <p role="status">
      {operation.data?.error_message || operation.data?.progress || 'Waiting to start…'}
    </p>
  );
}
