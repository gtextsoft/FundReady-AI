import { mockApi } from './mock';
import type { FundMeApi } from './contract';

/**
 * Single seam between the app and the backend.
 *
 * Today it resolves to the in-memory mock. When the service is live, add
 * `http.ts` implementing `FundMeApi` against EXPO_PUBLIC_API_URL and swap the
 * export below — every screen already talks to this object only.
 */
export const api: FundMeApi = mockApi;

export * from './contract';
