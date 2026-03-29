export const getSurfaceAccess = (manifest, surfaceKey) => manifest?.surfaces?.[surfaceKey] || null;

export const isSurfaceVisible = (access) => access?.visible === true;

export const isSurfaceNavigable = (access) => access?.navigable === true;

export const isSurfaceExecutable = (access) => access?.executable === true;

export const getSurfaceBlockCopy = (access, fallback = '') =>
  access?.blocked_reason || access?.upgrade_copy || fallback;

export const canSurfaceRender = (manifest, surfaceKey) =>
  isSurfaceVisible(getSurfaceAccess(manifest, surfaceKey));

export const canSurfaceNavigate = (manifest, surfaceKey) =>
  isSurfaceNavigable(getSurfaceAccess(manifest, surfaceKey));

export const getSurfacePolicyState = (
  manifest,
  surfaceKey,
  translate,
  fallbackReason = '',
) => {
  const access = getSurfaceAccess(manifest, surfaceKey);
  return {
    access,
    visible: isSurfaceVisible(access),
    navigable: isSurfaceNavigable(access),
    executable: isSurfaceExecutable(access),
    blockState: getSurfaceBlockState(access, translate, fallbackReason),
  };
};

const DEFAULT_BLOCK_METADATA = {
  preview_blocked: {
    badgeKey: 'policy_block_badge_preview',
    badgeDefault: 'Free limit',
    titleKey: 'policy_block_title_preview',
    titleDefault: 'This workflow is outside the NetSphere Free operating scope.',
    hintKey: 'policy_block_hint_preview',
    hintDefault: 'Use Free to prove discovery and visibility first, then move to Pro when active operations need to continue here.',
    actionPath: '/edition/compare',
    actionLabelKey: 'policy_block_action_compare',
    actionLabelDefault: 'Compare Free and Pro',
    actionDescKey: 'policy_block_action_compare_desc',
    actionDescDefault: 'Review the edition boundary, then return to Operations Home and continue on an allowed path.',
  },
  license_feature_required: {
    badgeKey: 'policy_block_badge_license',
    badgeDefault: 'Capability required',
    titleKey: 'policy_block_title_license',
    titleDefault: 'This workflow requires an enabled Pro capability.',
    hintKey: 'policy_block_hint_license',
    hintDefault: 'Check whether this deployment includes the required Pro capability before returning to this workflow.',
    actionPath: '/edition/compare',
    actionLabelKey: 'policy_block_action_compare',
    actionLabelDefault: 'Compare Free and Pro',
    actionDescKey: 'policy_block_action_compare_desc',
    actionDescDefault: 'Review the edition boundary, then return to Operations Home and continue on an allowed path.',
  },
  role_required: {
    badgeKey: 'policy_block_badge_role',
    badgeDefault: 'Role required',
    titleKey: 'policy_block_title_role',
    titleDefault: 'This workflow requires a higher operator role.',
    hintKey: 'policy_block_hint_role',
    hintDefault: 'Ask an administrator to grant the required role or open this workflow on your behalf.',
    actionPath: '/automation',
    actionLabelKey: 'policy_block_action_home',
    actionLabelDefault: 'Open Operations Home',
    actionDescKey: 'policy_block_action_home_desc',
    actionDescDefault: 'Return to Operations Home and continue from a workflow that matches your current role.',
  },
  preview_only: {
    badgeKey: 'policy_block_badge_free_only',
    badgeDefault: 'Free only',
    titleKey: 'policy_block_title_free_only',
    titleDefault: 'This review surface is reserved for NetSphere Free.',
    hintKey: 'policy_block_hint_free_only',
    hintDefault: 'Use this surface only from a Free collector installation when administrator review is required.',
    actionPath: '/automation',
    actionLabelKey: 'policy_block_action_home',
    actionLabelDefault: 'Open Operations Home',
    actionDescKey: 'policy_block_action_free_review_desc',
    actionDescDefault: 'Use the Free collector review path when administrator audit is required for masked handling flows.',
  },
  default: {
    badgeKey: 'policy_block_badge_default',
    badgeDefault: 'Blocked',
    titleKey: 'app_policy_blocked_title',
    titleDefault: 'Feature blocked by product policy',
    hintKey: 'app_policy_blocked_hint',
    hintDefault: 'Check license, edition, and your current role permissions for this page.',
    actionPath: '/automation',
    actionLabelKey: 'policy_block_action_home',
    actionLabelDefault: 'Open Operations Home',
    actionDescKey: 'policy_block_action_home_desc',
    actionDescDefault: 'Return to Operations Home and continue from a workflow that matches your current role.',
  },
};

export const getSurfaceBlockState = (access, translate, fallbackReason = '') => {
  const code = String(access?.blocked_code || '').trim().toLowerCase();
  const reason = getSurfaceBlockCopy(access, fallbackReason);
  const metadata = DEFAULT_BLOCK_METADATA[code] || DEFAULT_BLOCK_METADATA.default;

  return {
    code,
    badge: translate(access?.blocked_badge_key || metadata.badgeKey, metadata.badgeDefault),
    title: translate(access?.blocked_title_key || metadata.titleKey, metadata.titleDefault),
    reason: reason || translate('app_policy_blocked_default_reason', 'License or edition policy does not allow this page.'),
    hint: translate(access?.blocked_hint_key || metadata.hintKey, metadata.hintDefault),
    actionPath: access?.blocked_action_path || metadata.actionPath,
    actionLabel: translate(access?.blocked_action_label_key || metadata.actionLabelKey, metadata.actionLabelDefault),
    actionDescription: translate(access?.blocked_action_desc_key || metadata.actionDescKey, metadata.actionDescDefault),
  };
};

export const getSurfaceBlockSummary = (blockState, translate) => {
  const fallback = translate('locked_action', 'Locked');
  const reason = blockState?.reason || fallback;
  const title = blockState?.title || translate('app_policy_blocked_title', 'Feature blocked by product policy');
  const badge = blockState?.badge || fallback;
  const description = blockState?.actionDescription || blockState?.hint || '';
  return {
    badge,
    title,
    reason,
    description,
    tooltip: description ? `${badge}: ${reason} | ${description}` : `${badge}: ${reason}`,
  };
};
