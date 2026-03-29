import React from 'react';
import { CheckCircle, Activity, Clock, Network } from 'lucide-react';

const StatCard = ({ title, value, subValue, subLabel, icon: Icon, colorClass, trend }) => (
  <div className="bg-[#1e293b] rounded-xl p-5 border border-[#283039] shadow-lg">
    <div className="flex justify-between items-start mb-2">
      <p className="text-[#9dabb9] text-sm font-medium">{title}</p>
      <div className={`p-1.5 rounded-lg ${colorClass} bg-opacity-10`}>
        <Icon size={20} className={colorClass.replace('bg-', 'text-')} />
      </div>
    </div>
    <div className="flex items-baseline gap-2 mt-2">
      <h3 className="text-white text-2xl font-bold tracking-tight">{value}</h3>
      {trend && (
        <span className={`text-xs font-medium flex items-center ${trend === 'up' ? 'text-green-500' : 'text-red-500'}`}>
          {subValue}
        </span>
      )}
    </div>
    <p className="text-[#64748b] text-xs mt-1">{subLabel}</p>
  </div>
);

const StatsGrid = () => {
  const stats = [
    {
      title: "Uptime",
      value: "99.99%",
      subValue: "↑ 0.01%",
      subLabel: "Last downtime: 42 days ago",
      icon: CheckCircle,
      colorClass: "text-green-500",
      trend: "up"
    },
    {
      title: "Packet Loss",
      value: "0.01%",
      subValue: "Stable",
      subLabel: "Avg over 1h",
      icon: Activity,
      colorClass: "text-blue-500", // primary color
      trend: "up" // 파란색은 트렌드 색상 무시
    },
    {
      title: "Latency",
      value: "12ms",
      subValue: "↓ 2ms",
      subLabel: "Avg over 1h: 14ms",
      icon: Clock,
      colorClass: "text-orange-500",
      trend: "up" // 실제로는 down 화살표가 좋지만 일단 통일
    },
    {
      title: "Active Ports",
      value: "42/48",
      subValue: "",
      subLabel: "87% Utilization",
      icon: Network,
      colorClass: "text-purple-500",
      trend: ""
    }
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat, index) => (
        <StatCard key={index} {...stat} />
      ))}
    </div>
  );
};

export default StatsGrid;