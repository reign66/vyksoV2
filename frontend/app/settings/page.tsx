export const dynamic = 'force-dynamic';

'use client';

import { useAuthStore } from '@/store/auth';
import { Logo } from '@/components/Logo';
import { Loader2, User as UserIcon, Mail, Badge, CreditCard } from 'lucide-react';

export default function SettingsPage() {
  const { user, userData, loading } = useAuthStore();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-600">
        Veuillez vous connecter pour accéder aux paramètres.
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 shadow-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Logo />
          <div className="text-sm text-gray-500">Settings</div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 max-w-4xl">
        <h1 className="text-3xl font-bold mb-6">Paramètres du compte</h1>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">Profil</h2>
            <div className="space-y-3 text-gray-700">
              <p className="flex items-center gap-2"><UserIcon className="w-4 h-4 text-gray-500"/> {userData?.first_name || '—'} {userData?.last_name || ''}</p>
              <p className="flex items-center gap-2"><Mail className="w-4 h-4 text-gray-500"/> {user.email}</p>
              <p className="flex items-center gap-2"><Badge className="w-4 h-4 text-gray-500"/> ID: {user.id}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">Abonnement</h2>
            <div className="space-y-3 text-gray-700">
              <p className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-gray-500"/> Plan actuel: {userData?.plan || '—'}</p>
              <p className="text-sm text-gray-600">Votre plan décompte des secondes vidéo, sans différence de crédits entre les modèles.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
