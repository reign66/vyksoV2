"use client";

import Image from 'next/image';
import { useState } from 'react';

export type AiModelKey = 'sora2' | 'sora2_pro' | 'veo31_fast' | 'veo31_quality';

export const MODEL_CARDS: Array<{
  key: AiModelKey;
  title: string;
  subtitle: string;
  image: string;
  recommended?: boolean;
}> = [
  {
    key: 'sora2',
    title: 'SORA 2',
    subtitle: 'Creative, general purpose',
    image: '/models/sora2.svg',
    recommended: true,
  },
  {
    key: 'sora2_pro',
    title: 'SORA 2 PRO',
    subtitle: 'Premium control & consistency',
    image: '/models/sora2_pro.svg',
  },
  {
    key: 'veo31_fast',
    title: 'VEO 3.1 Fast',
    subtitle: 'Speed-first iteration',
    image: '/models/veo31_fast.svg',
  },
  {
    key: 'veo31_quality',
    title: 'VEO 3.1 Quality',
    subtitle: 'High fidelity results',
    image: '/models/veo31_quality.svg',
  },
];

export function ModelSelector({
  value,
  onChange,
}: {
  value: AiModelKey;
  onChange: (v: AiModelKey) => void;
}) {
  const [hovered, setHovered] = useState<AiModelKey | null>(null);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
      {MODEL_CARDS.map((m) => {
        const isActive = value === m.key;
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            onMouseEnter={() => setHovered(m.key)}
            onMouseLeave={() => setHovered(null)}
            className={`group relative rounded-2xl overflow-hidden border transition-all text-left ${
              isActive
                ? 'border-primary-500 ring-2 ring-primary-200 shadow-xl'
                : 'border-gray-200 hover:border-primary-300 hover:shadow-lg'
            }`}
          >
            <div className="aspect-[16/9] w-full bg-gray-100">
              <Image
                src={m.image}
                alt={m.title}
                width={800}
                height={450}
                className="w-full h-full object-cover"
                priority={m.recommended}
              />
            </div>
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500">Model</p>
                  <p className="text-lg font-semibold text-gray-900">{m.title}</p>
                </div>
                {m.recommended && (
                  <span className="text-xs font-semibold px-2 py-1 rounded-full bg-primary-100 text-primary-700">
                    Recommandé
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 mt-1">{m.subtitle}</p>
            </div>
            <div
              className={`absolute inset-0 bg-black/5 transition-opacity pointer-events-none ${
                hovered === m.key ? 'opacity-100' : 'opacity-0'
              }`}
            />
          </button>
        );
      })}
    </div>
  );
}
