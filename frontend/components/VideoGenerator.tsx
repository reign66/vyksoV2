'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useAuthStore } from '@/store/auth';
import { videoApi } from '@/lib/api';
import toast from 'react-hot-toast';
import { Sparkles, Loader2, MonitorPlay } from 'lucide-react';
import { ModelSelector, type AiModelKey } from '@/components/ModelSelector';

export function VideoGenerator() {
  const { user } = useAuthStore();
  const [customPrompt, setCustomPrompt] = useState('');
  const [duration, setDuration] = useState(30);
  const [aiModel, setAiModel] = useState<AiModelKey>('veo31_fast');
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    if (!user) {
      toast.error('Vous devez être connecté');
      return;
    }

    if (!customPrompt.trim()) {
      toast.error('Veuillez entrer un prompt');
      return;
    }

    setGenerating(true);

    try {
      // Map UI models to backend-supported identifiers
      const backendModel =
        aiModel === 'veo31_fast' ? 'veo3_fast' : aiModel === 'veo31_quality' ? 'veo3' : 'sora2';

      const response = await videoApi.generate({
        user_id: user.id,
        custom_prompt: customPrompt.trim(),
        duration,
        // Keep a default quality for backend compatibility, but not exposed in UI
        quality: 'basic',
        ai_model: backendModel as any,
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
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-lg p-8">
        <h2 className="text-3xl font-bold mb-6 flex items-center gap-2">
          <Sparkles className="w-8 h-8 text-primary-600" />
          Générer une nouvelle vidéo
        </h2>

        {/* Model Selector */}
        <div className="mb-8">
          <label className="block text-sm font-medium text-gray-700 mb-3">Choisissez votre modèle</label>
          <ModelSelector value={aiModel} onChange={setAiModel} />
        </div>

        {/* Custom Prompt */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Entrez votre prompt
          </label>
          <textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
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

        {/* Usage Summary (creditless messaging) */}
        <div className="mb-6 p-4 bg-gradient-to-r from-primary-50 to-purple-50 rounded-lg border border-primary-100">
          <p className="text-sm text-gray-700 flex items-start gap-2">
            <MonitorPlay className="w-4 h-4 mt-0.5 text-primary-600" />
            Avec votre plan, vous disposez d'un quota en secondes. Une vidéo de {duration}s déduira {duration} secondes. Des vidéos plus courtes permettent d'en faire davantage chaque jour.
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
