import React from 'react';
import { Shield, Wifi, Box, Layers, Globe } from 'lucide-react';

export const formatBps = (bps) => {
  const v = Number(bps || 0);
  if (!Number.isFinite(v) || v <= 0) return '0 bps';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let n = v;
  let i = 0;
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000;
    i += 1;
  }
  const fixed = n >= 100 ? 0 : n >= 10 ? 1 : 2;
  return `${n.toFixed(fixed)} ${units[i]}`;
};

export const truncateLabel = (text, maxLen) => {
  const s = String(text ?? '');
  const n = Number(maxLen ?? 42);
  if (!Number.isFinite(n) || n < 8) return s;
  if (s.length <= n) return s;
  return `${s.slice(0, Math.max(1, n - 3))}...`;
};

export const buildEvidenceParts = (node) => {
  const evidence = node?.evidence && typeof node.evidence === 'object' ? node.evidence : {};
  const summary = [];
  const details = [];

  if (evidence.type === 'route_lookup') {
    if (evidence.protocol) summary.push(String(evidence.protocol).toUpperCase());
    if (evidence.vrf) summary.push(`VRF:${evidence.vrf}`);
    if (evidence.next_hop_ip) summary.push(`NH:${evidence.next_hop_ip}`);
    if (evidence.outgoing_interface) summary.push(`OUT:${evidence.outgoing_interface}`);

    if (evidence.protocol) details.push(`Routing Protocol: ${String(evidence.protocol).toUpperCase()}`);
    if (evidence.vrf) details.push(`VRF: ${evidence.vrf}`);
    if (evidence.next_hop_ip) details.push(`Next-hop IP: ${evidence.next_hop_ip}`);
    if (evidence.outgoing_interface) details.push(`Outgoing IF: ${evidence.outgoing_interface}`);
    if (evidence.arp && typeof evidence.arp === 'object') {
      if (evidence.arp.ip) details.push(`ARP IP: ${evidence.arp.ip}`);
      if (evidence.arp.mac) details.push(`ARP MAC: ${evidence.arp.mac}`);
      if (evidence.arp.interface) details.push(`ARP IF: ${evidence.arp.interface}`);
    }
    if (evidence.mac && typeof evidence.mac === 'object') {
      if (evidence.mac.mac) details.push(`MAC: ${evidence.mac.mac}`);
      if (evidence.mac.port) details.push(`MAC Port: ${evidence.mac.port}`);
      if (evidence.mac.vlan) details.push(`MAC VLAN: ${evidence.mac.vlan}`);
    }
  }

  if (evidence.type === 'l2_mac_trace') {
    if (evidence.learned_port) summary.push(`MAC:${evidence.learned_port}`);
    if (evidence.mac) summary.push(String(evidence.mac).toLowerCase());
    if (evidence.mac) details.push(`MAC: ${String(evidence.mac).toLowerCase()}`);
    if (evidence.learned_port) details.push(`Learned Port: ${evidence.learned_port}`);
  }

  if (evidence.l2_extend && typeof evidence.l2_extend === 'object') {
    if (evidence.l2_extend.host_ip) summary.push(`HOST:${evidence.l2_extend.host_ip}`);
    if (evidence.l2_extend.first_port) summary.push(`PORT:${evidence.l2_extend.first_port}`);
    if (evidence.l2_extend.host_ip) details.push(`Host IP: ${evidence.l2_extend.host_ip}`);
    if (evidence.l2_extend.first_port) details.push(`First Port: ${evidence.l2_extend.first_port}`);
  }

  if (evidence.type === 'cloud_peer') {
    if (evidence.provider) summary.push(String(evidence.provider).toUpperCase());
    if (evidence.asn) summary.push(`AS${evidence.asn}`);
    if (evidence.org_name) summary.push(truncateLabel(String(evidence.org_name), 32));
    if (evidence.provider) details.push(`Provider: ${String(evidence.provider).toUpperCase()}`);
    if (evidence.asn) details.push(`ASN: AS${evidence.asn}`);
    if (evidence.as_name) details.push(`AS Name: ${evidence.as_name}`);
    if (evidence.org_name) details.push(`Org: ${evidence.org_name}`);
    if (evidence.source) details.push(`Source: ${evidence.source}`);
    if (evidence.region) details.push(`Region: ${evidence.region}`);
  }

  return {
    summaryText: summary.join(' | '),
    detailLines: details,
  };
};

export const getIconByRole = (role) => {
  switch (role) {
    case 'core': return <Globe size={20} />;
    case 'distribution': return <Layers size={20} />;
    case 'security': return <Shield size={20} />;
    case 'cloud': return <Box size={20} />;
    case 'wlc': return <Wifi size={20} />;
    case 'access_point': return <Wifi size={16} className="opacity-70" />;
    case 'endpoint': return <Box size={16} className="opacity-70" />;
    case 'endpoint_group': return <Layers size={16} className="opacity-70" />;
    case 'access_domestic': return <Box size={20} />;
    default: return <Box size={20} />;
  }
};
