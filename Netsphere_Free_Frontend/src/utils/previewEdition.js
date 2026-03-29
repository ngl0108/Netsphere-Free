const normalizePath = (raw) => {
  let path = String(raw || '').trim();
  if (!path) return '/';
  if (!path.startsWith('/')) path = `/${path}`;
  if (path.length > 1) path = path.replace(/\/+$/, '');
  return path || '/';
};

const matchesPrefix = (path, prefix) => {
  const normalizedPath = normalizePath(path);
  const normalizedPrefix = normalizePath(prefix);
  if (normalizedPrefix === '/') return normalizedPath === '/';
  return normalizedPath === normalizedPrefix || normalizedPath.startsWith(`${normalizedPrefix}/`);
};

export const isPreviewPathAllowed = (path, policy = {}) => {
  if (policy?.preview_enabled !== true) return true;
  const normalizedPath = normalizePath(path);
  const exactPaths = Array.isArray(policy?.allowed_nav_exact_paths) ? policy.allowed_nav_exact_paths : [];
  const prefixPaths = Array.isArray(policy?.allowed_nav_prefixes) ? policy.allowed_nav_prefixes : [];
  const normalizedExact = new Set(exactPaths.map(normalizePath));
  if (normalizedExact.has(normalizedPath)) return true;
  return prefixPaths.some((prefix) => matchesPrefix(normalizedPath, prefix));
};

export const isPreviewOnlyPath = (path) => matchesPrefix(path, '/preview');

export const normalizePreviewPath = normalizePath;
