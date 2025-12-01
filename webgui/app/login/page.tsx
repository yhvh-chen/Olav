'use client';

import { useState, useEffect, Suspense, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getMe } from '@/lib/api/client';

function LoginContent() {
  const [manualToken, setManualToken] = useState('');
  const [error, setError] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [autoValidating, setAutoValidating] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const validationAttempted = useRef(false);
  
  const { setToken: storeToken, setUser, logout } = useAuthStore();

  // 验证 Token 的通用函数
  const validateToken = async (tokenToValidate: string): Promise<boolean> => {
    try {
      console.log('Validating token (first 10 chars):', tokenToValidate.substring(0, 10) + '...');
      const user = await getMe(tokenToValidate);
      console.log('Token validated successfully, user:', user);
      storeToken(tokenToValidate);
      setUser(user);
      router.replace('/chat');
      return true;
    } catch (err) {
      console.error('Token validation failed:', err);
      // Show more detailed error
      if (err instanceof Error) {
        console.error('Error details:', err.message, err.name);
      }
      // 清除可能无效的存储 token
      logout();
      return false;
    }
  };

  // 处理 URL 参数中的错误或 token
  useEffect(() => {
    // 防止重复验证
    if (validationAttempted.current) return;
    
    const urlError = searchParams.get('error');
    const urlToken = searchParams.get('token');
    
    if (urlError === 'invalid_token') {
      setError('Token 无效或已过期，请重新输入');
      validationAttempted.current = true;
      return;
    }
    
    // 如果 URL 有 token，自动验证（通常由根页面处理，这是 fallback）
    if (urlToken) {
      validationAttempted.current = true;
      setAutoValidating(true);
      validateToken(urlToken).then(success => {
        if (!success) {
          setError('URL 中的 Token 无效或已过期');
        }
        setAutoValidating(false);
      });
    } else {
      validationAttempted.current = true;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 手动提交 Token
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualToken.trim()) {
      setError('请输入 Token');
      return;
    }

    setIsValidating(true);
    setError('');

    const success = await validateToken(manualToken.trim());
    if (!success) {
      setError('Token 无效或已过期');
    }
    setIsValidating(false);
  };

  // 自动验证中的加载状态
  if (autoValidating) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin mx-auto h-8 w-8 rounded-full border-2 border-primary border-t-transparent" />
          <p className="mt-4 text-muted-foreground">正在验证...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-6">
        {/* Logo & Title */}
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <span className="text-3xl">🔐</span>
          </div>
          <h1 className="mt-4 text-2xl font-bold">OLAV WebGUI</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            企业网络运维智能助手
          </p>
        </div>

        {/* Token Input Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="token" className="block text-sm font-medium mb-1">
              Access Token
            </label>
            <input
              id="token"
              type="text"
              value={manualToken}
              onChange={(e) => setManualToken(e.target.value)}
              placeholder="粘贴 Token..."
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={isValidating}
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isValidating || !manualToken.trim()}
            className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isValidating ? '验证中...' : '进入系统'}
          </button>
        </form>

        {/* Help Section */}
        <div className="rounded-lg border border-border bg-secondary/30 p-4 text-sm">
          <h3 className="font-medium">💡 如何获取 Token</h3>
          <div className="mt-2 space-y-2 text-muted-foreground">
            <p>启动后端后，控制台会打印：</p>
            <div className="rounded bg-black/30 p-2 text-xs font-mono">
              <p className="text-green-400">🌐 WebGUI URL:</p>
              <p className="text-blue-400">   http://localhost:3100?token=xxx</p>
            </div>
            <p className="mt-2">两种方式进入：</p>
            <ul className="ml-4 list-disc space-y-1">
              <li>直接点击链接（自动登录）</li>
              <li>复制 token 值粘贴到上方输入框</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center">
        <div className="animate-spin mx-auto h-8 w-8 rounded-full border-2 border-primary border-t-transparent" />
        <p className="mt-4 text-muted-foreground">加载中...</p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <LoginContent />
    </Suspense>
  );
}
