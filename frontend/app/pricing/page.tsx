"use client";

export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useAuthStore } from '@/store/auth';
import { Button } from '@/components/ui/Button';
import { Logo } from '@/components/Logo';
import { BadgeDollarSign, CheckCircle2, Sparkles, Video, CreditCard, Settings, Flame } from 'lucide-react';
import { stripeApi } from '@/lib/api';

export default function PricingPage() {
  const { user } = useAuthStore();
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');

  const plans = useMemo(
    () => [
      {
        key: 'premium',
        title: 'Premium',
        priceMonthly: 199,
        priceAnnual: 169,
        emoji: '💎',
        subtitle: 'Le choix parfait pour lancer tes créations IA.',
        description: 'Tu veux des vidéos dignes de SORA sans dépenser une fortune ? Le plan Premium te donne tout ce qu\'il faut pour produire du contenu impactant, rapide et cinématique.',
        idealFor: 'Idéal pour les créateurs solo, les freelances ou les marques qui veulent tester la puissance de la génération IA haute qualité.',
        features: [
          '10 vidéos / mois — SORA 2 ou VEO 3.1 Fast',
          'Jusqu\'à 60 s par vidéo',
          '1 crédit = 1 seconde générée',
          'Accès complet aux modèles SORA et VEO Fast',
          'Génération fluide, sans watermark',
          'Support prioritaire',
        ],
      },
      {
        key: 'pro',
        title: 'Pro',
        priceMonthly: 589,
        priceAnnual: 559,
        emoji: '🚀',
        subtitle: 'Le plan des créateurs exigeants.',
        description: 'Passe à la vitesse supérieure : plus de vidéos, une qualité supérieure, et l\'accès à la version SORA 2 PRO pour un rendu photoréaliste.',
        idealFor: 'Parfait pour les studios, les agences et les créateurs qui publient plusieurs projets par semaine.',
        features: [
          '20 vidéos / mois (18 Fast + 2 Pro Quality)',
          'Accès complet à SORA 2 PRO & VEO 3.1 Quality',
          'Jusqu\'à 60 s par vidéo',
          'Génération 4K rapide',
          'Accès anticipé aux nouvelles versions',
          'Priorité sur la file de rendu',
          '1 crédit = 1 seconde',
        ],
      },
      {
        key: 'max',
        title: 'MAX',
        priceMonthly: 1199,
        priceAnnual: 999,
        emoji: '🧠',
        subtitle: 'Aucune limite, juste ton imagination.',
        description: 'Le plan ultime pour dominer les réseaux et produire du contenu IA à grande échelle.',
        idealFor: 'Conçu pour les producteurs de contenu, les studios IA et les marques internationales qui veulent transformer leurs idées en images spectaculaires.',
        features: [
          '30 vidéos / mois — 20 Fast + 10 Pro Quality',
          'Accès intégral à SORA 2 PRO, VEO 3.1 Fast/Quality',
          'Rendus prioritaires en ultra-qualité (jusqu\'à 60 s)',
          'Accès aux modèles expérimentaux et nouvelles features',
          'Assistance technique dédiée (1 to 1)',
          'Génération illimitée dans le cloud haute performance',
        ],
      },
    ],
    []
  );

  const onSelect = async (planKey: string) => {
    const planId = `${planKey}_${billingCycle}`; // e.g., premium_monthly
    try {
      if (!user) {
        // redirect to login if not authenticated
        window.location.href = '/login';
        return;
      }
      const res = await stripeApi.createCheckout(planId, user.id);
      if (res.checkout_url) window.location.href = res.checkout_url;
    } catch (e) {
      // noop — toast handled globally elsewhere if needed
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 shadow-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Logo />
          <div className="text-sm text-gray-500">Pricing</div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-6">
        {/* Sidebar */}
        <aside className="bg-white rounded-2xl border border-gray-200 p-4 h-fit sticky top-20">
          <nav className="flex flex-col gap-2">
            <Link href="/dashboard?tab=generate" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700">
              <Sparkles className="w-4 h-4" /> Générer
            </Link>
            <Link href="/dashboard?tab=gallery" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700">
              <Video className="w-4 h-4" /> Mes vidéos
            </Link>
            <Link href="/dashboard?tab=credits" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700">
              <CreditCard className="w-4 h-4" /> Secondes & Plans
            </Link>
            <div className="px-4 py-3 rounded-lg flex items-center gap-2 bg-primary-50 text-primary-700">
              <BadgeDollarSign className="w-4 h-4" /> Pricing
            </div>
            <Link href="/settings" className="px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-gray-50 text-gray-700">
              <Settings className="w-4 h-4" /> Paramètres
            </Link>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="py-2">
          <div className="max-w-6xl mx-auto">
            {/* Header Section */}
            <div className="text-center mb-12">
              <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-4">
                Des plans taillés pour les créateurs visionnaires.
              </h1>
              <p className="text-lg text-gray-700 max-w-3xl mx-auto leading-relaxed">
                Crée, teste et publie des vidéos IA ultra-réalistes avec SORA 2, VEO 3.1 ou Fast Generation — sans limite de créativité, seules les secondes comptent.
              </p>
              
              {/* Billing Toggle */}
              <div className="mt-8 inline-flex items-center bg-white shadow-lg border-2 border-gray-200 rounded-full overflow-hidden">
                <button
                  className={`px-6 py-3 text-sm font-semibold transition-all ${
                    billingCycle === 'monthly' 
                      ? 'bg-primary-600 text-white shadow-md' 
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                  onClick={() => setBillingCycle('monthly')}
                >
                  Mensuel
                </button>
                <button
                  className={`px-6 py-3 text-sm font-semibold transition-all relative ${
                    billingCycle === 'annual' 
                      ? 'bg-primary-600 text-white shadow-md' 
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                  onClick={() => setBillingCycle('annual')}
                >
                  Annuel
                  <span className="ml-2 px-2 py-0.5 bg-emerald-500 text-white text-xs font-bold rounded-full">-17%</span>
                </button>
              </div>
            </div>

            {/* Plans Grid */}
            <div className="grid md:grid-cols-3 gap-6 mb-12">
              {plans.map((plan, index) => {
                const isPro = plan.key === 'pro';
                const currentPrice = billingCycle === 'monthly' ? plan.priceMonthly : plan.priceAnnual;
                const originalPrice = billingCycle === 'annual' ? plan.priceMonthly : null;
                const discount = 17; // Fixed -17% discount

                return (
                  <div
                    key={plan.key}
                    className={`bg-white rounded-2xl shadow-lg border-2 overflow-hidden relative transition-all hover:shadow-xl ${
                      isPro 
                        ? 'border-primary-500 shadow-xl scale-105 md:scale-110 z-10' 
                        : 'border-gray-200'
                    }`}
                  >
                    {/* Flame badge for Pro */}
                    {isPro && (
                      <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-20">
                        <div className="bg-gradient-to-r from-orange-500 to-red-500 text-white px-4 py-1.5 rounded-full shadow-lg flex items-center gap-1.5">
                          <Flame className="w-4 h-4 fill-current" />
                          <span className="text-xs font-bold">POPULAIRE</span>
                        </div>
                      </div>
                    )}

                    <div className="p-8">
                      <div className="mb-4">
                        <span className="text-3xl mb-2 block">{plan.emoji}</span>
                        <h2 className="text-2xl font-bold mb-1">{plan.title}</h2>
                        <p className="text-sm text-gray-600 font-medium">{plan.subtitle}</p>
                      </div>

                      {/* Price */}
                      <div className="mb-4">
                        {billingCycle === 'annual' && originalPrice && (
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xl text-gray-400 line-through font-semibold">
                              {originalPrice}€
                            </span>
                            <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-xs font-bold rounded">
                              -17%
                            </span>
                          </div>
                        )}
                        <div className="flex items-baseline gap-2">
                          <span className="text-5xl font-extrabold text-gray-900">
                            {currentPrice}€
                          </span>
                          <span className="text-base text-gray-500 font-semibold">/mois</span>
                        </div>
                        {billingCycle === 'annual' && (
                          <p className="text-xs text-gray-500 mt-1">
                            Facturé annuellement
                          </p>
                        )}
                      </div>

                      <p className="text-sm text-gray-700 mb-6 leading-relaxed">
                        {plan.description}
                      </p>

                      {/* Features */}
                      <div className="space-y-3 mb-6">
                        {plan.features.map((feature, idx) => (
                          <Feature key={idx}>{feature}</Feature>
                        ))}
                      </div>

                      <p className="text-xs text-gray-600 italic mb-6 leading-relaxed">
                        💡 {plan.idealFor}
                      </p>

                      <Button 
                        onClick={() => onSelect(plan.key)} 
                        className={`w-full flex items-center justify-center gap-2 ${
                          isPro 
                            ? 'bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg' 
                            : ''
                        }`}
                      >
                        <Sparkles className="w-4 h-4" /> Choisir {plan.title}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer Section */}
            <div className="bg-white rounded-2xl border border-gray-200 p-8 text-center">
              <h3 className="text-2xl font-bold mb-4">⚙️ Accroche finale</h3>
              <div className="space-y-3 text-gray-700 max-w-3xl mx-auto">
                <p className="text-lg">
                  Peu importe ton plan, tu profites de la même puissance d'IA — seules les secondes comptent.
                </p>
                <p>
                  Chaque plan inclut la compatibilité avec SORA 2, SORA 2 PRO, VEO 3.1 Fast et VEO 3.1 Quality.
                </p>
                <p className="font-semibold text-primary-700">
                  Choisis la vitesse, la qualité et la liberté qui te ressemblent.
                </p>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-sm text-gray-700">
      <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" /> 
      <span>{children}</span>
    </p>
  );
}
