const DEFAULT_API_BASE_URL = '/api/v1';

export const getApiBaseUrl = () => {
  const fromEnv = String(import.meta.env.VITE_API_BASE_URL || '').trim();
  return fromEnv || DEFAULT_API_BASE_URL;
};

export default getApiBaseUrl;
