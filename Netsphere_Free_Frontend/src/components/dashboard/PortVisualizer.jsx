import React from 'react';
import { Server } from 'lucide-react';

const PortVisualizer = ({ interfaces = [] }) => {
  // 인터페이스 데이터가 없으면 48개 빈 슬롯 생성 (스켈레톤)
  const displayPorts = interfaces.length > 0
    ? interfaces
    : Array.from({ length: 48 }, (_, i) => ({ id: i, name: `Port ${i+1}`, status: 'unknown' }));

  const getPortColor = (status) => {
    const s = status?.toLowerCase() || '';
    if (s.includes('up')) return 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)] border-green-600 text-black';
    if (s.includes('down')) return 'bg-red-500/20 border-red-900 text-red-500';
    if (s.includes('admin')) return 'bg-gray-600 border-gray-500 text-gray-400';
    return 'bg-[#3b4754] border-[#4b5563] text-gray-500'; // Unknown
  };

  return (
    <div className="bg-[#1e293b] rounded-xl border border-[#283039] p-6 shadow-lg mb-6">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-white font-semibold flex items-center gap-2">
          <Server className="text-[#137fec]" size={20} />
          Port Status Visualization
        </h3>
        <div className="flex gap-4 text-xs">
          <div className="flex items-center gap-2"><div className="w-2 h-2 bg-green-500 rounded-sm"></div><span className="text-[#9dabb9]">UP</span></div>
          <div className="flex items-center gap-2"><div className="w-2 h-2 bg-red-500/50 rounded-sm"></div><span className="text-[#9dabb9]">DOWN</span></div>
          <div className="flex items-center gap-2"><div className="w-2 h-2 bg-gray-600 rounded-sm"></div><span className="text-[#9dabb9]">DISABLED</span></div>
        </div>
      </div>

      <div className="bg-[#111418] p-4 rounded-lg border border-[#283039] overflow-x-auto custom-scrollbar">
        {/* 간단하게 2열로 배치하지 않고 Flex Wrap으로 처리하여 포트 수에 유동적으로 대응 */}
        <div className="flex flex-wrap gap-2">
            {displayPorts.map((port, idx) => {
                // 이름에서 숫자만 추출하거나 짧게 표시 (예: GigabitEthernet1/0/1 -> 1)
                const shortName = port.name.replace(/[^\d/]/g, '').split('/').pop() || (idx + 1);

                return (
                  <div
                    key={idx}
                    title={`${port.name}: ${port.status}`}
                    className={`w-10 h-10 rounded border flex items-center justify-center text-[10px] font-mono font-bold transition-all cursor-help ${getPortColor(port.status)}`}
                  >
                    {shortName}
                  </div>
                );
            })}
        </div>
      </div>
    </div>
  );
};

export default PortVisualizer;