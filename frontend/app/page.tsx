import Link from 'next/link';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/Button';
import { Sparkles, Video, Zap, Shield } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      {/* Header */}
      <header className="container mx-auto px-4 py-6">
        <div className="flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost">Se connecter</Button>
            </Link>
            <Link href="/signup">
              <Button>Commencer</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-20 text-center">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-6xl font-bold mb-6 bg-gradient-to-r from-primary-600 to-primary-800 bg-clip-text text-transparent">
            G?n?rez des vid?os TikTok
            <br />
            avec l&apos;IA en quelques secondes
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Cr?ez des vid?os virales automatiquement gr?ce ? l&apos;intelligence artificielle.
            <br />
            Plus besoin de cam?ra, de montage ou de cr?ativit? - l&apos;IA s&apos;en charge.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/signup">
              <Button size="lg" className="text-lg px-8 py-6">
                Commencer gratuitement
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline" className="text-lg px-8 py-6">
                Voir une d?mo
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto px-4 py-20">
        <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          <div className="bg-white p-8 rounded-2xl shadow-lg">
            <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-primary-600" />
            </div>
            <h3 className="text-xl font-bold mb-2">IA Avanc?e</h3>
            <p className="text-gray-600">
              Utilisez les mod?les les plus puissants (Sora 2, Veo 3) pour cr?er des vid?os de qualit? professionnelle.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg">
            <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center mb-4">
              <Zap className="w-6 h-6 text-primary-600" />
            </div>
            <h3 className="text-xl font-bold mb-2">G?n?ration Rapide</h3>
            <p className="text-gray-600">
              Obtenez vos vid?os en moins d&apos;une minute. Parfait pour cr?er du contenu viral rapidement.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg">
            <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center mb-4">
              <Video className="w-6 h-6 text-primary-600" />
            </div>
            <h3 className="text-xl font-bold mb-2">Format TikTok</h3>
            <p className="text-gray-600">
              Vid?os optimis?es pour TikTok au format 9:16, pr?tes ? ?tre publi?es instantan?ment.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-20 text-center">
        <div className="max-w-3xl mx-auto bg-gradient-to-r from-primary-500 to-primary-700 rounded-3xl p-12 text-white">
          <h2 className="text-4xl font-bold mb-4">Pr?t ? cr?er votre premi?re vid?o ?</h2>
          <p className="text-xl mb-8 opacity-90">
            Rejoignez des milliers de cr?ateurs qui utilisent Vykso pour g?n?rer du contenu viral.
          </p>
          <Link href="/signup">
            <Button size="lg" variant="secondary" className="text-lg px-8 py-6">
              Commencer maintenant
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="container mx-auto px-4 py-8 border-t">
        <div className="flex items-center justify-between">
          <Logo />
          <p className="text-gray-600">? 2024 Vykso. Tous droits r?serv?s.</p>
        </div>
      </footer>
    </div>
  );
}
