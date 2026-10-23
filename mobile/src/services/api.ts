import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Alert } from 'react-native';
import { router } from 'expo-router';

// Backend URL is per-instance and comes from an env variable baked at build/
// start time (Expo inlines EXPO_PUBLIC_* vars). Set it differently for each
// instance — e.g. via the start:vim / start:martindow scripts, or a .env file:
//   EXPO_PUBLIC_API_URL=https://einv-backend-...run.app        (VIM / OGDCL)
//   EXPO_PUBLIC_API_URL=https://martin-dow-backend-...run.app  (Martin Dow)
// Falls back to the VIM backend when unset so the app still runs.
const DEFAULT_BASE_URL = 'https://einv-backend-94913592405.asia-south1.run.app';
const ENV_BASE_URL = process.env.EXPO_PUBLIC_API_URL?.trim();
const BASE_URL = ENV_BASE_URL || DEFAULT_BASE_URL;
const TIMEOUT_MS = 60_000;

const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

// Attach the stored session token to EVERY request as a Bearer header, so all
// endpoints (invoice list, detail, updates, etc.) authenticate — not just the
// few that passed ?token= manually. Key must match authService (auth_token).
apiClient.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('auth_token');
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401 the session was invalidated (most often: this account signed in on
// another device — login rotates the single session token). Sign out and send
// the user to the login screen. Guarded so parallel 401s don't stack alerts.
let handling401 = false;
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url || '';
    if (status === 401 && !url.includes('/login') && !handling401) {
      handling401 = true;
      await AsyncStorage.removeItem('auth_token');
      router.replace('/login');
      Alert.alert('Session ended', 'You were signed out because your account was signed in on another device.');
      setTimeout(() => { handling401 = false; }, 1500);
    }
    return Promise.reject(error);
  }
);

// Optional runtime override via AsyncStorage (Settings screen) — takes
// precedence over the env default when the user has set one on-device.
export async function updateBaseUrl(): Promise<void> {
  const url = await AsyncStorage.getItem('api_base_url');
  apiClient.defaults.baseURL = url || BASE_URL;
}

// Call on app start
updateBaseUrl();

export default apiClient;
