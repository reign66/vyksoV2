export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import { BadgeDollarSign, CheckCircle2, MonitorPlay, ArrowLeft } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { useState } from 'react';

export default function PricingPage() {
  const [yearly, setYearly] = useState<boolean>(false);
  const [details, setDetails] = useState<null | 'premium' | 'pro' | 'max'>(null);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 flex">
      <Sidebar />
      <div className="flex-1">
        <div className="px-6 py-10 max-w-6xl">
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 text-primary-700 text-sm font-semibold">
              <BadgeDollarSign className="w-4 h-4" />
              Plans & quotas en secondes
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mt-4">Des plans clairs, pensés pour la création</h1>
            <p className="text-gray-600 mt-3 max-w-2xl mx-auto">
              1 crédit = 1 seconde. Choisissez un plan, utilisez vos secondes selon vos besoins sur SORA 2, SORA 2 PRO, VEO 3.1 Fast ou VEO 3.1 Quality.
            </p>
            <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-white border p-1">
              <button
                onClick={() => setYearly(false)}
                className={`px-4 py-1.5 text-sm rounded-full ${!yearly ? 'bg-primary-600 text-white' : 'text-gray-700'}`}
              >
                Mensuel
              </button>
              <button
                onClick={() => setYearly(true)}
                className={`px-4 py-1.5 text-sm rounded-full ${yearly ? 'bg-primary-600 text-white' : 'text-gray-700'}`}
              >
                Annuel
              </button>
            </div>
          </div>

          {!details && (
            <div className="grid md:grid-cols-3 gap-6">
              {/* Premium - Recommended SORA 2 */}
              <div className="bg-white rounded-2xl shadow-xl border-2 border-primary-500 overflow-hidden relative">
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-600 to-purple-600 text-white text-xs font-bold tracking-wide px-3 py-1 rounded-full shadow">
                  Recommandé (SORA 2)
                </span>
                <div className="p-8">
                  <h2 className="text-xl font-bold">Premium</h2>
                  <p className="text-4xl font-extrabold my-2">{yearly ? '169€' : '199€'}<span className="text-base font-semibold text-gray-500">/mois</span></p>
                  <p className="text-gray-600">10 vidéos SORA 2 OU VEO 3.1 Fast (60s)</p>
                  <div className="mt-6 space-y-2 text-sm text-gray-700">
                    <Feature>Quota mensuel: 600 secondes</Feature>
                    <Feature>10 vidéos de 60s maximum</Feature>
                    <Feature>Accès aux 4 modèles IA</Feature>
                  </div>
                  <div className="flex gap-2 mt-6">
                    <Button className="w-full">Choisir Premium</Button>
                    <Button variant="secondary" onClick={() => setDetails('premium')}>Détails</Button>
                  </div>
                </div>
              </div>

              {/* Pro */}
              <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
                <div className="p-8">
                  <h2 className="text-xl font-bold">Pro</h2>
                  <p className="text-4xl font-extrabold my-2">{yearly ? '559€' : '589€'}<span className="text-base font-semibold text-gray-500">/mois</span></p>
                  <p className="text-gray-600">18 vidéos Fast (60s) + 2 vidéos PRO/Quality (60s)</p>
                  <div className="mt-6 space-y-2 text-sm text-gray-700">
                    <Feature>Quota indicatif: 1 200 secondes</Feature>
                    <Feature>Priorité de génération</Feature>
                    <Feature>Accès aux 4 modèles IA</Feature>
                  </div>
                  <div className="flex gap-2 mt-6">
                    <Button className="w-full">Choisir Pro</Button>
                    <Button variant="secondary" onClick={() => setDetails('pro')}>Détails</Button>
                  </div>
                </div>
              </div>

              {/* MAX */}
              <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
                <div className="p-8">
                  <h2 className="text-xl font-bold">MAX</h2>
                  <p className="text-4xl font-extrabold my-2">{yearly ? '989€' : '1199€'}<span className="text-base font-semibold text-gray-500">/mois</span></p>
                  <p className="text-gray-600">20 vidéos Fast (60s) + 10 vidéos PRO/Quality (60s)</p>
                  <div className="mt-6 space-y-2 text-sm text-gray-700">
                    <Feature>Quota indicatif: 1 800 secondes</Feature>
                    <Feature>Support prioritaire</Feature>
                    <Feature>Accès aux 4 modèles IA</Feature>
                  </div>
                  <div className="flex gap-2 mt-6">
                    <Button className="w-full">Choisir MAX</Button>
                    <Button variant="secondary" onClick={() => setDetails('max')}>Détails</Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {details && (
            <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-lg border border-gray-200 p-6">
              <button className="inline-flex items-center gap-2 text-sm text-gray-700 hover:text-gray-900 mb-4" onClick={() => setDetails(null)}>
                <ArrowLeft className="w-4 h-4" /> Retour
              </button>
              {details === 'premium' && (
                <PlanDetails
                  title="Premium"
                  price={yearly ? '169€/mois (annuel)' : '199€/mois'}
                  bullets={[
                    '10 vidéos SORA 2 OU VEO 3.1 Fast (60s)',
                    '600 secondes/mois',
                    'Accès SORA 2, SORA 2 PRO, VEO 3.1 Fast/Quality',
                  ]}
                />
              )}
              {details === 'pro' && (
                <PlanDetails
                  title="Pro"
                  price={yearly ? '559€/mois (annuel)' : '589€/mois'}
                  bullets={[
                    '18 vidéos Fast (60s) + 2 vidéos PRO/Quality (60s)',
                    '≈ 1 200 secondes/mois',
                    'Priorité de génération',
                  ]}
                />
              )}
              {details === 'max' && (
                <PlanDetails
                  title="MAX"
                  price={yearly ? '989€/mois (annuel)' : '1199€/mois'}
                  bullets={[
                    '20 vidéos Fast (60s) + 10 vidéos PRO/Quality (60s)',
                    '≈ 1 800 secondes/mois',
                    'Support prioritaire',
                  ]}
                />
              )}
            </div>
          )}

          <div className="mt-12 grid md:grid-cols-2 gap-6 items-start">
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h3 className="text-xl font-bold mb-2">Comment on compte ?</h3>
              <p className="text-gray-700">
                1 crédit = 1 seconde. Une vidéo de 18s consomme 18 crédits. Les modèles n'ont pas de coût différencié, seules les secondes comptent.
              </p>
              <p className="text-gray-700 mt-2 flex items-center gap-2">
                <MonitorPlay className="w-4 h-4 text-primary-600" />
                Répartissez librement vos secondes entre les modèles (SORA 2, SORA 2 PRO, VEO 3.1 Fast/Quality).
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

function PlanDetails({ title, price, bullets }: { title: string; price: string; bullets: string[] }) {
  return (
    <div>
      <h2 className="text-2xl font-bold">{title}</h2>
      <p className="text-xl text-primary-700 font-semibold mt-1">{price}</p>
      <ul className="mt-4 space-y-2 text-gray-700 list-disc pl-5">
        {bullets.map((b) => (
          <li key={b}>{b}</li>
        ))}
      </ul>
    </div>
  );
}
