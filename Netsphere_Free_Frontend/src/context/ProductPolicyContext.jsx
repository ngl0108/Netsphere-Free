import React, { createContext, useContext } from 'react';

import useProductPolicyManifest from '../hooks/useProductPolicyManifest';

const ProductPolicyContext = createContext({
  manifest: null,
  loading: false,
  error: null,
});

export const ProductPolicyProvider = ({ enabled = true, children }) => {
  const value = useProductPolicyManifest({ enabled });
  return <ProductPolicyContext.Provider value={value}>{children}</ProductPolicyContext.Provider>;
};

export const useProductPolicy = () => useContext(ProductPolicyContext);

export default ProductPolicyContext;
