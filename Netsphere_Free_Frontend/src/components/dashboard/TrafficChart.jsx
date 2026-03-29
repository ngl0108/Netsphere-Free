import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity } from 'lucide-react';

const TrafficChart = ({ data }) => {
  const chartData = data && data.length > 0 ? data : [];

  return (
    <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 rounded-2xl p-6 min-h-[350px] flex flex-col shadow-sm relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>

      {/* Chart Header */}
      <div className="flex justify-between items-center mb-6 relative z-10">
        <h3 className="text-gray-700 dark:text-gray-200 font-bold text-sm uppercase tracking-wider flex items-center gap-2">
          <Activity className="text-primary" size={18} />
          Network Traffic
        </h3>
        <div className="flex gap-4 text-xs font-mono">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
            <span className="w-2 h-2 rounded-full bg-primary"></span> Inbound
          </div>
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
            <span className="w-2 h-2 rounded-full bg-indigo-500"></span> Outbound
          </div>
        </div>
      </div>

      {/* Chart Area */}
      <div className="flex-1 w-full min-h-0 relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorIn" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorOut" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.2)" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tick={{ fill: '#94a3b8' }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tick={{ fill: '#94a3b8' }}
              width={30}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                borderColor: 'rgba(255,255,255,0.1)',
                color: '#fff',
                borderRadius: '12px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                backdropFilter: 'blur(8px)'
              }}
              itemStyle={{ fontSize: '12px', fontWeight: '500' }}
              labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
            />
            <Area
              type="monotone"
              dataKey="in"
              stroke="#3b82f6"
              strokeWidth={3}
              fillOpacity={1}
              fill="url(#colorIn)"
              animationDuration={1000}
              filter="drop-shadow(0 0 6px rgba(59, 130, 246, 0.5))"
            />
            <Area
              type="monotone"
              dataKey="out"
              stroke="#6366f1"
              strokeWidth={3}
              fillOpacity={1}
              fill="url(#colorOut)"
              animationDuration={1000}
              filter="drop-shadow(0 0 6px rgba(99, 102, 241, 0.5))"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TrafficChart;
