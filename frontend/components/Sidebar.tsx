"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BadgeDollarSign, Home, Settings, Sparkles } from 'lucide-react';
import { Logo } from './Logo';

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { href: '/dashboard', label: 'Tableau de bord', icon: <Home className="w-4 h-4" /> },
    { href: '/pricing', label: 'Plans & Tarifs', icon: <BadgeDollarSign className="w-4 h-4" /> },
    { href: '/settings', label: 'Paramètres', icon: <Settings className="w-4 h-4" /> },
  ];

  return (
    <aside className="h-screen sticky top-0 w-64 bg-white/90 backdrop-blur border-r border-gray-200 flex flex-col">
      <div className="px-4 py-4 border-b border-gray-100">
        <Link href="/" aria-label="Accueil">
          <Logo />
        </Link>
      </div>
      <nav className="p-3 space-y-1">
        {links.map((l) => {
          const active = pathname === l.href || (l.href !== '/' && pathname.startsWith(l.href));
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? 'bg-primary-50 text-primary-700 border border-primary-200'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              {l.icon}
              <span>{l.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto p-3 text-xs text-gray-500">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5" />
          <span>1 crédit = 1 seconde</span>
        </div>
      </div>
    </aside>
  );
}
