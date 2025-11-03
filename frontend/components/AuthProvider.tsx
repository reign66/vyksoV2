'use client';

import { useEffect } from 'react';
import { supabase } from '@/lib/supabase/client';
import { useAuthStore } from '@/store/auth';
import { useRouter, usePathname } from 'next/navigation';
import { User } from '@supabase/supabase-js';
import { userSyncApi } from '@/lib/api';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setLoading, fetchUserData } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Sync user data with backend after login
    const syncUser = async (user: User) => {
      try {
        // Extract name from user_metadata (Google OAuth provides this)
        const fullName = user.user_metadata?.full_name || user.user_metadata?.name || '';
        const firstName = user.user_metadata?.first_name || fullName.split(' ')[0] || null;
        const lastName = user.user_metadata?.last_name || fullName.split(' ').slice(1).join(' ') || null;

        // Sync with backend
        await userSyncApi.sync({
          id: user.id,
          email: user.email,
          user_metadata: {
            first_name: firstName,
            last_name: lastName,
            full_name: fullName,
          },
        }).catch((err) => console.error('Error syncing user:', err));

        // Fetch updated user data
        await fetchUserData(user.id);
      } catch (error) {
        console.error('Error in syncUser:', error);
      }
    };

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        syncUser(session.user);
      }
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        await syncUser(session.user);
        if (pathname === '/login' || pathname === '/signup') {
          router.push('/dashboard');
        }
      } else {
        if (pathname.startsWith('/dashboard')) {
          router.push('/login');
        }
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, [setUser, setLoading, fetchUserData, router, pathname]);

  return <>{children}</>;
}
