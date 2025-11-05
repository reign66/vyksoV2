export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import { BadgeDollarSign, CheckCircle2, MonitorPlay } from 'lucide-react';

export default function PricingPage() {
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
            Choisissez un plan, utilisez vos secondes comme vous voulez. SORA 2, SORA 2 PRO, VEO 3.1 Fast ou VEO 3.1 Quality — pas de différence de "crédits" entre les modèles, seules les secondes comptent.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Starter */}
          <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
            <div className="p-8">
              <h2 className="text-xl font-bold">Starter</h2>
              <p className="text-4xl font-extrabold my-2">19€</p>
              <p className="text-gray-600">Idéal pour débuter</p>
              <div className="mt-6 space-y-2 text-sm text-gray-700">
                <Feature>Quota mensuel: 600 secondes</Feature>
                <Feature>Jusqu'à 10 vidéos de 60s</Feature>
                <Feature>Ou 2 vidéos par jour de 10s</Feature>
                <Feature>Accès aux 4 modèles IA</Feature>
              </div>
              <Button className="w-full mt-6">Choisir Starter</Button>
            </div>
          </div>

          {/* Pro */}
          <div className="bg-white rounded-2xl shadow-xl border-2 border-primary-500 overflow-hidden relative">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-600 to-purple-600 text-white text-xs font-bold tracking-wide px-3 py-1 rounded-full shadow">
              Recommandé
            </span>
            <div className="p-8">
              <h2 className="text-xl font-bold">Pro</h2>
              <p className="text-4xl font-extrabold my-2">39€</p>
              <p className="text-gray-600">Pour créateurs réguliers</p>
              <div className="mt-6 space-y-2 text-sm text-gray-700">
                <Feature>Quota mensuel: 1 200 secondes</Feature>
                <Feature>Jusqu'à 20 vidéos de 60s</Feature>
                <Feature>Ou 4 vidéos par jour de 10s</Feature>
                <Feature>Accès aux 4 modèles IA</Feature>
                <Feature>Priorité de génération</Feature>
              </div>
              <Button className="w-full mt-6">Choisir Pro</Button>
            </div>
          </div>

          {/* Premium */}
          <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
            <div className="p-8">
              <h2 className="text-xl font-bold">Premium</h2>
              <p className="text-4xl font-extrabold my-2">79€</p>
              <p className="text-gray-600">Pour équipes et pros</p>
              <div className="mt-6 space-y-2 text-sm text-gray-700">
                <Feature>Quota mensuel: 3 000 secondes</Feature>
                <Feature>Jusqu'à 50 vidéos de 60s</Feature>
                <Feature>Ou ~5 vidéos par jour de 20s</Feature>
                <Feature>Accès aux 4 modèles IA</Feature>
                <Feature>Support prioritaire</Feature>
              </div>
              <Button className="w-full mt-6">Choisir Premium</Button>
            </div>
          </div>
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
