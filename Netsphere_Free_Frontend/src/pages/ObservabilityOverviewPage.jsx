/**
 * @deprecated This wrapper is no longer used.
 * The route now renders ObservabilityPage directly with mode="overview" in App.jsx.
 * This file is kept only for git history reference and can be safely deleted.
 */
import React from 'react';
import ObservabilityPage from './ObservabilityPage';

const ObservabilityOverviewPage = () => <ObservabilityPage mode="overview" />;

export default ObservabilityOverviewPage;
