import React, { useState, useEffect, useMemo } from 'react';
import { HardDrive, Upload, Trash2, RefreshCw, Zap, XCircle, Activity, Server, Play, Clock, CheckCircle, AlertTriangle } from 'lucide-react';
import { SDNService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import useVisiblePolling from '../../hooks/useVisiblePolling';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';

const ImagePage = () => {
  const { isOperator, isAdmin } = useAuth();
  const { toast } = useToast();

  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);

  // Deploy State
  const [showDeploy, setShowDeploy] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [devices, setDevices] = useState([]); // All devices
  const [selectedDeviceIds, setSelectedDeviceIds] = useState([]);
  const [deploying, setDeploying] = useState(false);

  // Jobs State
  const [showJobs, setShowJobs] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const hasActiveJobs = useMemo(() => {
    const activeStatuses = new Set([
      'queued',
      'pending',
      'running',
      'in_progress',
      'inprogress',
      'deploying',
      'retrying',
      'started',
    ]);
    return jobs.some((job) => activeStatuses.has(String(job?.status || '').trim().toLowerCase()));
  }, [jobs]);

  const fetchImages = async () => {
    setLoading(true);
    try {
      const res = await SDNService.getImages();
      setImages(res.data);
    } catch (err) {
      console.error("Failed to load images:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchDevices = async () => {
    try {
      const res = await SDNService.getDevices();
      setDevices(res.data);
    } catch (err) {
      console.error("Failed to load devices");
    }
  };

  const fetchJobs = async () => {
    setLoadingJobs(true);
    try {
      const res = await SDNService.getUpgradeJobs();
      setJobs(res.data);
    } catch (err) {
      console.error("Failed load jobs");
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    fetchImages();
    // Start job polling if jobs view is open? 
    // Simplified: Fetch once on mount or manual refresh
  }, []);

  useVisiblePolling(() => {
    void fetchJobs();
  }, hasActiveJobs ? 3000 : 12000, {
    enabled: !!showJobs,
    immediate: true,
    runOnVisible: true,
    minGapMs: hasActiveJobs ? 2000 : 5000,
    backoffOnError: false,
  });

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const version = window.prompt("Enter firmware version (e.g. 17.03.05):", "1.0");
    if (!version) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('version', version);
    formData.append('device_family', 'cisco_ios'); // Default, maybe add a dropdown later
    formData.append('is_golden', 'false');

    try {
      setLoading(true);
      await SDNService.uploadImage(formData);
      toast.success(t('images_upload_success', 'Image uploaded successfully!'));
      fetchImages();
    } catch (err) {
      toast.error(`${t('images_upload_failed', 'Upload failed')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm(t('images_delete_confirm', 'Delete this image?'))) return;
    try {
      await SDNService.deleteImage(id);
      fetchImages();
    } catch (err) {
      toast.error(t('images_delete_failed', 'Delete failed'));
    }
  };

  const openDeployModal = (image) => {
    setSelectedImage(image);
    setSelectedDeviceIds([]);
    fetchDevices();
    setShowDeploy(true);
  };

  const toggleDevice = (id) => {
    if (selectedDeviceIds.includes(id)) {
      setSelectedDeviceIds(selectedDeviceIds.filter(d => d !== id));
    } else {
      setSelectedDeviceIds([...selectedDeviceIds, id]);
    }
  };

  const executeDeploy = async () => {
    if (!selectedImage || selectedDeviceIds.length === 0) return;
    if (
      !window.confirm(
        t('images_deploy_confirm_fmt', 'Deploy {file} to {count} devices? This will copy, install and REBOOT.')
          .replace('{file}', String(selectedImage.filename || ''))
          .replace('{count}', String(selectedDeviceIds.length)),
      )
    ) return;

    setDeploying(true);
    try {
      await SDNService.deployImage(selectedImage.id, selectedDeviceIds);
      toast.success(t('images_deploy_started', 'Deployment started! Check Job Status for progress.'));
      setShowDeploy(false);
      setShowJobs(true);
    } catch (err) {
      toast.error(`${t('images_deploy_failed', 'Deployment failed')}: ${err.message}`);
    } finally {
      setDeploying(false);
    }
  };

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full min-h-0 text-gray-900 dark:text-white animate-fade-in overflow-hidden flex flex-col relative transition-colors">
      <div className="flex flex-col gap-3 lg:flex-row lg:justify-between lg:items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Software Image Management (SWIM)</h1>
          <p className="text-sm text-gray-500">Repository and Upgrade Controller</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setShowJobs(!showJobs)}
            className={`h-10 inline-flex items-center gap-2 px-4 border rounded-lg transition-colors text-sm font-bold ${showJobs ? 'bg-purple-100 border-purple-300 text-purple-600 dark:bg-purple-900/30 dark:border-purple-500 dark:text-purple-400' : 'bg-white dark:bg-[#25282c] border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300'}`}
          >
            <Activity size={16} /> Job Status
          </button>

          <button onClick={fetchImages} className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-white">
            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          </button>

          {isOperator() && (
            <label className="h-10 inline-flex items-center gap-2 px-4 bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors font-medium text-sm cursor-pointer">
              <Upload size={16} /> Upload Image
              <input type="file" className="hidden" onChange={handleUpload} />
            </label>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-4 overflow-hidden">
        {/* Main Image List */}
        <SectionCard className={`transition-all duration-300 flex-1 min-h-0 overflow-hidden flex flex-col shadow-sm ${showJobs ? 'lg:w-2/3' : ''}`}>
          <div className="overflow-auto flex-1">
            <table className="min-w-[640px] w-full text-left">
              <thead className="bg-gray-100 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-800 sticky top-0">
                <tr>
                  <th className="px-6 py-3 text-xs font-bold text-gray-500 uppercase">File Name</th>
                  <th className="px-6 py-3 text-xs font-bold text-gray-500 uppercase">Version</th>
                  <th className="px-6 py-3 text-xs font-bold text-gray-500 uppercase">Family</th>
                  <th className="px-6 py-3 text-xs font-bold text-gray-500 uppercase">Size</th>
                  <th className="px-6 py-3 text-xs font-bold text-gray-500 uppercase text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {loading && (
                  <tr>
                    <td colSpan={5} className="px-6 py-10">
                      <InlineLoading label={t('common_loading', 'Loading...')} />
                    </td>
                  </tr>
                )}
                {images.map((img) => (
                  <tr key={img.id} className="hover:bg-gray-50 dark:hover:bg-[#25282c] transition-colors group border-b border-gray-100 dark:border-gray-800/50">
                    <td className="px-6 py-4 flex items-center gap-3">
                      <HardDrive size={18} className="text-blue-500" />
                      <div>
                        <div className="font-bold text-sm text-gray-900 dark:text-gray-200">{img.filename}</div>
                        <div className="text-xs text-gray-600 dark:text-gray-500">MD5: {img.md5_checksum ? img.md5_checksum.substring(0, 8) + '...' : 'pending'}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300 font-mono">{img.version}</td>
                    <td className="px-6 py-4">
                      <span className="px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded text-xs text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700">{img.device_family}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 font-mono">{img.size_bytes ? `${(img.size_bytes / 1024 / 1024).toFixed(1)} MB` : '-'}</td>
                    <td className="px-6 py-4 text-right flex justify-end gap-2">
                      {/* Deploy Button */}
                      {isAdmin() && (
                        <button onClick={() => openDeployModal(img)} className="flex items-center gap-1 px-3 py-1.5 bg-purple-50 dark:bg-purple-900/20 hover:bg-purple-100 dark:hover:bg-purple-900/40 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-900/50 rounded-lg text-xs font-bold transition-colors">
                          <Zap size={14} /> Deploy
                        </button>
                      )}
                      {/* Delete Button */}
                      {isAdmin() && (
                        <button onClick={() => handleDelete(img.id)} className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 rounded text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-500 transition-colors">
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {!loading && images.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-10">
                      <InlineEmpty label={t('images_empty', 'No images available.')} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* Jobs Sidebar */}
        {showJobs && (
          <div className="w-full lg:w-[360px] lg:min-w-[320px] max-h-[38vh] lg:max-h-none bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden flex flex-col animate-slide-in-right shadow-xl z-10">
            <div className="p-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#25282c] flex justify-between items-center">
              <h3 className="font-bold text-gray-800 dark:text-gray-200 flex items-center gap-2">
                <Activity size={18} className="text-purple-500 dark:text-purple-400" /> Upgrade Jobs
              </h3>
              <button onClick={() => setShowJobs(false)} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"><XCircle size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {jobs.map(job => (
                <div key={job.id} className="bg-gray-50 dark:bg-[#0e1012] border border-gray-200 dark:border-gray-800 rounded-lg p-3">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-2">
                      <Server size={14} className="text-gray-600 dark:text-gray-500" />
                      <span className="font-bold text-sm text-gray-700 dark:text-gray-300">Device #{job.device_id}</span>
                    </div>
                    <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${job.status === 'completed' ? 'bg-green-900/30 text-green-400' :
                      job.status === 'failed' ? 'bg-red-900/30 text-red-400' :
                        job.status === 'running' ? 'bg-blue-900/30 text-blue-400' : 'bg-gray-800 text-gray-500'
                      }`}>
                      {job.status}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-gray-800 h-1.5 rounded-full mb-2 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${job.status === 'failed' ? 'bg-red-500' : 'bg-purple-500'}`}
                      style={{ width: `${job.progress_percent}%` }}
                    />
                  </div>

                  <div className="flex justify-between items-center text-xs text-gray-600 dark:text-gray-500">
                    <span>{job.current_stage}</span>
                    <span>{job.progress_percent}%</span>
                  </div>

                  {/* Logs Preview (Last line) */}
                  {job.logs && (
                    <div className="mt-2 p-2 bg-gray-800 dark:bg-black rounded text-[10px] text-gray-300 dark:text-gray-400 font-mono truncate">
                      {job.logs.split('\n').pop()}
                    </div>
                  )}

                  {job.error_message && (
                    <div className="mt-1 text-[10px] text-red-400 font-bold flex items-center gap-1">
                      <AlertTriangle size={10} /> {job.error_message}
                    </div>
                  )}
                </div>
              ))}
              {loadingJobs && (
                <InlineLoading label={t('common_loading', 'Loading...')} className="py-10" />
              )}
              {!loadingJobs && jobs.length === 0 && (
                <InlineEmpty label={t('images_no_jobs', 'No active jobs.')} className="py-10" />
              )}
            </div>
          </div>
        )}
      </div>

      {/* Deploy Modal */}
      {showDeploy && (
        <div className="absolute inset-0 z-50 bg-black/50 dark:bg-black/80 flex items-center justify-center p-8 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-2xl bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-full">
            <div className="p-5 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#25282c]">
              <h2 className="text-xl font-bold flex items-center gap-2 text-gray-900 dark:text-white">
                <Zap className="text-purple-500" /> Deploy Firmware
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                You are about to install <span className="text-gray-900 dark:text-white font-bold">{selectedImage?.filename}</span> ({selectedImage?.version}).
              </p>
            </div>

            <div className="p-6 overflow-y-auto flex-1 bg-white dark:bg-[#0e1012]">
              <h3 className="text-sm font-bold text-gray-500 uppercase mb-3">Target Devices</h3>
              <div className="grid gap-2 max-h-60 overflow-y-auto">
                {devices.map(dev => (
                  <div
                    key={dev.id}
                    onClick={() => toggleDevice(dev.id)}
                    className={`p-3 border rounded-lg flex items-center justify-between cursor-pointer transition-colors ${selectedDeviceIds.includes(dev.id) ? 'bg-purple-50 border-purple-500 dark:bg-purple-900/20' : 'bg-white border-gray-200 hover:border-gray-400 dark:bg-[#1b1d1f] dark:border-gray-800 dark:hover:border-gray-600'}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${selectedDeviceIds.includes(dev.id) ? 'bg-purple-500 border-purple-500' : 'border-gray-300 dark:border-gray-600'}`}>
                        {selectedDeviceIds.includes(dev.id) && <CheckCircle size={10} className="text-white" />}
                      </div>
                      <div>
                        <div className="font-bold text-sm text-gray-900 dark:text-gray-200">{dev.name}</div>
                        <div className="text-xs text-gray-500">{dev.ip_address} | {dev.model}</div>
                      </div>
                    </div>
                    <div className={`text-xs px-2 py-0.5 rounded ${dev.status === 'online' ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                      {dev.status}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-900/30 rounded-lg">
                <h4 className="flex items-center gap-2 text-yellow-600 dark:text-yellow-500 font-bold text-sm mb-2">
                  <AlertTriangle size={16} /> Warning
                </h4>
                <ul className="list-disc list-inside text-xs text-yellow-700 dark:text-yellow-200/80 space-y-1">
                  <li>This operation will transfer the firmware file to the device storage.</li>
                  <li>After verification, the device will receive a <strong>bootsystem</strong> change and will be <strong>REBOOTED</strong>.</li>
                  <li>Network connectivity will be lost during reboot (~5-10 mins).</li>
                </ul>
              </div>
            </div>

            <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#25282c] flex justify-end gap-3">
              <button onClick={() => setShowDeploy(false)} className="px-4 py-2 text-sm text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors">Cancel</button>
              <button
                onClick={executeDeploy}
                disabled={deploying || selectedDeviceIds.length === 0}
                className={`flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded-lg transition-colors ${(deploying || selectedDeviceIds.length === 0) ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {deploying ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
                {deploying ? 'Initializing...' : 'Start Deployment'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImagePage;
