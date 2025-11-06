"use client";

export const dynamic = 'force-dynamic';

import { useAuthStore } from '@/store/auth';
import { Loader2, User as UserIcon, Mail, CreditCard } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/Button';
import { stripeApi } from '@/lib/api';

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
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 flex">
      <Sidebar />
      <main className="flex-1 px-6 py-8 max-w-5xl">
        <h1 className="text-3xl font-bold mb-6">Paramètres du compte</h1>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">Profil</h2>
            <div className="space-y-3 text-gray-700">
              <p className="flex items-center gap-2"><UserIcon className="w-4 h-4 text-gray-500"/> {userData?.first_name || userData?.id || '—'} {userData?.last_name || ''}</p>
              <p className="flex items-center gap-2"><Mail className="w-4 h-4 text-gray-500"/> {user.email}</p>
              <div className="mt-2 p-3 rounded-lg bg-gradient-to-r from-primary-50 to-purple-50 border border-primary-100">
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">Crédits disponibles</p>
                <p className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent">{userData?.credits ?? 0}</p>
                <p className="text-xs text-gray-600 mt-1">1 crédit = 1 seconde</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">Abonnement</h2>
            <div className="space-y-3 text-gray-700">
              <p className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-gray-500"/> Plan actuel: {userData?.plan || '—'}</p>
              <p className="text-sm text-gray-600">Gérez votre abonnement et vos factures via le portail Stripe.</p>
              <Button
                onClick={async () => {
                  try {
                    const res = await stripeApi.portal(user.id);
                    if (res.url) window.location.href = res.url;
                  } catch (e) {
                    console.error(e);
                  }
                }}
              >Gérer mon abonnement</Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
