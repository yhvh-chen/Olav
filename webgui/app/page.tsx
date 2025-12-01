'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getMe } from '@/lib/api/client';

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { token: storedToken, setToken, setUser, _hasHydrated } = useAuthStore();
  const [status, setStatus] = useState<'hydrating' | 'checking' | 'redirecting'>('hydrating');

  useEffect(() => {
    // Wait for Zustand to hydrate from localStorage first
    if (!_hasHydrated) {
      return;
    }

    const handleAuth = async () => {
      setStatus('checking');
      const urlToken = searchParams.get('token');
      
      if (urlToken) {
        // URL 带 token - 直接在根页面验证，不跳转到 login
        try {
          const user = await getMe(urlToken);
          setToken(urlToken);
          setUser(user);
          setStatus('redirecting');
          router.replace('/chat');
        } catch (err) {
          console.error('Token validation failed:', err);
          // Token 无效，清除并跳转登录页显示错误
          router.replace('/login?error=invalid_token');
        }
      } else if (storedToken) {
        // 有存储的 token，验证后跳转
        try {
          await getMe(storedToken);
          setStatus('redirecting');
          router.replace('/chat');
        } catch (err) {
          // 存储的 token 过期，清除后去登录
          useAuthStore.getState().logout();
          router.replace('/login');
        }
      } else {
        // 无 token，去登录页
        router.replace('/login');
      }
    };

    handleAuth();
  }, [router, searchParams, storedToken, setToken, setUser, _hasHydrated]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center">
        <div className="animate-spin mx-auto h-8 w-8 rounded-full border-2 border-primary border-t-transparent" />
        <p className="mt-4 text-muted-foreground">
          {status === 'hydrating' ? '加载中...' : status === 'checking' ? '正在验证...' : '正在跳转...'}
        </p>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="animate-spin h-8 w-8 rounded-full border-2 border-primary border-t-transparent" />
      </div>
    }>
      <HomeContent />
    </Suspense>
  );
}
