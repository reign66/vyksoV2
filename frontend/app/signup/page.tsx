'use client';

import { useRouter } from 'next/navigation';
import LoginPage from '../login/page';

export default function SignupPage() {
  // Same as login - Google OAuth handles both
  return <LoginPage />;
}
