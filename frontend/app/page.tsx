export const dynamic = 'force-dynamic';
import Link from 'next/link';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/Button';
import { Sparkles, Video, Zap, Shield, ArrowRight, Star, TrendingUp } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50">
      {/* Header */}
      <header className="container mx-auto px-4 py-6 sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100">
        <div className="flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost" className="hover:bg-gray-100">Se connecter</Button>
            </Link>
            <Link href="/signup">
              <Button className="bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-lg shadow-primary-500/50">
                Commencer <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-20 text-center relative overflow-hidden">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-10 w-72 h-72 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-blob"></div>
          <div className="absolute top-40 right-10 w-72 h-72 bg-purple-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-blob animation-delay-2000"></div>
          <div className="absolute -bottom-8 left-1/2 w-72 h-72 bg-pink-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-blob animation-delay-4000"></div>
        </div>
        
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary-100 text-primary-700 rounded-full text-sm font-medium mb-6">
            <Star className="w-4 h-4 fill-primary-600" />
            Plus de 10,000 vidéos générées cette semaine
          </div>
          <h1 className="text-6xl md:text-7xl font-extrabold mb-6 bg-gradient-to-r from-primary-600 via-purple-600 to-primary-800 bg-clip-text text-transparent leading-tight">
            Générez des vidéos TikTok
            <br />
            avec l&apos;IA en quelques secondes
          </h1>
          <p className="text-xl md:text-2xl text-gray-700 mb-10 max-w-3xl mx-auto leading-relaxed">
            Créez des vidéos virales automatiquement grâce à l&apos;intelligence artificielle.
            <br />
            Plus besoin de caméra, de montage ou de créativité - l&apos;IA s&apos;en charge.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link href="/signup">
              <Button size="lg" className="text-lg px-8 py-6 bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800 shadow-xl shadow-primary-500/50 hover:shadow-2xl hover:shadow-primary-500/50 transition-all transform hover:scale-105">
                Commencer gratuitement <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline" className="text-lg px-8 py-6 border-2 hover:bg-gray-50 transition-all">
                Voir une démo
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto px-4 py-20">
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4 bg-gradient-to-r from-primary-600 to-purple-600 bg-clip-text text-transparent">
            Pourquoi choisir Vykso ?
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Une plateforme complète pour créer du contenu viral avec l&apos;IA
          </p>
        </div>
        <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:-translate-y-2 border border-gray-100">
            <div className="w-14 h-14 bg-gradient-to-br from-primary-500 to-primary-600 rounded-xl flex items-center justify-center mb-6 shadow-lg shadow-primary-500/30">
              <Sparkles className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900">IA Avancée</h3>
            <p className="text-gray-600 leading-relaxed">
              Utilisez les modèles les plus puissants (Sora 2, Veo 3) pour créer des vidéos de qualité professionnelle.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:-translate-y-2 border border-gray-100">
            <div className="w-14 h-14 bg-gradient-to-br from-yellow-500 to-orange-500 rounded-xl flex items-center justify-center mb-6 shadow-lg shadow-yellow-500/30">
              <Zap className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900">Génération Rapide</h3>
            <p className="text-gray-600 leading-relaxed">
              Obtenez vos vidéos en moins d&apos;une minute. Parfait pour créer du contenu viral rapidement.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:-translate-y-2 border border-gray-100">
            <div className="w-14 h-14 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center mb-6 shadow-lg shadow-purple-500/30">
              <Video className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900">Format TikTok</h3>
            <p className="text-gray-600 leading-relaxed">
              Vidéos optimisées pour TikTok au format 9:16, prêtes à être publiées instantanément.
            </p>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="container mx-auto px-4 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 max-w-5xl mx-auto">
          <div className="text-center">
            <div className="text-4xl md:text-5xl font-bold text-primary-600 mb-2">10K+</div>
            <div className="text-gray-600">Vidéos générées</div>
          </div>
          <div className="text-center">
            <div className="text-4xl md:text-5xl font-bold text-primary-600 mb-2">5K+</div>
            <div className="text-gray-600">Créateurs actifs</div>
          </div>
          <div className="text-center">
            <div className="text-4xl md:text-5xl font-bold text-primary-600 mb-2">99%</div>
            <div className="text-gray-600">Satisfaction</div>
          </div>
          <div className="text-center">
            <div className="text-4xl md:text-5xl font-bold text-primary-600 mb-2">&lt;1min</div>
            <div className="text-gray-600">Temps moyen</div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-20 text-center">
        <div className="max-w-4xl mx-auto bg-gradient-to-r from-primary-600 via-purple-600 to-primary-700 rounded-3xl p-12 md:p-16 text-white relative overflow-hidden">
          <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-10"></div>
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-bold mb-6">Prêt à créer votre première vidéo ?</h2>
            <p className="text-xl md:text-2xl mb-10 opacity-95 max-w-2xl mx-auto leading-relaxed">
              Rejoignez des milliers de créateurs qui utilisent Vykso pour générer du contenu viral.
            </p>
            <Link href="/signup">
              <Button size="lg" variant="secondary" className="text-lg px-10 py-6 bg-white text-primary-600 hover:bg-gray-100 shadow-xl hover:shadow-2xl transition-all transform hover:scale-105">
                Commencer maintenant <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="container mx-auto px-4 py-8 border-t">
        <div className="flex items-center justify-between">
          <Logo />
          <p className="text-gray-600">© 2024 Vykso. Tous droits réservés.</p>
        </div>
      </footer>
    </div>
  );
}
