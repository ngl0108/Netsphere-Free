const withGrafanaVars = (basePath, { deviceId, siteId } = {}) => {
  const params = new URLSearchParams();
  if (siteId !== undefined && siteId !== null && String(siteId).trim() !== '') {
    params.set('var-site_id', String(siteId).trim());
  }
  if (deviceId !== undefined && deviceId !== null && String(deviceId).trim() !== '') {
    params.set('var-device_id', String(deviceId).trim());
  }
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
};

export const buildObservabilityPath = ({ deviceId, siteId } = {}) => {
  const params = new URLSearchParams();
  if (siteId !== undefined && siteId !== null && String(siteId).trim() !== '') {
    params.set('siteId', String(siteId).trim());
  }
  if (deviceId !== undefined && deviceId !== null && String(deviceId).trim() !== '') {
    params.set('deviceId', String(deviceId).trim());
  }
  const query = params.toString();
  return query ? `/observability?${query}` : '/observability';
};

export const buildTopologyPath = ({
  siteId,
  cloudProvider,
  cloudAccountId,
  cloudRegion,
  cloudResourceTypes = [],
  cloudIntentImpact = false,
  focusCloudResourceId,
  focusCloudResourceName,
} = {}) => {
  const params = new URLSearchParams();
  if (siteId !== undefined && siteId !== null && String(siteId).trim() !== '') {
    params.set('siteId', String(siteId).trim());
  }
  if (cloudProvider !== undefined && cloudProvider !== null && String(cloudProvider).trim() !== '') {
    params.set('cloudProvider', String(cloudProvider).trim());
  }
  if (cloudAccountId !== undefined && cloudAccountId !== null && String(cloudAccountId).trim() !== '') {
    params.set('cloudAccountId', String(cloudAccountId).trim());
  }
  if (cloudRegion !== undefined && cloudRegion !== null && String(cloudRegion).trim() !== '') {
    params.set('cloudRegion', String(cloudRegion).trim());
  }
  const normalizedResourceTypes = Array.isArray(cloudResourceTypes)
    ? cloudResourceTypes.map((row) => String(row || '').trim()).filter(Boolean)
    : [];
  if (normalizedResourceTypes.length > 0) {
    params.set('cloudResourceTypes', normalizedResourceTypes.join(','));
  }
  if (cloudIntentImpact) {
    params.set('cloudIntentImpact', '1');
  }
  if (focusCloudResourceId !== undefined && focusCloudResourceId !== null && String(focusCloudResourceId).trim() !== '') {
    params.set('focusCloudResourceId', String(focusCloudResourceId).trim());
  }
  if (focusCloudResourceName !== undefined && focusCloudResourceName !== null && String(focusCloudResourceName).trim() !== '') {
    params.set('focusCloudResourceName', String(focusCloudResourceName).trim());
  }
  const query = params.toString();
  return query ? `/topology?${query}` : '/topology';
};

export const buildDevicePath = (deviceId) => {
  if (deviceId === undefined || deviceId === null || String(deviceId).trim() === '') {
    return '/devices';
  }
  return `/devices/${encodeURIComponent(String(deviceId).trim())}`;
};

export const buildGrafanaFleetHealthUrl = ({ deviceId, siteId } = {}) =>
  withGrafanaVars('/grafana/d/netsphere-fleet-health/net-sphere-fleet-health', { deviceId, siteId });

export const buildGrafanaAlertingCenterUrl = ({ deviceId, siteId } = {}) =>
  withGrafanaVars('/grafana/d/netsphere-alerting-center/net-sphere-alerting-center', { deviceId, siteId });

export const buildGrafanaOperationsControlPlaneUrl = ({ deviceId, siteId } = {}) =>
  withGrafanaVars('/grafana/d/netsphere-ops-control-plane/net-sphere-operations-control-plane', { deviceId, siteId });

export const buildGrafanaDiscoveryTopologyOpsUrl = ({ deviceId, siteId } = {}) =>
  withGrafanaVars('/grafana/d/netsphere-discovery-topology-ops/net-sphere-discovery-topology-ops', { deviceId, siteId });

export const buildGrafanaComplianceAutomationOpsUrl = ({ deviceId, siteId } = {}) =>
  withGrafanaVars('/grafana/d/netsphere-compliance-automation-ops/net-sphere-compliance-automation-ops', { deviceId, siteId });
