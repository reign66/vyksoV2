'use client';

import { useRouter } from 'next/navigation';

// Force dynamic rendering to avoid build-time Supabase initialization
export const dynamic = 'force-dynamic';
import LoginPage from '../login/page';

export default function SignupPage() {
  // Same as login - Google OAuth handles both
  return <LoginPage />;
}
