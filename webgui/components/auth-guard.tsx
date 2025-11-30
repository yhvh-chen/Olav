'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';

// 公开路由 - 不需要认证检查
const PUBLIC_PATHS = ['/login'];

interface AuthGuardProps {
  children: React.ReactNode;
}

function AuthGuardContent({ children }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token } = useAuthStore();
  const [mounted, setMounted] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const isPublicPath = PUBLIC_PATHS.includes(pathname);
    const hasUrlToken = searchParams.get('token');
    
    // 根路径由其自身处理（它会验证 token 并跳转）
    if (pathname === '/') {
      setChecked(true);
      return;
    }

    // 公开路由：
    // - 如果 URL 有 token 参数，让页面自己处理验证
    // - 如果没有 URL token 但已有存储 token，不自动跳转（让用户可以重新输入）
    if (isPublicPath) {
      setChecked(true);
      return;
    }

    // 私有路由需要 token
    if (!token) {
      router.replace('/login');
      return;
    }

    setChecked(true);
  }, [mounted, token, pathname, router, searchParams]);

  // 等待客户端挂载
  if (!mounted || !checked) {
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
