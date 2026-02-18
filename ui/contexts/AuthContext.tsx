'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, authApi, User } from '@/lib/api';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  register: (data: any) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // Check if user is logged in
    const token = localStorage.getItem('token');
    if (token) {
      api.setToken(token);
      loadUser();
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      router.replace('/login');
    };
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, [router]);

  const loadUser = async () => {
    try {
      const response = await authApi.getMe();
      if (response.data) {
        setUser(response.data);
      } else {
        // If we get an error, clear the token
        if (response.error) {
          api.setToken(null);
        }
      }
    } catch (error) {
      console.error('Error loading user:', error);
      api.setToken(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string): Promise<boolean> => {
    try {
      const response = await authApi.login({ email, password });
      const loginData = response.data as { access_token?: string } | undefined;
      if (loginData && loginData.access_token) {
        api.setToken(loginData.access_token);
        // Wait a bit for token to be set, then load user
        await new Promise(resolve => setTimeout(resolve, 100));
        await loadUser();
        return true;
      }
      return false;
    } catch (error) {
      console.error('Login error:', error);
      return false;
    }
  };

  const register = async (data: any): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await authApi.register(data);
      if (response.data) {
        setUser(response.data);
        return { success: true };
      }
      return { success: false, error: response.error || 'Registration failed' };
    } catch (error: any) {
      console.error('Registration error:', error);
      // Extract error message from response
      let errorMessage = 'Registration failed. Please try again.';
      const errorDetail = (error?.response?.data as { detail?: string | string[] } | undefined)?.detail;
      if (errorDetail) {
        errorMessage = typeof errorDetail === 'string' ? errorDetail : errorDetail.join(', ');
      } else if (error?.message) {
        errorMessage = error.message;
      } else if (typeof error === 'string') {
        errorMessage = error;
      }
      console.error('Full error details:', {
        error,
        response: error?.response,
        data: error?.response?.data,
        detail: error?.response?.data?.detail
      });
      return { success: false, error: errorMessage };
    }
  };

  const logout = () => {
    // Fire-and-forget audit log before clearing token
    api.post('/api/auth/logout', {}).catch(() => {});
    api.setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
        isAuthenticated: !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
