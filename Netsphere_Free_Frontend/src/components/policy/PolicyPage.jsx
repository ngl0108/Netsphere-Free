import React, { useState, useEffect } from 'react';
import { Shield, Plus, CheckCircle, XCircle, MoreHorizontal, RefreshCw, Trash2, Edit, Save, ArrowLeft, FileCode, Zap } from 'lucide-react';
import { SDNService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';

const PolicyPage = () => {
    useLocaleRerender();
    const { isOperator, isAdmin } = useAuth(); // [RBAC]
    const { toast } = useToast();

    const [policies, setPolicies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedPolicy, setSelectedPolicy] = useState(null); // 모달 선택 상태

    const fetchPolicies = async () => {
        setLoading(true);
        try {
            const res = await SDNService.getPolicies();
            setPolicies(res.data);
        } catch (err) {
            console.error("Failed to load policies:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async () => {
        const name = window.prompt(t('policy_enter_name_prompt', 'Enter policy name:'), t('policy_new_default_name', 'New Security Policy'));
        if (!name) return;

        try {
            setLoading(true);
            await SDNService.createPolicy({
                name,
                type: 'ACL',
                description: t('policy_created_from_web', 'Created from web interface'),
                rules: []
            });
            fetchPolicies();
        } catch (err) {
            toast.error(t('policy_create_failed', 'Failed to create policy'));
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm(t('policy_confirm_delete', 'Delete this policy?'))) return;
        try {
            setLoading(true);
            await SDNService.deletePolicy(id);
            fetchPolicies();
        } catch (err) {
            toast.error(t('policy_delete_failed', 'Failed to delete policy'));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPolicies();
    }, []);

    return (
        <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full min-h-0 text-gray-900 dark:text-white animate-fade-in overflow-y-auto custom-scrollbar">
            {/* 상세 편집 모달 */}
            {selectedPolicy ? (
                <PolicyDetailByView
                    policy={selectedPolicy}
                    onClose={() => { setSelectedPolicy(null); fetchPolicies(); }}
                />
            ) : (
                <>
                    <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-6">
                        <div>
                            <h1 className="text-2xl font-bold">{t('policy_title', 'Security Policies')}</h1>
                            <p className="text-sm text-gray-500">{t('policy_desc', 'Define and enforce network security rules.')}</p>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                            <button onClick={fetchPolicies} className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400">
                                <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
                            </button>
                            {/* [RBAC] Only Network Admin+ can create */}
                            {isOperator() && (
                                <button onClick={handleCreate} className="h-10 inline-flex items-center gap-2 px-4 bg-green-600 hover:bg-green-500 rounded-lg transition-colors font-medium text-sm">
                                    <Plus size={16} /> {t('policy_create', 'Create Policy')}
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4">
                        {loading ? (
                            <SectionCard className="py-10">
                                <InlineLoading label={t('policy_loading', 'Loading policies...')} />
                            </SectionCard>
                        ) : policies.length === 0 ? (
                            <SectionCard className="py-10">
                                <InlineEmpty label={t('policy_no_active', 'No active policies found.')} />
                            </SectionCard>
                        ) : (
                            policies.map((policy) => (
                                <div key={policy.id} onClick={() => setSelectedPolicy(policy)} className="bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 p-4 rounded-xl flex items-center justify-between hover:border-blue-500 transition-colors cursor-pointer group shadow-sm">
                                    <div className="flex items-center gap-4">
                                        <div className={`p-3 rounded-lg ${policy.status === 'active' ? 'bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:text-blue-500' : 'bg-gray-100 text-gray-500 dark:bg-gray-700/30 dark:text-gray-500'}`}>
                                            <Shield size={24} />
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-lg text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{policy.name}</h3>
                                            <div className="flex items-center gap-3 text-sm text-gray-500 mt-1">
                                                <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs border border-gray-200 dark:border-gray-700 font-medium">{policy.type || 'ACL'}</span>
                                                <span>{policy.rules?.length || 0} {t('policy_rules', 'Rules')}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-6">
                                        <div className="flex items-center gap-2">
                                            {policy.status === 'active' ? <CheckCircle size={16} className="text-green-500" /> : <XCircle size={16} className="text-gray-500" />}
                                            <span className={`text-sm font-medium ${policy.status === 'active' ? 'text-green-500' : 'text-gray-500'}`}>
                                                {policy.status ? policy.status.toUpperCase() : 'UNKNOWN'}
                                            </span>
                                        </div>
                                        <div className="flex gap-2">
                                            {/* [RBAC] Only Admin can delete */}
                                            {isAdmin() && (
                                                <button onClick={(e) => { e.stopPropagation(); handleDelete(policy.id) }} className="p-2 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-full text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-500">
                                                    <Trash2 size={18} />
                                                </button>
                                            )}
                                            {/* [RBAC] Only Network Admin+ can edit */}
                                            {isOperator() && (
                                                <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full text-gray-500 dark:text-gray-400">
                                                    <Edit size={18} />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </>
            )}
        </div>
    );
};

// --- 상세/편집 컴포넌트 ---
const PolicyDetailByView = ({ policy, onClose }) => {
    useLocaleRerender();
    const { toast } = useToast();
    const [rules, setRules] = useState(policy.rules || []);
    const [name, setName] = useState(policy.name);
    const [description, setDescription] = useState(policy.description || "");
    const [autoRemediate, setAutoRemediate] = useState(policy.auto_remediate || false); // [NEW] Auto-Remediation State
    const [saving, setSaving] = useState(false);

    // 새 규칙 추가
    const addRule = () => {
        setRules([...rules, {
            priority: (rules.length + 1) * 10,
            action: 'permit',
            match_conditions: {
                protocol: 'tcp',
                source: 'any',
                destination: 'any',
                port: '80'
            }
        }]);
    };

    // 규칙 삭제
    const removeRule = (index) => {
        const newRules = rules.filter((_, i) => i !== index);
        setRules(newRules);
    };

    // 규칙 내용 변경
    const updateRule = (index, field, value) => {
        const newRules = [...rules];
        if (field === 'priority' || field === 'action') {
            newRules[index][field] = value;
        } else {
            // match_conditions 내부 업데이트
            newRules[index].match_conditions = {
                ...newRules[index].match_conditions,
                [field]: value
            };
        }
        setRules(newRules);
    };

    const [previewCommands, setPreviewCommands] = useState(null); // 미리보기 데이터
    const [showPreview, setShowPreview] = useState(false);

    const handlePreview = async () => {
        try {
            const res = await SDNService.previewPolicy(policy.id);
            setPreviewCommands(res.data.commands.join('\n'));
            setShowPreview(true);
        } catch (e) {
            toast.error(t('policy_preview_failed', 'Preview failed'));
        }
    };

    const [showDeploy, setShowDeploy] = useState(false);
    const [deployDevices, setDeployDevices] = useState([]); // 배포 대상 장비 목록 (Load from API)
    const [selectedDeviceIds, setSelectedDeviceIds] = useState([]);
    const [deployResults, setDeployResults] = useState(null); // 배포 결과
    const [deploying, setDeploying] = useState(false);

    // 장비 목록 불러오기 및 모달 열기
    const handleOpenDeploy = async () => {
        try {
            // 예시: Dashboard 등에서 쓰는 /devices 엔드포인트 사용
            const res = await SDNService.getDevices();
            setDeployDevices(res.data);
            setShowDeploy(true);
            setDeployResults(null);
            setSelectedDeviceIds([]);
        } catch (e) {
            toast.error(t('policy_load_devices_failed', 'Failed to load devices for deployment.'));
        }
    };

    const handleExecuteDeploy = async () => {
        if (selectedDeviceIds.length === 0) {
            toast.warning(t('config_select_at_least_one_device', 'Please select at least one device.'));
            return;
        }

        if (!window.confirm(t('policy_confirm_deploy', `Deploy policy to ${selectedDeviceIds.length} devices? This will push configuration immediately.`))) return;

        setDeploying(true);
        try {
            const res = await SDNService.deployPolicy(policy.id, selectedDeviceIds);
            setDeployResults(res.data.results);
        } catch (e) {
            toast.error(t('policy_deploy_failed', 'Deployment failed.'));
        } finally {
            setDeploying(false);
        }
    };

    const toggleDeviceSelection = (id) => {
        if (selectedDeviceIds.includes(id)) {
            setSelectedDeviceIds(selectedDeviceIds.filter(dId => dId !== id));
        } else {
            setSelectedDeviceIds([...selectedDeviceIds, id]);
        }
    };

    const handleDeploy = async () => {
        await handleOpenDeploy();
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await SDNService.updatePolicy(policy.id, {
                name,
                description,
                auto_remediate: autoRemediate, // [NEW] Payload
                rules: rules
            });
            toast.success(t('policy_save_success', 'Policy saved successfully!'));
            onClose();
        } catch (e) {
            console.error(e);
            toast.error(t('policy_save_failed', 'Failed to save policy.'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6 relative">
            {/* Deploy Modal */}
            {showDeploy && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-10 animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-xl border border-gray-200 dark:border-gray-700 shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-[#25282c]">
                            <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <Zap size={18} className="text-purple-400" /> {t('policy_deploy_to_devices', 'Deploy Policy to Devices')}
                            </h3>
                            <button onClick={() => setShowDeploy(false)} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"><XCircle size={20} /></button>
                        </div>

                        <div className="p-6 overflow-y-auto bg-white dark:bg-[#0e1012]">
                            {!deployResults ? (
                                <>
                                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t('policy_select_devices_for_apply', 'Select the devices where this policy should be applied:')}</p>
                                    <div className="space-y-2">
                                        {deployDevices.map(dev => (
                                            <div key={dev.id}
                                                onClick={() => toggleDeviceSelection(dev.id)}
                                                className={`p-3 rounded-lg border flex items-center justify-between cursor-pointer transition-colors ${selectedDeviceIds.includes(dev.id) ? 'bg-blue-50 border-blue-500 dark:bg-blue-900/20' : 'bg-gray-50 dark:bg-[#1b1d1f] border-gray-200 dark:border-gray-800 hover:border-gray-400 dark:hover:border-gray-600'}`}
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${selectedDeviceIds.includes(dev.id) ? 'bg-blue-500 border-blue-500' : 'border-gray-400 dark:border-gray-500'}`}>
                                                        {selectedDeviceIds.includes(dev.id) && <div className="w-2 h-2 bg-white rounded-full"></div>}
                                                    </div>
                                                    <div>
                                                        <div className="font-bold text-gray-900 dark:text-white">{dev.name}</div>
                                                        <div className="text-xs text-gray-500">{dev.ip_address} ({dev.device_type})</div>
                                                    </div>
                                                </div>
                                                <div className={`px-2 py-0.5 rounded text-xs ${dev.status === 'online' ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                                                    {dev.status}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            ) : (
                                <div className="space-y-3">
                                    <h4 className="font-bold text-white mb-2">{t('policy_deployment_results', 'Deployment Results')}</h4>
                                    {deployResults.map((res, idx) => (
                                        <div key={idx} className="p-3 bg-gray-50 dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-lg">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="font-bold text-gray-900 dark:text-white">{res.device_name}</span>
                                                <span className={`text-xs font-bold px-2 py-0.5 rounded ${res.status === 'success' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                                    {res.status.toUpperCase()}
                                                </span>
                                            </div>
                                            <p className="text-sm text-gray-600 dark:text-gray-400">{res.message}</p>
                                            {res.output && (
                                                <pre className="mt-2 p-2 bg-black rounded text-xs text-green-300 font-mono overflow-x-auto">
                                                    {JSON.stringify(res.output, null, 2)}
                                                </pre>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-2 bg-gray-50 dark:bg-[#25282c]">
                            {!deployResults ? (
                                <>
                                    <button onClick={() => setShowDeploy(false)} className="px-4 py-2 hover:text-gray-900 dark:hover:text-white text-gray-600 dark:text-gray-400 text-sm">{t('common_cancel', 'Cancel')}</button>
                                    <button
                                        onClick={handleExecuteDeploy}
                                        disabled={deploying || selectedDeviceIds.length === 0}
                                        className={`px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-bold text-sm flex items-center gap-2 ${(deploying || selectedDeviceIds.length === 0) ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    >
                                        <Zap size={16} className={deploying ? "animate-spin" : ""} />
                                        {deploying ? t('policy_deploying', 'Deploying...') : t('policy_deploy_now', 'Deploy Now')}
                                    </button>
                                </>
                            ) : (
                                <button onClick={() => setShowDeploy(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">{t('common_close', 'Close')}</button>
                            )}
                        </div>
                    </div>
                </div>
            )}


            {/* Config Preview Modal */}
            {showPreview && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-10 animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-xl border border-gray-200 dark:border-gray-700 shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-[#25282c]">
                            <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <FileCode size={18} className="text-blue-500 dark:text-blue-400" /> {t('policy_generated_config', 'Generated Configuration')}
                            </h3>
                            <button onClick={() => setShowPreview(false)} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"><XCircle size={20} /></button>
                        </div>
                        <div className="p-4 overflow-y-auto bg-gray-50 dark:bg-[#0e1012] font-mono text-sm text-green-600 dark:text-green-400 whitespace-pre">
                            {previewCommands}
                        </div>
                        <div className="p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end">
                            <button onClick={() => setShowPreview(false)} className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded text-gray-700 dark:text-white text-sm">{t('common_close', 'Close')}</button>
                        </div>
                    </div>
                </div>
            )}

            <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-800 pb-4">
                <div className="flex items-center gap-4">
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-600 dark:text-gray-300">
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('policy_edit_prefix', 'Edit Policy')}: {name}</h2>
                        <p className="text-sm text-gray-500">{t('policy_configure_access_rules', 'Configure access control rules.')}</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={handlePreview}
                        className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors text-gray-700 dark:text-gray-300"
                    >
                        <FileCode size={16} /> {t('policy_preview_config', 'Preview Config')}
                    </button>
                    <button
                        onClick={handleDeploy}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium transition-colors"
                    >
                        <Zap size={16} /> {t('policy_deploy', 'Deploy')}
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors"
                    >
                        {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                        {t('settings_save_changes', 'Save Changes')}
                    </button>
                </div>
            </div>


            {/* 기본 정보 설정 */}
            <div className="bg-white dark:bg-[#1b1d1f] p-4 rounded-xl border border-gray-200 dark:border-gray-800 space-y-4 shadow-sm">
                <h3 className="font-bold text-gray-800 dark:text-gray-300 flex justify-between items-center">
                    <span>{t('policy_basic_info', 'Basic Info')}</span>

                    {/* [NEW] Auto-Remediation Toggle UI */}
                    <div className="flex items-center gap-3 bg-gray-100 dark:bg-[#25282c] px-3 py-1 rounded-lg border border-gray-200 dark:border-gray-700">
                        <div className="text-right">
                            <div className={`text-xs font-bold ${autoRemediate ? 'text-green-400' : 'text-gray-500'}`}>
                                {t('policy_auto_remediation', 'Auto-Remediation')} {autoRemediate ? t('common_on', 'ON') : t('common_off', 'OFF')}
                            </div>
                            <div className="text-[10px] text-gray-500">{t('policy_auto_fix_violations', 'Auto fix violations')}</div>
                        </div>
                        <button
                            onClick={() => setAutoRemediate(!autoRemediate)}
                            className={`w-10 h-5 rounded-full relative transition-colors ${autoRemediate ? 'bg-green-600' : 'bg-gray-700'}`}
                        >
                            <div className={`w-3 h-3 bg-white rounded-full absolute top-1 transition-all ${autoRemediate ? 'left-6' : 'left-1'}`} />
                        </button>
                    </div>
                </h3>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs text-gray-500 font-bold mb-1">{t('policy_name', 'Policy Name')}</label>
                        <input
                            value={name} onChange={e => setName(e.target.value)}
                            className="w-full bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none text-gray-900 dark:text-white"
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-gray-500 font-bold mb-1">{t('visual_label_description', 'Description')}</label>
                        <input
                            value={description} onChange={e => setDescription(e.target.value)}
                            className="w-full bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none text-gray-900 dark:text-white"
                        />
                    </div>
                </div>
            </div>

            {/* 규칙 리스트 (Rule Table) */}
            <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-[#25282c]">
                    <h3 className="font-bold text-gray-800 dark:text-gray-300">{t('policy_rules', 'Rules')} ({rules.length})</h3>
                    <button onClick={addRule} className="text-xs flex items-center gap-1 px-2 py-1 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded text-gray-700 dark:text-gray-200">
                        <Plus size={14} /> {t('policy_add_rule', 'Add Rule')}
                    </button>
                </div>
                <table className="w-full text-left text-sm">
                    <thead className="bg-white dark:bg-[#1b1d1f] text-gray-500 border-b border-gray-200 dark:border-gray-800">
                        <tr>
                            <th className="px-4 py-3 w-16">{t('policy_seq', 'Seq')}</th>
                            <th className="px-4 py-3 w-24">{t('policy_action', 'Action')}</th>
                            <th className="px-4 py-3 w-24">{t('policy_protocol', 'Protocol')}</th>
                            <th className="px-4 py-3">{t('policy_source_ip', 'Source IP')}</th>
                            <th className="px-4 py-3">{t('policy_dest_ip', 'Dest IP')}</th>
                            <th className="px-4 py-3 w-24">{t('policy_dest_port', 'Dest Port')}</th>
                            <th className="px-4 py-3 w-16 text-right">{t('common_delete', 'Del')}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                        {rules.map((rule, idx) => (
                            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-[#25282c] transition-colors text-gray-900 dark:text-gray-300">
                                <td className="px-4 py-2">
                                    <input
                                        type="number" className="w-12 bg-transparent border-b border-gray-300 dark:border-gray-700 focus:border-blue-500 text-center outline-none"
                                        value={rule.priority} onChange={(e) => updateRule(idx, 'priority', parseInt(e.target.value))}
                                    />
                                </td>
                                <td className="px-4 py-2">
                                    <select
                                        className={`bg-transparent border border-gray-300 dark:border-gray-700 rounded px-1 py-0.5 text-xs outline-none ${rule.action === 'deny' ? 'text-red-500 dark:text-red-400 border-red-200 dark:border-red-900/50' : 'text-green-600 dark:text-green-400 border-green-200 dark:border-green-900/50'}`}
                                        value={rule.action} onChange={(e) => updateRule(idx, 'action', e.target.value)}
                                    >
                                        <option value="permit" className="bg-white dark:bg-gray-800 text-green-600 dark:text-green-400">{t('policy_permit', 'Permit')}</option>
                                        <option value="deny" className="bg-white dark:bg-gray-800 text-red-500 dark:text-red-400">{t('policy_deny', 'Deny')}</option>
                                    </select>
                                </td>
                                <td className="px-4 py-2">
                                    <select
                                        className="bg-transparent border-b border-gray-300 dark:border-gray-700 focus:border-blue-500 w-full outline-none text-gray-900 dark:text-gray-300"
                                        value={rule.match_conditions?.protocol || 'tcp'} onChange={(e) => updateRule(idx, 'protocol', e.target.value)}
                                    >
                                        <option value="tcp" className="bg-white dark:bg-gray-800">TCP</option>
                                        <option value="udp" className="bg-white dark:bg-gray-800">UDP</option>
                                        <option value="icmp" className="bg-white dark:bg-gray-800">ICMP</option>
                                        <option value="ip" className="bg-white dark:bg-gray-800">IP</option>
                                    </select>
                                </td>
                                <td className="px-4 py-2">
                                    <input
                                        className="bg-transparent border-b border-gray-300 dark:border-gray-700 focus:border-blue-500 w-full outline-none font-mono text-gray-700 dark:text-gray-300 placeholder-gray-400"
                                        value={rule.match_conditions?.source || 'any'} onChange={(e) => updateRule(idx, 'source', e.target.value)}
                                    />
                                </td>
                                <td className="px-4 py-2">
                                    <input
                                        className="bg-transparent border-b border-gray-300 dark:border-gray-700 focus:border-blue-500 w-full outline-none font-mono text-gray-700 dark:text-gray-300 placeholder-gray-400"
                                        value={rule.match_conditions?.destination || 'any'} onChange={(e) => updateRule(idx, 'destination', e.target.value)}
                                    />
                                </td>
                                <td className="px-4 py-2">
                                    <input
                                        className="bg-transparent border-b border-gray-300 dark:border-gray-700 focus:border-blue-500 w-full outline-none font-mono text-gray-700 dark:text-gray-300 placeholder-gray-400"
                                        value={rule.match_conditions?.port || 'any'} onChange={(e) => updateRule(idx, 'port', e.target.value)}
                                    />
                                </td>
                                <td className="px-4 py-2 text-right">
                                    <button onClick={() => removeRule(idx)} className="text-gray-400 hover:text-red-500 transition-colors">
                                        <XCircle size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {rules.length === 0 && (
                    <div className="p-8 text-center text-gray-500 text-sm">
                        {t('policy_no_rules', "No rules defined. Click 'Add Rule' to start.")}
                    </div>
                )}
            </div>
        </div>
    );
};

export default PolicyPage;
