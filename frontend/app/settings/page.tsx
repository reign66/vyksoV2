"use client";

export const dynamic = 'force-dynamic';

import { useAuthStore } from '@/store/auth';
import { Logo } from '@/components/Logo';
import { Loader2, User as UserIcon, Mail, CreditCard, Settings, BadgeDollarSign, Sparkles, Video } from 'lucide-react';
import Link from 'next/link';
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

  const manageSubscription = async () => {
    if (!user) return;
    try {
      const res = await stripeApi.createPortal(user.id);
      if (res.url) window.location.href = res.url;
    } catch (e) {
      // silent fail; could toast
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 shadow-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Logo />
          <div className="text-sm text-gray-500">Paramètres</div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-6">
        <aside className="bg-white rounded-2xl border border-gray-200 p-4 h-fit sticky top-20">
          <nav className="flex flex-col gap-2">
            <Link href="/dashboard?tab=generate" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700"><Sparkles className="w-4 h-4"/> Générer</Link>
            <Link href="/dashboard?tab=gallery" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700"><Video className="w-4 h-4"/> Mes vidéos</Link>
            <Link href="/dashboard?tab=credits" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700"><CreditCard className="w-4 h-4"/> Secondes & Plans</Link>
            <Link href="/pricing" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700"><BadgeDollarSign className="w-4 h-4"/> Pricing</Link>
            <div className="px-4 py-3 rounded-lg flex items-center gap-2 bg-primary-50 text-primary-700"><Settings className="w-4 h-4"/> Paramètres</div>
          </nav>
        </aside>

        <main className="max-w-4xl">
          <h1 className="text-3xl font-bold mb-6">Paramètres du compte</h1>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">Profil</h2>
              <div className="space-y-3 text-gray-700">
                <p className="flex items-center gap-2"><UserIcon className="w-4 h-4 text-gray-500"/> {userData?.full_name || `${userData?.first_name || '—'} ${userData?.last_name || ''}`}</p>
                <p className="flex items-center gap-2"><Mail className="w-4 h-4 text-gray-500"/> {user.email}</p>
                <p className="text-sm text-gray-600">Créé le {userData?.created_at ? new Date(userData.created_at).toLocaleDateString('fr-FR') : ''}</p>
              </div>
            </div>
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">Abonnement</h2>
              <div className="space-y-3 text-gray-700">
                <p className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-gray-500"/> Plan actuel: {userData?.plan || '—'}</p>
                <p className="flex items-center gap-2"><BadgeDollarSign className="w-4 h-4 text-gray-500"/> Secondes disponibles: {userData?.credits ?? 0}</p>
                <p className="text-sm text-gray-600">Votre plan décompte des secondes vidéo (1 crédit = 1 seconde).</p>
                <Button onClick={manageSubscription} className="mt-2">Gérer mon abonnement</Button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
