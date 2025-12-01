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

  // Common function to validate token
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
      // Clear potentially invalid stored token
      logout();
      return false;
    }
  };

  // Handle errors or tokens in URL parameters
  useEffect(() => {
    // Prevent duplicate validation
    if (validationAttempted.current) return;
    
    const urlError = searchParams.get('error');
    const urlToken = searchParams.get('token');
    
    if (urlError === 'invalid_token') {
      setError('Token is invalid or expired, please re-enter');
      validationAttempted.current = true;
      return;
    }
    
    // If URL has token, auto-validate (usually handled by root page, this is fallback)
    if (urlToken) {
      validationAttempted.current = true;
      setAutoValidating(true);
      validateToken(urlToken).then(success => {
        if (!success) {
          setError('Token in URL is invalid or expired');
        }
        setAutoValidating(false);
      });
    } else {
      validationAttempted.current = true;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Manually submit Token
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualToken.trim()) {
      setError('Please enter Token');
      return;
    }

    setIsValidating(true);
    setError('');

    const success = await validateToken(manualToken.trim());
    if (!success) {
      setError('Token is invalid or expired');
    }
    setIsValidating(false);
  };

  // Loading state during auto-validation
  if (autoValidating) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin mx-auto h-8 w-8 rounded-full border-2 border-primary border-t-transparent" />
          <p className="mt-4 text-muted-foreground">Validating...</p>
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
            Enterprise Network Operations Intelligent Assistant
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
              placeholder="Paste Token..."
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
            {isValidating ? 'Validating...' : 'Enter System'}
          </button>
        </form>

        {/* Help Section */}
        <div className="rounded-lg border border-border bg-secondary/30 p-4 text-sm">
          <h3 className="font-medium">💡 How to get Token</h3>
          <div className="mt-2 space-y-2 text-muted-foreground">
            <p>After starting the backend, the console will print:</p>
            <div className="rounded bg-black/30 p-2 text-xs font-mono">
              <p className="text-green-400">🌐 WebGUI URL:</p>
              <p className="text-blue-400">   http://localhost:3100?token=xxx</p>
            </div>
            <p className="mt-2">Two ways to enter:</p>
            <ul className="ml-4 list-disc space-y-1">
              <li>Click the link directly (auto-login)</li>
              <li>Copy the token value and paste it into the input box above</li>
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
        <p className="mt-4 text-muted-foreground">Loading...</p>
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
