/**
 * Zustand Store - Authentication State
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@/lib/api/types';
import { getMe } from '@/lib/api/client';

interface AuthState {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  error: string | null;
  
  // 计算属性
  isAuthenticated: boolean;
  
  // Single Token 模式
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  validateToken: (token: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isLoading: false,
      error: null,

      // 计算属性 - 使用 getter
      get isAuthenticated() {
        return !!get().token;
      },

      // Single Token 模式
      setToken: (token: string) => {
        set({ token, error: null });
      },

      setUser: (user: User) => {
        set({ user });
      },

      // 验证 Token 并获取用户信息
      validateToken: async (token: string) => {
        set({ isLoading: true, error: null });
        
        try {
          const user = await getMe(token);
          set({ 
            token, 
            user, 
            isLoading: false,
            error: null,
          });
          return true;
        } catch (err) {
          set({ 
            isLoading: false, 
            error: err instanceof Error ? err.message : 'Token 验证失败',
          });
          return false;
        }
      },

      logout: () => {
        set({ token: null, user: null, error: null });
      },

      clearError: () => {
        set({ error: null });
      },
    }),
    {
      name: 'olav-auth',
      partialize: (state) => ({ 
        token: state.token, 
        user: state.user,
      }),
    }
  )
);
