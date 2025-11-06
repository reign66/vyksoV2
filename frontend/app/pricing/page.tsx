"use client";

export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useAuthStore } from '@/store/auth';
import { Button } from '@/components/ui/Button';
import { BadgeDollarSign, CheckCircle2, MonitorPlay, Sparkles } from 'lucide-react';
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
        highlights: [
          '10 vidéos — SORA 2 OU VEO 3.1 Fast',
          'Jusqu’à 60s par vidéo',
          '1 crédit = 1 seconde',
        ],
      },
      {
        key: 'pro',
        title: 'Pro',
        priceMonthly: 589,
        priceAnnual: 559,
        highlights: [
          '18 vidéos — SORA 2 OU VEO 3.1 Fast (60s)',
          '2 vidéos — SORA 2 PRO OU VEO 3.1 Quality (60s)',
          '1 crédit = 1 seconde',
        ],
      },
      {
        key: 'max',
        title: 'MAX',
        priceMonthly: 1199,
        priceAnnual: 989,
        highlights: [
          '20 vidéos — SORA 2 OU VEO 3.1 Fast (60s)',
          '10 vidéos — SORA 2 PRO OU VEO 3.1 Quality (60s)',
          '1 crédit = 1 seconde',
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
      <div className="container mx-auto px-4 py-12 max-w-6xl">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 text-primary-700 text-sm font-semibold">
            <BadgeDollarSign className="w-4 h-4" />
            Plans & quotas en secondes
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mt-4">Des plans clairs, pensés pour la création</h1>
          <p className="text-gray-600 mt-3 max-w-2xl mx-auto">
            Choisissez un plan, utilisez vos secondes comme vous voulez. SORA 2, SORA 2 PRO, VEO 3.1 Fast ou VEO 3.1 Quality — pas de différence de &quot;crédits&quot; entre les modèles, seules les secondes comptent.
          </p>
          <div className="mt-6 inline-flex items-center bg-white shadow-sm border rounded-full overflow-hidden">
            <button
              className={`px-4 py-2 text-sm font-medium ${
                billingCycle === 'monthly' ? 'bg-primary-600 text-white' : 'text-gray-700'
              }`}
              onClick={() => setBillingCycle('monthly')}
            >
              Mensuel
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium ${
                billingCycle === 'annual' ? 'bg-primary-600 text-white' : 'text-gray-700'
              }`}
              onClick={() => setBillingCycle('annual')}
            >
              Annuel <span className="ml-1 text-xs opacity-80">(économisez)</span>
            </button>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <div key={plan.key} className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
              <div className="p-8">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  {plan.title}
                  {plan.key === 'premium' && (
                    <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-primary-100 text-primary-700">SORA 2 recommandé</span>
                  )}
                </h2>
                <p className="text-4xl font-extrabold my-2">
                  {billingCycle === 'monthly' ? plan.priceMonthly : plan.priceAnnual}€
                  <span className="text-base text-gray-500 font-semibold">/mois</span>
                </p>
                <p className="text-gray-600">
                  {plan.key === 'premium' && '10 vidéos SORA 2 OU VEO 3.1 Fast'}
                  {plan.key === 'pro' && '18 Fast + 2 Pro/Quality'}
                  {plan.key === 'max' && '20 Fast + 10 Pro/Quality'}
                </p>
                <div className="mt-6 space-y-2 text-sm text-gray-700">
                  {plan.highlights.map((h) => (
                    <Feature key={h}>{h}</Feature>
                  ))}
                </div>
                <Button onClick={() => onSelect(plan.key)} className="w-full mt-6 flex items-center justify-center gap-2">
                  <Sparkles className="w-4 h-4" /> Choisir {plan.title}
                </Button>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 grid md:grid-cols-2 gap-6 items-start">
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h3 className="text-xl font-bold mb-2">Comment on compte ?</h3>
            <p className="text-gray-700">
              Seules les secondes générées sont déduites. Ex: une vidéo de 18s = 18 secondes. Si vous préférez des vidéos plus courtes, vous en ferez simplement plus. Les modèles ont le même impact sur votre quota.
            </p>
            <p className="text-gray-700 mt-2 flex items-center gap-2">
              <MonitorPlay className="w-4 h-4 text-primary-600" />
              10 vidéos de SORA 2 ou 10 vidéos de VEO 3.1 Fast maximum de 60s pour le plan Premium — à vous de répartir selon vos besoins.
            </p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h3 className="text-xl font-bold mb-2">Modèles disponibles</h3>
            <ul className="text-gray-700 list-disc pl-5">
              <li>SORA 2</li>
              <li>SORA 2 PRO</li>
              <li>VEO 3.1 Fast</li>
              <li>VEO 3.1 Quality</li>
            </ul>
            <Link href="/dashboard" className="inline-block mt-4">
              <Button variant="secondary">Générer une vidéo</Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2">
      <CheckCircle2 className="w-4 h-4 text-emerald-600" /> {children}
    </p>
  );
}
