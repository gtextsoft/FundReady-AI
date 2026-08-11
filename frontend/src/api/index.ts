import { httpApi } from './http';
import type { FundReadyApi } from './contract';

/**
 * Single seam between the app and the backend.
 *
 * Points at the real service, configured by `EXPO_PUBLIC_API_URL`. There is no
 * mock: the app shows live data or says the feature is not built yet.
 */
export const api: FundReadyApi = httpApi;

export * from './contract';
