import React from 'react';
import { Link } from 'react-router-dom';

import { t } from '../../i18n';

const ProductPolicyBlockCard = ({
  blockState,
  fullPage = false,
  compact = false,
  className = '',
}) => {
  const actionPath = blockState?.actionPath || '/automation';
  const actionLabel = blockState?.actionLabel || t('policy_block_action_home', 'Open Operations Home');

  const card = (
    <div
      className={`rounded-2xl border border-amber-200 bg-amber-50/80 dark:bg-amber-950/20 dark:border-amber-900 ${
        compact ? 'px-4 py-4' : 'px-6 py-8'
      } ${className}`.trim()}
    >
      {blockState?.badge ? (
        <div className="inline-flex items-center rounded-full border border-amber-300 dark:border-amber-800/70 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.18em] text-amber-800 dark:text-amber-200">
          {blockState.badge}
        </div>
      ) : null}
      <h2 className={`${compact ? 'mt-2 text-lg' : 'mt-3 text-xl'} font-bold text-amber-900 dark:text-amber-200`}>
        {blockState?.title || t('app_policy_blocked_title', 'Feature blocked by product policy')}
      </h2>
      <p className="mt-3 text-sm text-amber-800 dark:text-amber-300">
        {blockState?.reason || t('app_policy_blocked_default_reason', 'License or edition policy does not allow this page.')}
      </p>
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
        {blockState?.hint || t('app_policy_blocked_hint', 'Check license, edition, and your current role permissions for this page.')}
      </p>
      {blockState?.actionDescription ? (
        <div className="mt-4 rounded-xl border border-amber-200/80 dark:border-amber-900/50 bg-white/70 dark:bg-black/10 px-4 py-3">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-amber-800 dark:text-amber-200">
            {t('policy_block_next_step', 'Recommended next step')}
          </div>
          <div className="mt-1 text-xs text-amber-800 dark:text-amber-300">
            {blockState.actionDescription}
          </div>
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap gap-2">
        <Link
          to={actionPath}
          className="inline-flex px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold"
        >
          {actionLabel}
        </Link>
        {actionPath !== '/automation' ? (
          <Link
            to="/automation"
            className="inline-flex px-4 py-2 rounded-xl border border-amber-300 dark:border-amber-800/70 text-amber-900 dark:text-amber-200 text-sm font-bold hover:bg-amber-100/70 dark:hover:bg-amber-900/20"
          >
            {t('policy_block_action_home', 'Open Operations Home')}
          </Link>
        ) : null}
      </div>
    </div>
  );

  if (!fullPage) {
    return card;
  }

  return (
    <div
      data-testid="policy-blocked-page"
      className="h-full w-full min-h-[calc(100dvh-9rem)] bg-[#f4f5f9] dark:bg-[#0e1012] p-6 flex items-center justify-center"
    >
      <div className="max-w-xl w-full">
        {card}
      </div>
    </div>
  );
};

export default ProductPolicyBlockCard;
