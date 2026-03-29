const DEFAULT_CHANGE_POLICY = {
  templateDirectMaxDevices: 3,
  fabricLiveRequiresApproval: true,
};

const toBool = (value, fallback = false) => {
  if (typeof value === "boolean") return value;
  if (value == null) return fallback;
  const normalized = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "y", "on"].includes(normalized)) return true;
  if (["false", "0", "no", "n", "off"].includes(normalized)) return false;
  return fallback;
};

const toNonNegativeInt = (value, fallback = 0) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return Math.max(0, Number(fallback) || 0);
  return Math.max(0, Math.trunc(n));
};

export const normalizeChangePolicy = (policy = {}) => ({
  templateDirectMaxDevices: toNonNegativeInt(
    policy?.templateDirectMaxDevices,
    DEFAULT_CHANGE_POLICY.templateDirectMaxDevices,
  ),
  fabricLiveRequiresApproval: toBool(
    policy?.fabricLiveRequiresApproval,
    DEFAULT_CHANGE_POLICY.fabricLiveRequiresApproval,
  ),
});

export const evaluateChangePolicy = ({ kind, targetCount, policy } = {}) => {
  const k = String(kind || "").trim().toLowerCase();
  const n = Math.max(0, Number(targetCount || 0));
  const normalizedPolicy = normalizeChangePolicy(policy);

  if (k === "fabric_deploy") {
    if (normalizedPolicy.fabricLiveRequiresApproval) {
      return {
        route: "approval",
        reason: "Fabric live deploy requires approval by current policy.",
        label: "Smart Deploy (Approval)",
      };
    }
    return {
      route: "direct",
      reason: "Fabric live deploy is allowed directly by current policy.",
      label: "Smart Deploy (Direct)",
    };
  }

  if (k === "template_deploy") {
    if (n <= normalizedPolicy.templateDirectMaxDevices) {
      return {
        route: "direct",
        reason: `Target count (${n}) is within direct threshold (${normalizedPolicy.templateDirectMaxDevices}).`,
        label: "Smart Deploy (Direct)",
      };
    }
    return {
      route: "approval",
      reason: `Target count (${n}) exceeds direct threshold (${normalizedPolicy.templateDirectMaxDevices}).`,
      label: "Smart Deploy (Approval)",
    };
  }

  return {
    route: "approval",
    reason: "Unknown change type: route to approval for safety.",
    label: "Smart Deploy (Approval)",
  };
};
