'use client';
export const dynamic = 'force-dynamic';

import { useRouter } from 'next/navigation';

// Force dynamic rendering to avoid build-time Supabase initialization
import LoginPage from '../login/page';

export default function SignupPage() {
  // Same as login - Google OAuth handles both
  return <LoginPage />;
}
