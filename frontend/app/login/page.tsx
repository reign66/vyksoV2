'use client';
export const dynamic = 'force-dynamic';

import { useEffect, useState, Suspense } from 'react';

// Force dynamic rendering to avoid build-time Supabase initialization
import { useRouter, useSearchParams } from 'next/navigation';
import { supabase } from '@/lib/supabase/client';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/Button';
import { useAuthStore } from '@/store/auth';
import toast from 'react-hot-toast';

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user && !loading) {
      router.push('/dashboard');
    }
  }, [user, loading, router]);

  useEffect(() => {
    // Check for error in URL params (from callback redirect)
    const errorParam = searchParams.get('error');
    if (errorParam) {
      const decodedError = decodeURIComponent(errorParam);
      setError(decodedError);
      toast.error(decodedError);
      // Clean up URL
      router.replace('/login');
    }
  }, [searchParams, router]);

  const handleGoogleLogin = async () => {
    try {
      setError(null);
      
      // Get the current origin (works for both localhost and Vercel)
      const redirectTo = `${window.location.origin}/auth/callback`;
      
      const { error, data } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo,
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
          },
        },
      });

      if (error) {
        console.error('OAuth error:', error);
        throw error;
      }

      // The redirect will happen automatically
      // No need to do anything else here
    } catch (error: any) {
      const errorMessage = error.message || 'Erreur lors de la connexion';
      setError(errorMessage);
      toast.error(errorMessage);
      console.error('Login error:', error);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 via-blue-50 to-purple-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8 border border-gray-100">
        <div className="text-center mb-8">
          <Logo className="justify-center mb-6" />
          <h1 className="text-4xl font-bold text-gray-900 mb-3 bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent">Bienvenue</h1>
          <p className="text-gray-600 text-lg">Connectez-vous pour commencer à créer des vidéos</p>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        <Button
          onClick={handleGoogleLogin}
          className="w-full mb-4 flex items-center justify-center gap-3 bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg hover:shadow-xl transition-all"
          size="lg"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="currentColor"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="currentColor"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="currentColor"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          Continuer avec Google
        </Button>

        <p className="text-center text-sm text-gray-500">
          En vous connectant, vous acceptez nos{' '}
          <a href="/terms" className="text-primary-600 hover:underline">
            conditions d&apos;utilisation
          </a>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    }>
      <LoginContent />
    </Suspense>
  );
}
