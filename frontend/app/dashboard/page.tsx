'use client';

import { useEffect, useState } from 'react';

// Force dynamic rendering to avoid build-time Supabase initialization
export const dynamic = 'force-dynamic';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/auth';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/Button';
import { supabase } from '@/lib/supabase/client';
import { LogOut, Video, CreditCard, Sparkles, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { VideoGenerator } from '@/components/VideoGenerator';
import { VideoGallery } from '@/components/VideoGallery';
import { stripeApi } from '@/lib/api';
import toast from 'react-hot-toast';

export default function DashboardPage() {
  const router = useRouter();
  const { user, userData, loading, fetchUserData } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'generate' | 'gallery' | 'credits'>('generate');

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (user && !userData) {
      fetchUserData(user.id);
    }
  }, [user, userData, fetchUserData]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push('/');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 shadow-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Logo />
            <div className="flex items-center gap-4">
              <div className="text-right px-4 py-2 bg-gradient-to-r from-primary-50 to-purple-50 rounded-lg border border-primary-200">
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">Crédits disponibles</p>
                <p className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent">
                  {userData?.credits ?? 0}
                </p>
              </div>
              <Button onClick={handleLogout} variant="ghost" size="sm">
                <LogOut className="w-4 h-4 mr-2" />
                Déconnexion
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="bg-white/80 backdrop-blur-md border-b border-gray-200 shadow-sm">
        <div className="container mx-auto px-4">
          <nav className="flex gap-2">
            <button
              onClick={() => setActiveTab('generate')}
              className={`px-6 py-4 font-medium border-b-2 transition-all rounded-t-lg ${
                activeTab === 'generate'
                  ? 'border-primary-600 text-primary-600 bg-primary-50'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <Sparkles className="w-4 h-4 inline mr-2" />
              Générer une vidéo
            </button>
            <button
              onClick={() => setActiveTab('gallery')}
              className={`px-6 py-4 font-medium border-b-2 transition-all rounded-t-lg ${
                activeTab === 'gallery'
                  ? 'border-primary-600 text-primary-600 bg-primary-50'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <Video className="w-4 h-4 inline mr-2" />
              Mes vidéos
            </button>
            <button
              onClick={() => setActiveTab('credits')}
              className={`px-6 py-4 font-medium border-b-2 transition-all rounded-t-lg ${
                activeTab === 'credits'
                  ? 'border-primary-600 text-primary-600 bg-primary-50'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <CreditCard className="w-4 h-4 inline mr-2" />
              Crédits & Plans
            </button>
          </nav>
        </div>
      </div>

      {/* Content */}
      <main className="container mx-auto px-4 py-8">
        {activeTab === 'generate' && <VideoGenerator />}
        {activeTab === 'gallery' && <VideoGallery userId={user.id} />}
        {activeTab === 'credits' && (
          <div className="max-w-4xl mx-auto">
            <CreditsSection userId={user.id} />
          </div>
        )}
      </main>
    </div>
  );
}

function CreditsSection({ userId }: { userId: string }) {
  const { userData, fetchUserData } = useAuthStore();

  const handleBuyCredits = async (credits: number, amount: number) => {
    try {
      const data = await stripeApi.buyCredits(userId, credits, amount);
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Erreur lors de l\'achat de crédits');
    }
  };

  return (
    <div>
      <h2 className="text-3xl font-bold mb-8">Acheter des crédits</h2>
      <div className="grid md:grid-cols-3 gap-6">
        <div className="bg-white p-8 rounded-2xl shadow-lg border-2 border-gray-200 hover:shadow-xl transition-all transform hover:-translate-y-1">
          <h3 className="text-2xl font-bold mb-3 text-gray-900">Petit Pack</h3>
          <p className="text-4xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent mb-2">30 crédits</p>
          <p className="text-gray-600 mb-6">≈ 5 vidéos de 60s</p>
          <Button
            onClick={() => handleBuyCredits(30, 10)}
            className="w-full bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg"
          >
            10€
          </Button>
        </div>

        <div className="bg-gradient-to-br from-primary-50 to-purple-50 p-8 rounded-2xl shadow-xl border-2 border-primary-500 relative transform hover:-translate-y-1 transition-all">
          <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-600 to-purple-600 text-white px-5 py-1.5 rounded-full text-sm font-semibold shadow-lg">
            Populaire
          </span>
          <h3 className="text-2xl font-bold mb-3 text-gray-900 mt-2">Pack Moyen</h3>
          <p className="text-4xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent mb-2">100 crédits</p>
          <p className="text-gray-600 mb-6">≈ 16 vidéos de 60s</p>
          <Button
            onClick={() => handleBuyCredits(100, 25)}
            className="w-full bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg"
          >
            25€
          </Button>
        </div>

        <div className="bg-white p-8 rounded-2xl shadow-lg border-2 border-gray-200 hover:shadow-xl transition-all transform hover:-translate-y-1">
          <h3 className="text-2xl font-bold mb-3 text-gray-900">Gros Pack</h3>
          <p className="text-4xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent mb-2">250 crédits</p>
          <p className="text-gray-600 mb-6">≈ 41 vidéos de 60s</p>
          <Button
            onClick={() => handleBuyCredits(250, 50)}
            className="w-full bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg"
          >
            50€
          </Button>
        </div>
      </div>
    </div>
  );
}
