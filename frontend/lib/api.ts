import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Types
export interface VideoRequest {
  user_id: string;
  niche?: string;
  duration: number;
  quality: string;
  custom_prompt?: string;
  ai_model?: 'sora2' | 'veo3_fast' | 'veo3';
}

export interface VideoResponse {
  job_id: string;
  status: string;
  estimated_time: string;
  num_clips: number;
  total_credits: number;
}

export interface VideoJob {
  id: string;
  user_id: string;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  video_url?: string;
  niche?: string;
  duration: number;
  quality: string;
  prompt?: string;
  created_at: string;
  completed_at?: string;
  error?: string;
}

export interface User {
  id: string;
  email: string;
  credits: number;
  plan: string;
  first_name?: string;
  last_name?: string;
  created_at: string;
}

// API calls
export const videoApi = {
  generate: async (data: VideoRequest) => {
    const response = await api.post<VideoResponse>('/api/videos/generate', data);
    return response.data;
  },

  getStatus: async (jobId: string) => {
    const response = await api.get<VideoJob>(`/api/videos/${jobId}/status`);
    return response.data;
  },

  getUserVideos: async (userId: string) => {
    const response = await api.get<{ total: number; videos: VideoJob[] }>(
      `/api/users/${userId}/videos`
    );
    return response.data;
  },

  download: (jobId: string) => {
    return `${API_URL}/api/videos/${jobId}/download`;
  },

  stream: (jobId: string) => {
    return `${API_URL}/api/videos/${jobId}/stream`;
  },
};

export const userApi = {
  getInfo: async (userId: string) => {
    const response = await api.get<User>(`/api/users/${userId}/info`);
    return response.data;
  },
};

export const stripeApi = {
  createCheckout: async (plan: string, userId: string) => {
    const response = await api.post<{ checkout_url: string }>(
      '/api/stripe/create-checkout',
      { plan, user_id: userId }
    );
    return response.data;
  },

  buyCredits: async (userId: string, credits: number, amount: number) => {
    const response = await api.post<{ checkout_url: string }>(
      '/api/stripe/buy-credits',
      { user_id: userId, credits, amount }
    );
    return response.data;
  },
};

export const userSyncApi = {
  sync: async (userData: {
    id: string;
    email?: string;
    user_metadata?: {
      first_name?: string;
      last_name?: string;
      full_name?: string;
    };
  }) => {
    const response = await api.post<{ success: boolean; user: any }>(
      '/api/users/sync',
      userData
    );
    return response.data;
  },
};
