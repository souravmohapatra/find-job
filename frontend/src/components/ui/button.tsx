import type { ComponentProps } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva } from 'class-variance-authority';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
const styles = cva('button', {
  variants: {
    variant: { primary: 'button-primary', secondary: 'button-secondary', quiet: 'button-quiet' },
  },
  defaultVariants: { variant: 'primary' },
});
export function Button({
  asChild = false,
  variant = 'primary',
  className,
  ...props
}: ComponentProps<'button'> & { asChild?: boolean; variant?: 'primary' | 'secondary' | 'quiet' }) {
  const Component = asChild ? Slot : 'button';
  return <Component className={twMerge(clsx(styles({ variant }), className))} {...props} />;
}
