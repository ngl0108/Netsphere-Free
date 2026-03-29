import { useEffect, useState } from 'react';
import { OpsService } from '../api/services';

export const useProductPolicyManifest = ({ enabled = true } = {}) => {
  const [manifest, setManifest] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setManifest(null);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const res = await OpsService.getPolicyManifest();
        if (cancelled) return;
        setManifest(res?.data || null);
      } catch (nextError) {
        if (cancelled) return;
        setManifest(null);
        setError(nextError);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { manifest, loading, error };
};

export default useProductPolicyManifest;
