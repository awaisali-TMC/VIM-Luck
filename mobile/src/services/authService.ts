import apiClient from './api';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ─── Types ──────────────────────────────────────────────────────
export interface InternalUser {
  id: number;
  email: string;
  display_name: string;
  role: string;
  department: string | null;
  is_active: number;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  user: InternalUser;
}

// ─── Storage Keys ───────────────────────────────────────────────
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

// ─── API Calls ──────────────────────────────────────────────────

/** Login with email + password → token + user */
export async function loginInternal(email: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/api/auth/internal/login', {
    email,
    password,
  });
  // Persist token + user
  await AsyncStorage.setItem(TOKEN_KEY, data.token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(data.user));
  await AsyncStorage.setItem('user_email', data.user.email);
  await AsyncStorage.setItem('user_name', data.user.display_name);
  return data;
}

/** Validate current token → user data */
export async function getMe(): Promise<InternalUser | null> {
  const token = await getToken();
  if (!token) return null;
  try {
    const { data } = await apiClient.get<InternalUser>('/api/auth/internal/me', {
      params: { token },
    });
    await AsyncStorage.setItem(USER_KEY, JSON.stringify(data));
    return data;
  } catch {
    // Token invalid → clear
    await clearAuth();
    return null;
  }
}

/** Logout — invalidate token on server + clear local storage */
export async function logoutInternal(): Promise<void> {
  const token = await getToken();
  if (token) {
    try {
      await apiClient.post('/api/auth/internal/logout', null, {
        params: { token },
      });
    } catch {
      // Ignore server errors on logout
    }
  }
  await clearAuth();
}

// ─── Token Helpers ──────────────────────────────────────────────

export async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem(TOKEN_KEY);
}

export async function getStoredUser(): Promise<InternalUser | null> {
  const raw = await AsyncStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await getToken();
  return !!token;
}

async function clearAuth(): Promise<void> {
  await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY, 'user_email', 'user_name']);
}
