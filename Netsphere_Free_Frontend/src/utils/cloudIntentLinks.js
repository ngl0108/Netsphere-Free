const CLOUD_INTENT_PROVIDERS = new Set(['aws', 'azure', 'gcp', 'ncp']);

const normalizeText = (value) => String(value || '').trim();

const normalizeProvider = (value) => {
  const normalized = normalizeText(value).toLowerCase();
  return CLOUD_INTENT_PROVIDERS.has(normalized) ? normalized : '';
};

const uniqueValues = (items = []) => {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const normalized = normalizeText(item).toLowerCase().replace(/[\s-]+/g, '_');
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
};

const slugify = (value) =>
  normalizeText(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const buildIntentName = ({ provider, resourceName, resourceType, region } = {}) => {
  const parts = [
    normalizeProvider(provider),
    slugify(resourceName),
    slugify(region),
    slugify(resourceType),
    'guardrail',
  ].filter(Boolean);
  return parts.length > 0 ? parts.join('-') : 'cloud-guardrail-baseline';
};

export const buildCloudIntentPath = ({
  provider,
  accountId,
  region,
  resourceType,
  resourceTypes = [],
  resourceName,
  resourceId,
  routeRefs = [],
  securityRefs = [],
  source = 'topology',
} = {}) => {
  const params = new URLSearchParams();
  const normalizedProvider = normalizeProvider(provider);
  if (normalizedProvider) params.set('provider', normalizedProvider);

  const normalizedAccountId = normalizeText(accountId);
  if (normalizedAccountId) params.set('accountId', normalizedAccountId);

  const normalizedRegion = normalizeText(region);
  if (normalizedRegion) params.set('region', normalizedRegion);

  const normalizedResourceTypes = uniqueValues([
    resourceType,
    ...resourceTypes,
    ...routeRefs.map((row) => row?.resource_type || row?.resource_type_label),
    ...securityRefs.map((row) => row?.resource_type || row?.resource_type_label),
  ]);
  if (normalizedResourceTypes.length > 0) {
    params.set('resourceTypes', normalizedResourceTypes.join(','));
    params.set('resourceType', normalizedResourceTypes[0]);
  }

  const normalizedResourceName = normalizeText(resourceName);
  if (normalizedResourceName) params.set('resourceName', normalizedResourceName);

  const normalizedResourceId = normalizeText(resourceId);
  if (normalizedResourceId) params.set('resourceId', normalizedResourceId);

  params.set('source', normalizeText(source) || 'topology');
  params.set(
    'intentName',
    buildIntentName({
      provider: normalizedProvider,
      resourceName: normalizedResourceName,
      resourceType: normalizedResourceTypes[0] || resourceType,
      region: normalizedRegion,
    }),
  );

  const query = params.toString();
  return query ? `/cloud/intents?${query}` : '/cloud/intents';
};

export const parseCloudIntentPrefill = (search = '') => {
  const params = new URLSearchParams(search || '');
  const provider = normalizeProvider(params.get('provider'));
  const accountId = normalizeText(params.get('accountId'));
  const region = normalizeText(params.get('region'));
  const resourceName = normalizeText(params.get('resourceName'));
  const resourceId = normalizeText(params.get('resourceId'));
  const intentName = normalizeText(params.get('intentName'));
  const source = normalizeText(params.get('source'));
  const resourceTypes = uniqueValues([
    ...normalizeText(params.get('resourceTypes')).split(','),
    params.get('resourceType'),
  ]);

  const hasPrefill = Boolean(
    provider || accountId || region || resourceTypes.length > 0 || resourceName || resourceId || intentName || source,
  );

  return {
    hasPrefill,
    provider,
    accountId,
    region,
    resourceName,
    resourceId,
    intentName,
    resourceTypes,
    source,
  };
};
