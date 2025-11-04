'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useAuthStore } from '@/store/auth';
import { videoApi } from '@/lib/api';
import toast from 'react-hot-toast';
import { Sparkles, Loader2 } from 'lucide-react';

const NICHES = [
  { id: 'recettes', label: 'Recettes de cuisine', emoji: '🍳' },
  { id: 'voyage', label: 'Voyage & Aventure', emoji: '✈️' },
  { id: 'motivation', label: 'Motivation & Lifestyle', emoji: '💪' },
  { id: 'tech', label: 'Tech & Innovation', emoji: '💻' },
];

export function VideoGenerator() {
  const { user, userData } = useAuthStore();
  const [selectedNiche, setSelectedNiche] = useState<string>('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [duration, setDuration] = useState(30);
  const [quality, setQuality] = useState<'basic' | 'pro_720p' | 'pro_1080p'>('basic');
  const [aiModel, setAiModel] = useState<'veo3_fast' | 'veo3' | 'sora2'>('veo3_fast');
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    if (!user) {
      toast.error('Vous devez être connecté');
      return;
    }

    if (!selectedNiche && !customPrompt.trim()) {
      toast.error('Veuillez sélectionner une niche ou entrer un prompt personnalisé');
      return;
    }

    // Calculate credits needed
    const numClips = Math.ceil(duration / 10);
    let requiredCredits = numClips;
    if (quality === 'pro_720p') requiredCredits = numClips * 3;
    if (quality === 'pro_1080p') requiredCredits = numClips * 5;

    if (userData && userData.credits < requiredCredits) {
      toast.error(`Crédits insuffisants. Vous avez besoin de ${requiredCredits} crédits.`);
      return;
    }

    setGenerating(true);

    try {
      const response = await videoApi.generate({
        user_id: user.id,
        niche: selectedNiche || undefined,
        custom_prompt: customPrompt.trim() || undefined,
        duration,
        quality,
        ai_model: aiModel,
      });

      toast.success(`Vidéo en cours de génération ! (${response.estimated_time})`);
      
      // Redirect to gallery after a short delay
      setTimeout(() => {
        window.location.hash = 'gallery';
      }, 2000);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Erreur lors de la génération');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-2xl shadow-lg p-8">
        <h2 className="text-3xl font-bold mb-6 flex items-center gap-2">
          <Sparkles className="w-8 h-8 text-primary-600" />
          Générer une nouvelle vidéo
        </h2>

        {/* Niche Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Choisissez une niche (ou laissez vide pour un prompt personnalisé)
          </label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {NICHES.map((niche) => (
              <button
                key={niche.id}
                onClick={() => {
                  setSelectedNiche(niche.id);
                  setCustomPrompt('');
                }}
                className={`p-4 rounded-lg border-2 transition-all ${
                  selectedNiche === niche.id
                    ? 'border-primary-600 bg-primary-50'
                    : 'border-gray-200 hover:border-primary-300'
                }`}
              >
                <div className="text-3xl mb-2">{niche.emoji}</div>
                <div className="text-sm font-medium">{niche.label}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Custom Prompt */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Ou entrez votre propre prompt
          </label>
          <textarea
            value={customPrompt}
            onChange={(e) => {
              setCustomPrompt(e.target.value);
              if (e.target.value.trim()) setSelectedNiche('');
            }}
            placeholder="Ex: Un chat qui joue du piano dans un café parisien..."
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            rows={3}
          />
        </div>

        {/* Duration */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Durée: {duration} secondes
          </label>
          <input
            type="range"
            min="10"
            max="60"
            step="10"
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>10s</span>
            <span>60s</span>
          </div>
        </div>

        {/* Quality */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Qualité
          </label>
          <div className="flex gap-4">
            <label className="flex items-center">
              <input
                type="radio"
                value="basic"
                checked={quality === 'basic'}
                onChange={(e) => setQuality(e.target.value as any)}
                className="mr-2"
              />
              Basic (1 crédit/clip)
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                value="pro_720p"
                checked={quality === 'pro_720p'}
                onChange={(e) => setQuality(e.target.value as any)}
                className="mr-2"
              />
              Pro 720p (3 crédits/clip)
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                value="pro_1080p"
                checked={quality === 'pro_1080p'}
                onChange={(e) => setQuality(e.target.value as any)}
                className="mr-2"
              />
              Pro 1080p (5 crédits/clip)
            </label>
          </div>
        </div>

        {/* AI Model */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Modèle IA
          </label>
          <select
            value={aiModel}
            onChange={(e) => setAiModel(e.target.value as any)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="veo3_fast">Veo 3 Fast (Recommandé)</option>
            <option value="veo3">Veo 3 (Haute qualité)</option>
            <option value="sora2">Sora 2</option>
          </select>
        </div>

        {/* Cost Summary */}
        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">
            Coût estimé:{' '}
            <span className="font-bold text-primary-600">
              {Math.ceil(duration / 10) * (quality === 'basic' ? 1 : quality === 'pro_720p' ? 3 : 5)} crédits
            </span>
          </p>
        </div>

        {/* Generate Button */}
        <Button
          onClick={handleGenerate}
          disabled={generating || !user}
          className="w-full"
          size="lg"
        >
          {generating ? (
            <>
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Génération en cours...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5 mr-2" />
              Générer la vidéo
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
