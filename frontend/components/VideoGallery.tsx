'use client';

import { useEffect, useState } from 'react';
import { videoApi, VideoJob } from '@/lib/api';
import { Video, Download, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';

export function VideoGallery({ userId }: { userId: string }) {
  const [videos, setVideos] = useState<VideoJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState<Set<string>>(new Set());

  const loadVideos = async () => {
    try {
      const data = await videoApi.getUserVideos(userId);
      setVideos(data.videos);
      
      // Start polling for pending/generating videos
      const pendingIds = data.videos
        .filter((v) => v.status === 'pending' || v.status === 'generating')
        .map((v) => v.id);
      setPolling((prev) => {
        const next = new Set(prev);
        pendingIds.forEach((id) => next.add(id));
        return next;
      });
    } catch (error) {
      toast.error('Erreur lors du chargement des vid?os');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVideos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    // Poll for pending/generating videos
    const interval = setInterval(() => {
      polling.forEach((jobId) => {
        videoApi.getStatus(jobId).then((job) => {
          if (job.status === 'completed' || job.status === 'failed') {
            setPolling((prev) => {
              const next = new Set(prev);
              next.delete(jobId);
              return next;
            });
            loadVideos(); // Refresh list
          }
        });
      });
    }, 3000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polling]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-600" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-600" />;
      case 'generating':
      case 'pending':
        return <Loader2 className="w-5 h-5 text-primary-600 animate-spin" />;
      default:
        return null;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed':
        return 'Termin?e';
      case 'failed':
        return '?chou?e';
      case 'generating':
        return 'G?n?ration en cours...';
      case 'pending':
        return 'En attente...';
      default:
        return status;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div className="text-center py-12">
        <Video className="w-16 h-16 text-gray-400 mx-auto mb-4" />
        <h3 className="text-xl font-medium text-gray-900 mb-2">
          Aucune vid?o g?n?r?e
        </h3>
        <p className="text-gray-600">
          G?n?rez votre premi?re vid?o pour commencer !
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Mes vid?os</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {videos.map((video) => (
          <div
            key={video.id}
            className="bg-white rounded-lg shadow-lg overflow-hidden"
          >
            {video.video_url && video.status === 'completed' ? (
              <video
                src={videoApi.stream(video.id)}
                controls
                className="w-full h-64 object-cover"
              />
            ) : (
              <div className="w-full h-64 bg-gray-100 flex items-center justify-center">
                {getStatusIcon(video.status)}
              </div>
            )}

            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900">
                  {video.niche || 'Personnalis?'}
                </span>
                <span className="text-sm text-gray-600 flex items-center gap-1">
                  {getStatusIcon(video.status)}
                  {getStatusText(video.status)}
                </span>
              </div>

              <p className="text-xs text-gray-500 mb-3">
                {video.duration}s ? {video.quality} ? {new Date(video.created_at).toLocaleDateString('fr-FR')}
              </p>

              {video.status === 'completed' && video.video_url && (
                <a
                  href={videoApi.download(video.id)}
                  download
                  className="inline-flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700"
                >
                  <Download className="w-4 h-4" />
                  T?l?charger
                </a>
              )}

              {video.error && (
                <p className="text-xs text-red-600 mt-2">{video.error}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
