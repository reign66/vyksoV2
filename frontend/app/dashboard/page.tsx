'use client';

import { useEffect, useState } from 'react';
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Logo />
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-sm text-gray-600">Cr?dits disponibles</p>
                <p className="text-xl font-bold text-primary-600">
                  {userData?.credits ?? 0}
                </p>
              </div>
              <Button onClick={handleLogout} variant="ghost" size="sm">
                <LogOut className="w-4 h-4 mr-2" />
                D?connexion
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="bg-white border-b">
        <div className="container mx-auto px-4">
          <nav className="flex gap-4">
            <button
              onClick={() => setActiveTab('generate')}
              className={`px-6 py-4 font-medium border-b-2 transition-colors ${
                activeTab === 'generate'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              <Sparkles className="w-4 h-4 inline mr-2" />
              G?n?rer une vid?o
            </button>
            <button
              onClick={() => setActiveTab('gallery')}
              className={`px-6 py-4 font-medium border-b-2 transition-colors ${
                activeTab === 'gallery'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              <Video className="w-4 h-4 inline mr-2" />
              Mes vid?os
            </button>
            <button
              onClick={() => setActiveTab('credits')}
              className={`px-6 py-4 font-medium border-b-2 transition-colors ${
                activeTab === 'credits'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              <CreditCard className="w-4 h-4 inline mr-2" />
              Cr?dits & Plans
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
      toast.error(error.response?.data?.detail || 'Erreur lors de l\'achat de cr?dits');
    }
  };

  return (
    <div>
      <h2 className="text-3xl font-bold mb-8">Acheter des cr?dits</h2>
      <div className="grid md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-lg border-2 border-gray-200">
          <h3 className="text-xl font-bold mb-2">Petit Pack</h3>
          <p className="text-3xl font-bold text-primary-600 mb-4">30 cr?dits</p>
          <p className="text-gray-600 mb-4">? 5 vid?os de 60s</p>
          <Button
            onClick={() => handleBuyCredits(30, 10)}
            className="w-full"
          >
            10?
          </Button>
        </div>

        <div className="bg-white p-6 rounded-lg border-2 border-primary-500 relative">
          <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary-600 text-white px-4 py-1 rounded-full text-sm">
            Populaire
          </span>
          <h3 className="text-xl font-bold mb-2">Pack Moyen</h3>
          <p className="text-3xl font-bold text-primary-600 mb-4">100 cr?dits</p>
          <p className="text-gray-600 mb-4">? 16 vid?os de 60s</p>
          <Button
            onClick={() => handleBuyCredits(100, 25)}
            className="w-full"
          >
            25?
          </Button>
        </div>

        <div className="bg-white p-6 rounded-lg border-2 border-gray-200">
          <h3 className="text-xl font-bold mb-2">Gros Pack</h3>
          <p className="text-3xl font-bold text-primary-600 mb-4">250 cr?dits</p>
          <p className="text-gray-600 mb-4">? 41 vid?os de 60s</p>
          <Button
            onClick={() => handleBuyCredits(250, 50)}
            className="w-full"
          >
            50?
          </Button>
        </div>
      </div>
    </div>
  );
}
