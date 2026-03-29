import React, { useEffect, useMemo, useState } from 'react';
import { Layers, Server, ArrowRight, CheckCircle, Code, RefreshCw, Box, Play, ShieldCheck } from 'lucide-react';
import { ApprovalService, SDNService, DeviceService, SettingsService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import { evaluateChangePolicy } from '../../utils/changePolicy';
import { t } from '../../i18n';
import { InlineEmpty, SectionCard } from '../common/PageState';

const StepBadge = ({ active, done, label }) => (
  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${done || active ? 'bg-pink-600 text-white' : 'bg-gray-200 dark:bg-gray-800 text-gray-500'}`}>
    {label}
  </div>
);

const parseBoolSetting = (value, fallback = false) => {
  if (typeof value === 'boolean') return value;
  if (value == null) return fallback;
  const t = String(value).trim().toLowerCase();
  if (['true', '1', 'yes', 'y', 'on'].includes(t)) return true;
  if (['false', '0', 'no', 'n', 'off'].includes(t)) return false;
  return fallback;
};

const parseNonNegativeIntSetting = (value, fallback = 0) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return Math.max(0, Number(fallback) || 0);
  return Math.max(0, Math.trunc(n));
};

const extractChangePolicyFromSettings = (raw = {}) => ({
  templateDirectMaxDevices: parseNonNegativeIntSetting(raw?.change_policy_template_direct_max_devices, 3),
  fabricLiveRequiresApproval: parseBoolSetting(raw?.change_policy_fabric_live_requires_approval, true),
});

const FabricPage = () => {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [devices, setDevices] = useState([]);
  const [spines, setSpines] = useState([]);
  const [leafs, setLeafs] = useState([]);
  const [generatedConfigs, setGeneratedConfigs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [deployLoading, setDeployLoading] = useState(false);
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const [deploySummary, setDeploySummary] = useState(null);
  const [deployResults, setDeployResults] = useState([]);
  const [changePolicy, setChangePolicy] = useState(() => ({
    templateDirectMaxDevices: 3,
    fabricLiveRequiresApproval: true,
  }));

  const [asn, setAsn] = useState(65000);
  const [vniBase, setVniBase] = useState(10000);

  useEffect(() => {
    fetchDevices();
  }, []);

  const fetchDevices = async () => {
    try {
      const [res, settingsRes] = await Promise.all([
        DeviceService.getDevices(),
        SettingsService.getGeneral().catch(() => ({ data: {} })),
      ]);
      setDevices(Array.isArray(res?.data) ? res.data : []);
      setChangePolicy(extractChangePolicyFromSettings(settingsRes?.data || {}));
    } catch (e) {
      console.error(e);
      setDevices([]);
    }
  };

  const toggleSelection = (id, type) => {
    if (type === 'spine') {
      setSpines((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
      setLeafs((prev) => prev.filter((x) => x !== id));
      return;
    }
    setLeafs((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    setSpines((prev) => prev.filter((x) => x !== id));
  };

  const handleGenerate = async () => {
    setLoading(true);
    setDeploySummary(null);
    setDeployResults([]);
    try {
      const res = await SDNService.generateFabric({
        spine_ids: spines,
        leaf_ids: leafs,
        asn,
        vni_base: vniBase,
      });
      setGeneratedConfigs(res.data || {});
      setStep(3);
    } catch (e) {
      toast.error(`${t('fabric_generation_failed', 'Generation failed')}: ${e?.response?.data?.detail || e?.message}`);
    } finally {
      setLoading(false);
    }
  };

  const runFabric = async (dryRun) => {
    setDeployLoading(true);
    try {
      const res = await SDNService.deployFabric({
        spine_ids: spines,
        leaf_ids: leafs,
        asn,
        vni_base: vniBase,
        dry_run: !!dryRun,
        rollback_on_error: true,
        verify_commands: ['show bgp summary', 'show lldp neighbors'],
      });
      const payload = res?.data || {};
      setDeploySummary(payload.summary || null);
      setDeployResults(Array.isArray(payload.results) ? payload.results : []);
      if (dryRun) {
        toast.success(t('fabric_dry_run_completed', 'Dry-run validation completed.'));
      } else if ((payload.summary?.failed || 0) > 0) {
        toast.warning(
          t('fabric_deploy_completed_with_failures_fmt', 'Deploy completed with failures: {count}')
            .replace('{count}', String(payload.summary.failed)),
        );
      } else {
        toast.success(t('fabric_deploy_completed', 'Fabric deploy completed successfully.'));
      }
    } catch (e) {
      toast.error(`${t('fabric_execution_failed', 'Fabric execution failed')}: ${e?.response?.data?.detail || e?.message}`);
    } finally {
      setDeployLoading(false);
    }
  };

  const handleRequestDeployApproval = async () => {
    if (spines.length === 0 || leafs.length === 0) {
      toast.warning(t('fabric_select_spine_leaf_required', 'Select at least one spine and one leaf.'));
      return;
    }

    setApprovalSubmitting(true);
    try {
      const devById = new Map((devices || []).map((d) => [Number(d.id), d]));
      const spineNames = spines
        .map((id) => devById.get(Number(id))?.name || `spine-${id}`)
        .slice(0, 4)
        .join(', ');
      const leafNames = leafs
        .map((id) => devById.get(Number(id))?.name || `leaf-${id}`)
        .slice(0, 4)
        .join(', ');
      await ApprovalService.create({
        title: `[Fabric] VXLAN EVPN deploy (${spines.length + leafs.length} nodes)`,
        description: [
          'Fabric deployment approval request',
          `ASN: ${asn}, VNI Base: ${vniBase}`,
          `Spines: ${spineNames}${spines.length > 4 ? ' ...' : ''}`,
          `Leafs: ${leafNames}${leafs.length > 4 ? ' ...' : ''}`,
        ].join('\n'),
        request_type: 'fabric_deploy',
        payload: {
          spine_ids: spines.map((id) => Number(id)),
          leaf_ids: leafs.map((id) => Number(id)),
          asn: Number(asn),
          vni_base: Number(vniBase),
          dry_run: false,
          pre_check_commands: [],
          verify_commands: ['show bgp summary', 'show nve peers'],
          rollback_on_error: true,
          canary_count: 0,
          wave_size: 0,
          stop_on_wave_failure: true,
          inter_wave_delay_seconds: 0.0,
        },
      });
      toast.success(t('fabric_approval_submitted', 'Approval request submitted.'));
    } catch (e) {
      toast.error(`${t('fabric_approval_failed', 'Approval request failed')}: ${e?.response?.data?.detail || e?.message}`);
    } finally {
      setApprovalSubmitting(false);
    }
  };

  const canProceed = spines.length > 0 && leafs.length > 0;
  const fabricTargetCount = spines.length + leafs.length;
  const fabricDeployPolicy = useMemo(
    () => evaluateChangePolicy({
      kind: "fabric_deploy",
      targetCount: fabricTargetCount,
      policy: changePolicy,
    }),
    [fabricTargetCount, changePolicy],
  );
  const fabricSmartIsApproval = fabricDeployPolicy.route === "approval";
  const fabricSmartSubmitting = fabricSmartIsApproval ? approvalSubmitting : deployLoading;
  const runSmartFabricDeploy = async () => {
    if (fabricSmartIsApproval) {
      await handleRequestDeployApproval();
      return;
    }
    await runFabric(false);
  };
  const sortedConfigs = useMemo(() => Object.entries(generatedConfigs || {}), [generatedConfigs]);

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full min-h-0 text-gray-900 dark:text-white animate-fade-in flex flex-col">
      <div className="flex flex-col gap-3 lg:flex-row lg:justify-between lg:items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="text-pink-500" /> Fabric Automation: VXLAN EVPN
          </h1>
          <p className="text-sm text-gray-500">Design, validate, deploy and rollback from one flow.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <StepBadge label="1" active={step === 1} done={step > 1} />
          <StepBadge label="2" active={step === 2} done={step > 2} />
          <StepBadge label="3" active={step === 3} done={false} />
        </div>
      </div>

      <SectionCard className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {step === 1 && (
          <div className="p-6 flex-1 flex flex-col">
            <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Box size={20} className="text-pink-400" /> Assign Roles
            </h2>

            <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-[#0e1012]">
                <h3 className="font-bold text-gray-500 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">SPINE ({spines.length})</h3>
                {devices.map((dev) => (
                  <button
                    type="button"
                    key={dev.id}
                    onClick={() => toggleSelection(dev.id, 'spine')}
                    className={`w-full p-3 mb-2 rounded border text-left flex justify-between items-center transition-colors ${spines.includes(dev.id) ? 'bg-pink-100 dark:bg-pink-900/30 border-pink-500' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                  >
                    <div className="flex items-center gap-2">
                      <Server size={14} />
                      <span className="text-sm font-bold">{dev.name}</span>
                    </div>
                    {spines.includes(dev.id) && <CheckCircle size={14} className="text-pink-500" />}
                  </button>
                ))}
              </div>

              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-[#0e1012]">
                <h3 className="font-bold text-gray-500 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">LEAF ({leafs.length})</h3>
                {devices.map((dev) => (
                  <button
                    type="button"
                    key={dev.id}
                    onClick={() => toggleSelection(dev.id, 'leaf')}
                    className={`w-full p-3 mb-2 rounded border text-left flex justify-between items-center transition-colors ${leafs.includes(dev.id) ? 'bg-cyan-100 dark:bg-cyan-900/30 border-cyan-500' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                  >
                    <div className="flex items-center gap-2">
                      <Server size={14} />
                      <span className="text-sm font-bold">{dev.name}</span>
                    </div>
                    {leafs.includes(dev.id) && <CheckCircle size={14} className="text-cyan-500" />}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setStep(2)}
                disabled={!canProceed}
                className="px-6 py-2 bg-pink-600 hover:bg-pink-500 rounded font-bold transition-colors disabled:opacity-50"
              >
                Next: Parameters <ArrowRight size={16} className="inline ml-1" />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="p-6 flex-1 flex flex-col justify-center items-center max-w-2xl mx-auto w-full">
            <h2 className="text-xl font-bold mb-6">Fabric Parameters</h2>
            <div className="w-full space-y-4">
              <div>
                <label className="block text-gray-500 text-sm mb-1">BGP ASN</label>
                <input
                  type="number"
                  value={asn}
                  onChange={(e) => setAsn(Number(e.target.value || 65000))}
                  className="w-full bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-700 p-3 rounded text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-gray-500 text-sm mb-1">VNI Base</label>
                <input
                  type="number"
                  value={vniBase}
                  onChange={(e) => setVniBase(Number(e.target.value || 10000))}
                  className="w-full bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-700 p-3 rounded text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <div className="mt-8 flex gap-4 w-full">
              <button onClick={() => setStep(1)} className="flex-1 py-3 border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-800">Back</button>
              <button
                onClick={handleGenerate}
                disabled={loading}
                className="flex-1 py-3 bg-pink-600 hover:bg-pink-500 rounded font-bold flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loading ? <RefreshCw className="animate-spin" /> : <Code />} Generate Configs
              </button>
            </div>
          </div>
        )}

        {step === 3 && generatedConfigs && (
          <div className="p-6 flex-1 flex flex-col overflow-hidden">
            <h2 className="text-lg font-bold mb-4 flex items-center justify-between">
              <span>Preview and Execution</span>
              <span className="text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-3 py-1 rounded">Deploy Engine Ready</span>
            </h2>

            <div className="flex-1 overflow-y-auto grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="space-y-4">
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-[#0e1012]">
                  <div className="flex items-center gap-2 text-sm font-bold">
                    <ShieldCheck size={16} className="text-emerald-500" /> Runbook
                  </div>
                  <div className="mt-2 text-xs text-gray-500">
                    1) Dry-run validates rendered configs before network touch.
                    <br />
                    2) Deploy applies commands to all selected nodes.
                    <br />
                    3) On device error, rollback is attempted where supported.
                  </div>
                </div>
                {sortedConfigs.map(([devId, config]) => (
                  <div key={devId} className="bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-700 rounded-lg p-4 font-mono text-xs overflow-x-auto">
                    <div className="text-pink-500 font-bold mb-2"># Device ID: {devId}</div>
                    <pre className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{config}</pre>
                  </div>
                ))}
              </div>

              <div className="space-y-4">
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-[#0e1012]">
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => runFabric(true)}
                      disabled={deployLoading || approvalSubmitting}
                      className="px-4 py-2 border border-blue-400 text-blue-600 dark:text-blue-300 rounded font-bold hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-50"
                    >
                      {deployLoading ? 'Running...' : 'Dry Run Validate'}
                    </button>
                    <button
                      onClick={runSmartFabricDeploy}
                      disabled={deployLoading || approvalSubmitting}
                      className={`px-4 py-2 text-white rounded font-bold flex items-center gap-2 disabled:opacity-50 ${fabricSmartIsApproval ? 'bg-amber-600 hover:bg-amber-500' : 'bg-green-600 hover:bg-green-500'}`}
                    >
                      {fabricSmartSubmitting ? <RefreshCw className="animate-spin" size={16} /> : fabricSmartIsApproval ? <CheckCircle size={16} /> : <Play size={16} fill="currentColor" />}
                      {fabricSmartSubmitting ? 'Processing...' : fabricDeployPolicy.label}
                    </button>
                  </div>
                  <div className="mt-2 text-xs text-gray-500">{fabricDeployPolicy.reason}</div>
                  {deploySummary ? (
                    <div className="mt-3 text-xs text-gray-500">
                      total={deploySummary.total} success={deploySummary.success} failed={deploySummary.failed} dry_run={deploySummary.dry_run}
                    </div>
                  ) : null}
                </div>

                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-white dark:bg-[#0e1012] max-h-[420px] overflow-auto">
                  <div className="text-sm font-bold mb-2">Execution Results</div>
                  {deployResults.length === 0 ? (
                    <InlineEmpty label="No execution results yet." className="py-4" />
                  ) : (
                    <div className="space-y-2">
                      {deployResults.map((r) => (
                        <div key={`${r.device_id}-${r.status}`} className="rounded border border-gray-200 dark:border-gray-700 p-2">
                          <div className="text-xs font-bold">
                            {r.device_name || `Device ${r.device_id}`} - <span className={r.status === 'success' ? 'text-emerald-500' : r.status === 'dry_run' ? 'text-blue-500' : 'text-red-500'}>{r.status}</span>
                          </div>
                          {Array.isArray(r.validation_issues) && r.validation_issues.length > 0 ? (
                            <div className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">validation: {r.validation_issues.join(', ')}</div>
                          ) : null}
                          {r.error ? <div className="text-[11px] text-red-600 dark:text-red-400 mt-1">{r.error}</div> : null}
                          {r.rollback?.attempted ? (
                            <div className="text-[11px] mt-1">
                              rollback: {r.rollback.success ? 'success' : 'failed'} {r.rollback.message ? `(${r.rollback.message})` : ''}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setStep(2)} className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-800">Back</button>
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
};

export default FabricPage;
