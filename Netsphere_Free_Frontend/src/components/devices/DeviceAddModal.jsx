import React, { useState, useEffect } from 'react';
import { X, Save, Server, Shield, Globe, Terminal, MapPin } from 'lucide-react';
import { DeviceService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import {
  DOMESTIC_DEVICE_VENDOR_OPTIONS,
  GLOBAL_DEVICE_VENDOR_OPTIONS,
  OTHER_DEVICE_VENDOR_OPTIONS,
} from '../../utils/deviceVendorCatalog';

const DeviceAddModal = ({ isOpen, onClose, onDeviceAdded, deviceToEdit }) => {
  useLocaleRerender();
  const { toast } = useToast();
  const initialFormState = {
    name: '',
    ip_address: '',
    device_type: 'cisco_ios',
    site_id: '',
    snmp_community: 'public',
    ssh_username: '',
    ssh_password: '',
    ssh_port: 22,
    enable_password: '',
    polling_interval: 60,
    status_interval: 300,
    auto_provision_template_id: ''
  };

  const [formData, setFormData] = useState(initialFormState);
  const [sites, setSites] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchSites = async () => {
    try {
      const res = await DeviceService.getSites();
      setSites(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Failed to fetch sites:', err);
    }
  };

  const fetchTemplates = async () => {
    try {
      const res = await DeviceService.getTemplates();
      setTemplates(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    fetchSites();
    fetchTemplates();

    if (deviceToEdit) {
      setFormData({
        ...initialFormState,
        ...deviceToEdit,
        site_id: deviceToEdit.site_id || '',
        ssh_password: '',
        enable_password: ''
      });
      return;
    }

    setFormData(initialFormState);
  }, [isOpen, deviceToEdit]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const payload = {
        ...formData,
        ssh_port: parseInt(formData.ssh_port, 10) || 22,
        polling_interval: parseInt(formData.polling_interval, 10) || 60,
        status_interval: parseInt(formData.status_interval, 10) || 300,
        site_id: formData.site_id ? parseInt(formData.site_id, 10) : null,
        auto_provision_template_id: formData.auto_provision_template_id ? parseInt(formData.auto_provision_template_id, 10) : null
      };

      if (deviceToEdit) {
        if (!payload.ssh_password) delete payload.ssh_password;
        if (!payload.enable_password) delete payload.enable_password;
        await DeviceService.update(deviceToEdit.id, payload);
        toast.success(t('devices_update_success', 'Device updated successfully.'));
      } else {
        await DeviceService.create(payload);
        toast.success(t('devices_create_success', 'Device created successfully.'));
      }

      onDeviceAdded();
      onClose();
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || t('devices_save_failed', 'Failed to save device.'));
    } finally {
      setLoading(false);
    }
  };

  const labelStyle = 'text-xs font-bold text-gray-700 dark:text-gray-400 uppercase';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-center p-6 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#202327]">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              {deviceToEdit ? <Save className="text-blue-500" size={24} /> : <Server className="text-green-500" size={24} />}
              {deviceToEdit ? t('devices_edit_title', 'Edit Device') : t('devices_add_title', 'Add New Device')}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              {deviceToEdit ? t('devices_edit_desc', 'Update connection details.') : t('devices_add_desc', 'Register a new network node to inventory.')}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors">
            <X size={20} className="text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto custom-scrollbar">
          {error && (
            <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
              {error}
            </div>
          )}

          <form id="deviceForm" onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_col_device', 'Device')} *</label>
                <input required name="name" value={formData.name} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder={t('devices_name_placeholder', 'e.g. Core-Switch-01')} />
              </div>
              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_col_ip', 'IP Address')} *</label>
                <input required name="ip_address" value={formData.ip_address} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white font-mono focus:ring-2 focus:ring-blue-500 outline-none" placeholder="192.168.1.1" />
              </div>
              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_col_type', 'Type')}</label>
                <select name="device_type" value={formData.device_type} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none">
                  <optgroup label={t('devices_vendor_global', 'Global Vendors')}>
                    {GLOBAL_DEVICE_VENDOR_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label={t('devices_vendor_domestic', 'Domestic Vendors (Korea)')}>
                    {DOMESTIC_DEVICE_VENDOR_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label={t('common_other', 'Other')}>
                    {OTHER_DEVICE_VENDOR_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value === 'unknown'
                          ? t('devices_vendor_unknown', option.label)
                          : option.label}
                      </option>
                    ))}
                  </optgroup>
                </select>
              </div>

              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_auto_provision', 'Auto Provision (Day 0)')}</label>
                <div className="relative">
                  <Terminal className="absolute left-3 top-3 text-purple-500" size={16} />
                  <select
                    name="auto_provision_template_id"
                    value={formData.auto_provision_template_id}
                    onChange={handleChange}
                    disabled={!!deviceToEdit}
                    className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none appearance-none"
                  >
                    <option value="">{t('devices_no_auto_provision', '-- No Auto Provision --')}</option>
                    {templates.map((tmpl) => (
                      <option key={tmpl.id} value={tmpl.id}>
                        {tmpl.name} (v{tmpl.version})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_assign_site', 'Assign Site (Location)')}</label>
                <div className="relative">
                  <MapPin className="absolute left-3 top-3 text-gray-400" size={16} />
                  <select
                    name="site_id"
                    value={formData.site_id}
                    onChange={handleChange}
                    className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none appearance-none"
                  >
                    <option value="">{t('devices_global_no_site', '-- Global (No Site) --')}</option>
                    {sites.map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.name} ({site.type})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className={labelStyle}>{t('devices_snmp_community', 'SNMP Community')}</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-3 text-gray-400" size={16} />
                  <input
                    name="snmp_community"
                    value={formData.snmp_community}
                    onChange={handleChange}
                    className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    placeholder={t('devices_snmp_community_placeholder', 'public')}
                  />
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
              <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                <Shield size={16} className="text-indigo-500" /> {t('devices_ssh_credentials', 'SSH Credentials')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className={labelStyle}>{t('settings_username', 'Username')}</label>
                  <input
                    name="ssh_username"
                    value={formData.ssh_username}
                    onChange={handleChange}
                    className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    placeholder={t('settings_username_placeholder', 'admin')}
                  />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>{t('settings_password', 'Password')}</label>
                  <input type="password" name="ssh_password" value={formData.ssh_password} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder={deviceToEdit ? t('devices_unchanged', '(Unchanged)') : '********'} />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>{t('devices_enable_secret', 'Enable Secret')}</label>
                  <input type="password" name="enable_password" value={formData.enable_password} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder={deviceToEdit ? t('devices_unchanged', '(Unchanged)') : t('common_optional', 'Optional')} />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>{t('devices_ssh_port', 'SSH Port')}</label>
                  <div className="relative">
                    <Terminal className="absolute left-3 top-3 text-gray-400" size={16} />
                    <input type="number" name="ssh_port" value={formData.ssh_port} onChange={handleChange} className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" />
                  </div>
                </div>
              </div>
            </div>
          </form>
        </div>

        <div className="p-6 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#202327] flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors">
            {t('common_cancel', 'Cancel')}
          </button>
          <button
            type="submit"
            form="deviceForm"
            disabled={loading}
            className={`px-5 py-2.5 text-sm font-bold text-white rounded-lg shadow-lg flex items-center gap-2 transition-all ${
              loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20'
            }`}
          >
            {loading ? t('devices_processing', 'Processing...') : (deviceToEdit ? t('devices_update_changes', 'Update Changes') : t('devices_register', 'Register Device'))}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeviceAddModal;
