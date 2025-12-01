'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/lib/stores/auth-store';

// Public routes - no auth check needed
const PUBLIC_PATHS = ['/login'];

interface AuthGuardProps {
  children: React.ReactNode;
}

function AuthGuardContent({ children }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token } = useAuthStore();
  const hasHydrated = useHasHydrated();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!hasHydrated) return;

    const isPublicPath = PUBLIC_PATHS.includes(pathname);
    const hasUrlToken = searchParams.get('token');
    
    // Root path handled by itself
    if (pathname === '/') {
      setChecked(true);
      return;
    }

    // Public routes
    if (isPublicPath) {
      setChecked(true);
      return;
    }

    // Private routes need token
    if (!token) {
      router.replace('/login');
      return;
    }

    setChecked(true);
  }, [hasHydrated, token, pathname, router, searchParams]);

  // Wait for hydration and check
  if (!hasHydrated || !checked) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}

export function AuthGuard({ children }: AuthGuardProps) {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    }>
      <AuthGuardContent>{children}</AuthGuardContent>
    </Suspense>
  );
}
