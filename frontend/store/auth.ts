import { create } from 'zustand';
import { User } from '@supabase/supabase-js';
import { User as ApiUser } from '@/lib/api';
import { userApi } from '@/lib/api';

interface AuthState {
  user: User | null;
  userData: ApiUser | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setUserData: (userData: ApiUser | null) => void;
  setLoading: (loading: boolean) => void;
  fetchUserData: (userId: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  userData: null,
  loading: true,
  setUser: (user) => set({ user }),
  setUserData: (userData) => set({ userData }),
  setLoading: (loading) => set({ loading }),
  fetchUserData: async (userId: string) => {
    try {
      const data = await userApi.getInfo(userId);
      set({ userData: data });
    } catch (error) {
      console.error('Error fetching user data:', error);
    }
  },
}));
