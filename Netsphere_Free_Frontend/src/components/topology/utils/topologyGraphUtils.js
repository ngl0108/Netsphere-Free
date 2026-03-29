import { MarkerType } from 'reactflow';

const clamp01 = (x) => Math.max(0, Math.min(1, x));

const defaultFormatBps = (bps) => {
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

const defaultTruncateLabel = (text, maxLen) => {
  const s = String(text ?? '');
  const n = Number(maxLen ?? 42);
  if (!Number.isFinite(n) || n < 8) return s;
  if (s.length <= n) return s;
  return `${s.slice(0, Math.max(1, n - 3))}...`;
};

export const aggregateLinks = (links, pathResult, opts) => {
  const linkMap = new Map();
  const maxEdgeLabelLen = Number.isFinite(Number(opts?.maxEdgeLabelLen)) ? Number(opts.maxEdgeLabelLen) : 42;
  const pathBadgesEnabled = opts?.pathBadgesEnabled !== false;
  const labelTruncateMode = String(opts?.labelTruncateMode || 'all');
  const formatBps = typeof opts?.formatBps === 'function' ? opts.formatBps : defaultFormatBps;
  const truncateLabel = typeof opts?.truncateLabel === 'function' ? opts.truncateLabel : defaultTruncateLabel;

  const pathEdgeKeys = new Set();
  const pathEdgeDir = new Map();
  const pathMetaByLinkId = new Map();
  const pathMetaByPairProto = new Map();
  const hasStructuredSegments = Array.isArray(pathResult?.segments) && pathResult.segments.length > 0;
  if (hasStructuredSegments) {
    pathResult.segments.forEach((seg, idx) => {
      const fromId = String(seg?.from_id ?? pathResult?.path?.[idx]?.id ?? '');
      const toId = String(seg?.to_id ?? pathResult?.path?.[idx + 1]?.id ?? '');
      if (!fromId || !toId) return;
      const sorted = [fromId, toId].sort().join('-');
      const protocol = String(seg?.protocol || seg?.link?.protocol || '').trim().toUpperCase();
      const linkId = seg?.link?.id != null ? String(seg.link.id) : '';
      const meta = {
        fromId,
        toId,
        hopIndex: Number.isFinite(Number(seg?.hop)) ? Number(seg.hop) : idx,
        fromPort: seg?.from_port || pathResult?.path?.[idx]?.egress_intf || null,
        toPort: seg?.to_port || pathResult?.path?.[idx + 1]?.ingress_intf || null,
        protocol,
        linkId: linkId || null,
        status: String(seg?.status || seg?.link?.status || '').trim().toLowerCase(),
        layer: String(seg?.layer || seg?.link?.layer || '').trim().toLowerCase(),
      };
      if (meta.linkId) {
        pathMetaByLinkId.set(meta.linkId, meta);
      }
      if (protocol) {
        pathMetaByPairProto.set(`${sorted}-${protocol}`, meta);
      }
      if (!pathEdgeDir.has(sorted)) {
        pathEdgeDir.set(sorted, meta);
      }
      pathEdgeKeys.add(sorted);
    });
  } else if (pathResult?.path?.length > 1) {
    for (let i = 0; i < pathResult.path.length - 1; i++) {
      const fromId = String(pathResult.path[i].id);
      const toId = String(pathResult.path[i + 1].id);
      const sorted = [fromId, toId].sort().join('-');
      pathEdgeKeys.add(sorted);
      if (!pathEdgeDir.has(sorted)) {
        pathEdgeDir.set(sorted, {
          fromId,
          toId,
          hopIndex: i,
          fromPort: pathResult.path[i]?.egress_intf,
          toPort: pathResult.path[i + 1]?.ingress_intf
        });
      }
    }
  }

  const activeHopIndex = Number.isFinite(Number(opts?.pathPlayback?.activeEdgeIndex))
    ? Number(opts.pathPlayback.activeEdgeIndex)
    : null;

  links.forEach((link) => {
    const proto = (link.protocol || 'LLDP').toUpperCase();
    const sortedIds = [String(link.source), String(link.target)].sort();
    const key = `${sortedIds[0]}-${sortedIds[1]}-${proto}`;
    const sortedPairKey = `${sortedIds[0]}-${sortedIds[1]}`;
    const rawLinkId = link?.id != null ? String(link.id) : null;
    const exactPathMeta = (rawLinkId && pathMetaByLinkId.get(rawLinkId))
      || pathMetaByPairProto.get(`${sortedPairKey}-${proto}`)
      || (!hasStructuredSegments ? pathEdgeDir.get(sortedPairKey) : null)
      || null;
    const portInfo = `${link.src_port || '?'} -> ${link.dst_port || '?'}`;
    const degradedReason = (link.status === 'degraded' && link.reason) ? String(link.reason) : '';
    const linkConfidence = Number(link?.confidence ?? link?.evidence?.confidence ?? 0);
    const safeConfidence = Number.isFinite(linkConfidence) ? Math.max(0, Math.min(1, linkConfidence)) : 0;
    const linkEvidence = link?.evidence && typeof link.evidence === 'object' ? link.evidence : {};
    const sourceHint = String(link?.discovery_source || linkEvidence?.discovery_source || '').trim();
    const ageHint = Number(linkEvidence?.age_seconds);
    const staleHint = Boolean(linkEvidence?.is_stale) || (Number.isFinite(ageHint) && ageHint > 86400);

    let trafficFwd = 0;
    let trafficRev = 0;
    if (opts?.trafficFlowEnabled) {
      const t = link?.traffic;
      const f = Number(t?.fwd_bps || 0);
      const r = Number(t?.rev_bps || 0);
      if (Number.isFinite(f) || Number.isFinite(r)) {
        trafficFwd = Math.max(0, Number.isFinite(f) ? f : 0);
        trafficRev = Math.max(0, Number.isFinite(r) ? r : 0);
      } else if (opts?.nodeTrafficById) {
        const src = opts.nodeTrafficById.get(String(link.source)) || {};
        const dst = opts.nodeTrafficById.get(String(link.target)) || {};
        const srcIn = Number(src.in_bps || 0);
        const srcOut = Number(src.out_bps || 0);
        const dstIn = Number(dst.in_bps || 0);
        const dstOut = Number(dst.out_bps || 0);
        trafficFwd = Math.max(0, Math.min(srcOut, dstIn));
        trafficRev = Math.max(0, Math.min(dstOut, srcIn));
      }
    }

    if (!linkMap.has(key)) {
      linkMap.set(key, {
        source: String(link.source),
        target: String(link.target),
        count: 1,
        status: link.status,
        ports: [portInfo],
        reasons: degradedReason ? [degradedReason] : [],
        rawLink: link,
        protocol: proto,
        inPath: !!exactPathMeta || (!hasStructuredSegments && pathEdgeKeys.has(sortedPairKey)),
        pathMeta: exactPathMeta,
        traffic_fwd_bps: trafficFwd,
        traffic_rev_bps: trafficRev,
        confidence_sum: safeConfidence,
        confidence_count: 1,
        confidence_min: safeConfidence,
        confidence_max: safeConfidence,
        discovery_sources: sourceHint ? [sourceHint] : [],
        stale: staleHint,
        max_age_seconds: Number.isFinite(ageHint) ? Math.max(0, Math.round(ageHint)) : null,
      });
    } else {
      const existing = linkMap.get(key);
      existing.count += 1;
      existing.ports.push(portInfo);
      if (link.status === 'active' || link.status === 'up') {
        existing.status = 'active';
      } else if (existing.status !== 'active' && link.status === 'degraded') {
        existing.status = 'degraded';
      }
      if (degradedReason && !existing.reasons.includes(degradedReason)) {
        existing.reasons.push(degradedReason);
      }
      if (exactPathMeta) {
        existing.inPath = true;
        existing.pathMeta = exactPathMeta;
      } else if (!hasStructuredSegments && pathEdgeKeys.has(sortedPairKey)) {
        existing.inPath = true;
      }
      existing.traffic_fwd_bps += trafficFwd;
      existing.traffic_rev_bps += trafficRev;
      existing.confidence_sum += safeConfidence;
      existing.confidence_count += 1;
      existing.confidence_min = Math.min(Number(existing.confidence_min || 0), safeConfidence);
      existing.confidence_max = Math.max(Number(existing.confidence_max || 0), safeConfidence);
      if (sourceHint && !existing.discovery_sources.includes(sourceHint)) existing.discovery_sources.push(sourceHint);
      if (staleHint) existing.stale = true;
      if (Number.isFinite(ageHint)) {
        const age = Math.max(0, Math.round(ageHint));
        existing.max_age_seconds = Number(existing.max_age_seconds || 0) > 0
          ? Math.max(Number(existing.max_age_seconds), age)
          : age;
      }
    }
  });

  const aggregated = Array.from(linkMap.values());
  let maxTraffic = 0;
  if (opts?.trafficFlowEnabled) {
    for (const l of aggregated) {
      const total = Number(l.traffic_fwd_bps || 0) + Number(l.traffic_rev_bps || 0);
      if (total > maxTraffic) maxTraffic = total;
    }
  }

  return aggregated.map((l, idx) => {
    const isMultiLink = l.count > 1;
    const isOSPF = l.protocol === 'OSPF';
    const isBGP = l.protocol === 'BGP';
    const rawLayer = String(l?.rawLink?.layer || '').trim().toLowerCase();
    const isOverlay = rawLayer === 'overlay' || ['VXLAN', 'EVPN', 'NVE', 'OVERLAY'].includes(l.protocol);
    const isL3 = !isOverlay && (isOSPF || isBGP || rawLayer === 'l3');
    const hybridMeta = l?.rawLink?.hybrid && typeof l.rawLink.hybrid === 'object' ? l.rawLink.hybrid : null;
    const isHybrid = !!hybridMeta || l.protocol === 'CLOUD' || rawLayer === 'hybrid';
    const l3Meta = l?.rawLink?.l3 && typeof l.rawLink.l3 === 'object' ? l.rawLink.l3 : null;
    const overlayMeta = l?.rawLink?.overlay && typeof l.rawLink.overlay === 'object' ? l.rawLink.overlay : null;
    const bgpRelationship = String(l3Meta?.relationship || '').trim().toLowerCase();
    const bgpState = String(l3Meta?.state || '').trim().toLowerCase();
    const trafficTotal = Number(l.traffic_fwd_bps || 0) + Number(l.traffic_rev_bps || 0);
    const sortedPair = [String(l.source), String(l.target)].sort().join('-');
    const pathMeta = l.pathMeta || pathEdgeDir.get(sortedPair);
    const pathPhase = (pathMeta && activeHopIndex != null)
      ? (pathMeta.hopIndex < activeHopIndex ? 'done' : (pathMeta.hopIndex === activeHopIndex ? 'active' : 'pending'))
      : null;
    const pathStatus = String(pathMeta?.status || '').trim().toLowerCase();

    const confidence = Number(l.confidence_count || 0) > 0
      ? Number(l.confidence_sum || 0) / Number(l.confidence_count || 1)
      : 0;
    const confidenceText = Number.isFinite(confidence) ? confidence.toFixed(2) : '0.00';
    const quality = confidence >= 0.9 ? 'high' : (confidence >= 0.7 ? 'medium' : 'low');
    let edgeLabel = isMultiLink
      ? `${l.count} Links (LAG)`
      : l.rawLink.label || l.ports[0];

    if (isOverlay) {
      const transport = String(overlayMeta?.transport || '').trim().toUpperCase();
      const state = String(overlayMeta?.state || '').trim().toUpperCase();
      const vniCount = Number(overlayMeta?.vni_count || (Array.isArray(overlayMeta?.vnis) ? overlayMeta.vnis.length : 0));
      const parts = [];
      if (transport) parts.push(transport);
      if (Number.isFinite(vniCount) && vniCount > 0) parts.push(`${vniCount} VNI`);
      if (state) parts.push(state);
      edgeLabel = `[VXLAN] ${parts.join(' / ') || 'overlay'}`;
    } else if (isL3) {
      if (isBGP) {
        const srcAs = l3Meta?.source?.local_as;
        const dstAs = l3Meta?.target?.local_as;
        const relationship = String(l3Meta?.relationship || '').trim().toUpperCase();
        const state = String(l3Meta?.state || '').trim().toUpperCase();
        const parts = [];
        if (Number.isFinite(Number(srcAs)) && Number.isFinite(Number(dstAs))) {
          parts.push(`AS${srcAs}<->AS${dstAs}`);
        }
        if (relationship) parts.push(relationship);
        if (state) parts.push(state);
        edgeLabel = `[BGP] ${parts.join(' / ') || 'session'}`;
      } else if (isOSPF) {
        const state = String(l3Meta?.state || '').trim().toUpperCase();
        const area = String(l3Meta?.area || '').trim();
        const parts = [];
        if (state) parts.push(state);
        if (area) parts.push(`area ${area}`);
        edgeLabel = `[OSPF] ${parts.join(' / ') || 'adjacency'}`;
      } else {
        edgeLabel = `[${l.protocol}] ${l.rawLink.label || ''}`;
      }
    } else if (isHybrid) {
      const hybridKind = String(hybridMeta?.kind || '').trim().toLowerCase();
      const relation = String(hybridMeta?.relationship || '').trim().replace(/_/g, ' ');
      const provider = String(hybridMeta?.provider || '').trim().toUpperCase();
      const resource = String(hybridMeta?.resource_name || hybridMeta?.resource_id || '').trim();
      const parts = [];
      if (provider) parts.push(provider);
      if (relation) parts.push(relation);
      if (resource) parts.push(resource);
      edgeLabel = `[HYBRID] ${parts.join(' / ') || (hybridKind || 'link')}`;
    }

    let strokeColor = l.status === 'active' || l.status === 'up' ? '#3b82f6' : (l.status === 'degraded' ? '#f59e0b' : '#ef4444');
    let strokeWidth = isMultiLink ? 4 : 2;
    let animated = l.status === 'active' || l.status === 'up' || l.status === 'degraded';
    let zIndex = 0;
    let dashArray = undefined;
    let markerStart = undefined;
    let edgeSource = l.source;
    let edgeTarget = l.target;

    if (isOverlay) {
      const overlayState = String(overlayMeta?.state || '').trim().toLowerCase();
      if (overlayState && overlayState !== 'up') {
        strokeColor = '#f59e0b';
        dashArray = '6 4';
        strokeWidth = 3;
      } else {
        strokeColor = '#06b6d4';
        dashArray = '10 5';
        strokeWidth = 3;
      }
    } else if (isOSPF) {
      strokeColor = '#f97316';
      dashArray = '8 4';
      strokeWidth = 2.5;
    } else if (isBGP) {
      if (bgpState && bgpState !== 'established' && bgpState !== 'up') {
        strokeColor = '#f59e0b';
        dashArray = '6 4';
        strokeWidth = 3;
      } else if (bgpRelationship === 'ebgp') {
        strokeColor = '#d946ef';
        dashArray = undefined;
        strokeWidth = 3.25;
      } else if (bgpRelationship === 'ibgp') {
        strokeColor = '#8b5cf6';
        dashArray = '12 6';
        strokeWidth = 2.75;
      } else {
        strokeColor = '#a855f7';
        dashArray = '10 5';
        strokeWidth = 2.75;
      }
    } else if (isHybrid) {
      const hybridKind = String(hybridMeta?.kind || '').trim().toLowerCase();
      if (hybridKind === 'inventory' || l.protocol === 'CLOUD' || rawLayer === 'hybrid') {
        strokeColor = '#0ea5e9';
        dashArray = '12 6';
        strokeWidth = 2.75;
        animated = false;
      } else {
        strokeColor = l.status === 'degraded' ? '#f59e0b' : '#0284c7';
        dashArray = l.status === 'degraded' ? '6 4' : '10 5';
        strokeWidth = Math.max(strokeWidth, 3);
      }
    }

    if (l.inPath) {
      if (pathMeta) {
        edgeSource = pathMeta.fromId;
        edgeTarget = pathMeta.toId;
        edgeLabel = `#${pathMeta.hopIndex + 1} ${pathMeta.fromPort || '?'} -> ${pathMeta.toPort || '?'}`;

        if (pathBadgesEnabled) {
          const ev = pathResult?.path?.[pathMeta.hopIndex]?.evidence;
          const protocol = ev?.protocol ? String(ev.protocol).toUpperCase() : null;
          const vrf = ev?.vrf ? String(ev.vrf) : null;
          const badgeParts = [];
          if (protocol) badgeParts.push(protocol);
          if (vrf) badgeParts.push(`VRF:${vrf}`);
          if (badgeParts.length > 0) {
            edgeLabel = `[${badgeParts.join(' | ')}] ${edgeLabel}`;
          }
        }
      }

      if (pathPhase === 'active') {
        strokeColor = '#22c55e';
        strokeWidth = 6;
        animated = true;
        zIndex = 12;
        dashArray = undefined;
      } else if (pathPhase === 'done') {
        strokeColor = pathStatus === 'degraded' ? '#d97706' : '#16a34a';
        strokeWidth = 4;
        animated = false;
        zIndex = 11;
        dashArray = pathStatus === 'degraded' ? '8 4' : undefined;
      } else if (pathPhase === 'pending') {
        strokeColor = pathStatus === 'degraded' ? '#fcd34d' : '#bbf7d0';
        strokeWidth = 3;
        animated = false;
        zIndex = 10;
        dashArray = '6 6';
      } else {
        strokeColor = pathStatus === 'degraded' ? '#f59e0b' : '#10b981';
        strokeWidth = 4;
        animated = pathStatus !== 'degraded';
        zIndex = 10;
        dashArray = pathStatus === 'degraded' ? '8 4' : undefined;
      }
    } else if (pathResult) {
      strokeColor = '#e5e7eb';
      animated = false;
      dashArray = undefined;
    } else if (quality === 'low') {
      strokeColor = '#f59e0b';
      dashArray = '6 4';
      strokeWidth = Math.max(strokeWidth, 2.5);
    } else if (opts?.trafficFlowEnabled) {
      const heat = maxTraffic > 0 ? clamp01(trafficTotal / maxTraffic) : 0;
      const width = 2 + heat * 8;
      strokeWidth = isMultiLink ? Math.max(width, 4) : width;
      const hue = 200 - heat * 160;
      strokeColor = `hsl(${hue}, 85%, 55%)`;
      animated = trafficTotal > 0;
      if (Number(l.traffic_rev_bps || 0) > 0) {
        markerStart = { type: MarkerType.ArrowClosed, color: strokeColor };
      }
      if (!isL3 && !isOverlay && !isMultiLink) {
        edgeLabel = `${edgeLabel} | ${formatBps(trafficTotal)}`;
      }
    }

    if (!l.inPath && l.status === 'degraded') {
      const reasons = Array.isArray(l.reasons) ? l.reasons.filter(Boolean) : [];
      const reasonLabel = reasons.length > 0 ? reasons.join(',') : 'unknown';
      edgeLabel = `${edgeLabel} | DEG:${reasonLabel}`;
    }

    const fullLabel = edgeLabel;
    const shouldTruncate = labelTruncateMode === 'all' || (labelTruncateMode === 'path' && l.inPath);
    const displayLabel = shouldTruncate ? truncateLabel(fullLabel, maxEdgeLabelLen) : fullLabel;
    const evidenceLines = [
      `Protocol: ${String(l.protocol || '').toUpperCase() || 'UNKNOWN'}`,
      `Confidence: ${confidenceText} (${quality})`,
      `Source: ${(Array.isArray(l.discovery_sources) && l.discovery_sources.length > 0) ? l.discovery_sources.join(', ') : 'unknown'}`,
    ];
    if (isBGP && l3Meta) {
      if (l3Meta.relationship) evidenceLines.push(`BGP: ${String(l3Meta.relationship).toUpperCase()}`);
      if (l3Meta.state) evidenceLines.push(`Session: ${String(l3Meta.state).toUpperCase()}`);
      if (Number.isFinite(Number(l3Meta?.source?.local_as)) && Number.isFinite(Number(l3Meta?.target?.local_as))) {
        evidenceLines.push(`ASN: AS${l3Meta.source.local_as} <-> AS${l3Meta.target.local_as}`);
      }
      if (Number.isFinite(Number(l3Meta?.prefixes_received))) evidenceLines.push(`Prefixes: ${Number(l3Meta.prefixes_received)}`);
      if (l3Meta?.uptime) evidenceLines.push(`Uptime: ${String(l3Meta.uptime)}`);
    }
    if (isOSPF && l3Meta) {
      if (l3Meta.state) evidenceLines.push(`Adjacency: ${String(l3Meta.state).toUpperCase()}`);
      if (l3Meta.area) evidenceLines.push(`Area: ${String(l3Meta.area)}`);
      if (l3Meta?.source?.interface) evidenceLines.push(`Src IF: ${String(l3Meta.source.interface)}`);
      if (l3Meta?.target?.interface) evidenceLines.push(`Dst IF: ${String(l3Meta.target.interface)}`);
    }
    if (isOverlay && overlayMeta) {
      if (overlayMeta.transport) evidenceLines.push(`Overlay: ${String(overlayMeta.transport).toUpperCase().replace(/_/g, ' ')}`);
      if (overlayMeta.state) evidenceLines.push(`Tunnel: ${String(overlayMeta.state).toUpperCase()}`);
      const vtepA = String(overlayMeta?.source?.local_vtep_ip || '').trim();
      const vtepB = String(overlayMeta?.target?.local_vtep_ip || '').trim();
      if (vtepA || vtepB) evidenceLines.push(`VTEP: ${vtepA || '?'} <-> ${vtepB || '?'}`);
      const vniRows = Array.isArray(overlayMeta?.vnis) ? overlayMeta.vnis : [];
      if (vniRows.length > 0) {
        const vniText = vniRows.slice(0, 6).map((row) => `VNI${row?.vni}`).join(', ');
        evidenceLines.push(`VNIs: ${vniText}${vniRows.length > 6 ? ` +${vniRows.length - 6}` : ''}`);
      }
      if (overlayMeta?.evpn?.relationship) evidenceLines.push(`EVPN: ${String(overlayMeta.evpn.relationship).toUpperCase()}`);
    }
    if (isHybrid && hybridMeta) {
      if (hybridMeta.kind) evidenceLines.push(`Hybrid: ${String(hybridMeta.kind).replace(/_/g, ' ')}`);
      if (hybridMeta.relationship) evidenceLines.push(`Scope: ${String(hybridMeta.relationship).replace(/_/g, ' ')}`);
      if (hybridMeta.provider) evidenceLines.push(`Provider: ${String(hybridMeta.provider).toUpperCase()}`);
      if (hybridMeta.account_name || hybridMeta.account_id != null) {
        const accountPart = hybridMeta.account_name
          ? `${String(hybridMeta.account_name)}${hybridMeta.account_id != null ? ` (#${hybridMeta.account_id})` : ''}`
          : `#${String(hybridMeta.account_id)}`;
        evidenceLines.push(`Account: ${accountPart}`);
      }
      if (hybridMeta.region) evidenceLines.push(`Region: ${String(hybridMeta.region)}`);
      if (hybridMeta.resource_name || hybridMeta.resource_id) {
        evidenceLines.push(`Resource: ${String(hybridMeta.resource_name || hybridMeta.resource_id)}`);
      }
    }
    if (l.max_age_seconds != null) evidenceLines.push(`Age: ${Math.max(0, Number(l.max_age_seconds || 0))}s`);
    if (l.stale) evidenceLines.push('Freshness: stale (>24h)');
    const portDetails = (() => {
      const ports = Array.isArray(l.ports) ? l.ports : [];
      if (!l.inPath && l.status === 'degraded') {
        const reasons = Array.isArray(l.reasons) ? l.reasons.filter(Boolean) : [];
        const reasonLabel = reasons.length > 0 ? reasons.join(',') : 'unknown';
        return [...evidenceLines, `Reason: ${reasonLabel}`, ...ports];
      }
      return [...evidenceLines, ...ports];
    })();

    const protocolLabelColor = isOSPF
      ? '#ea580c'
      : isOverlay
        ? strokeColor
      : isHybrid
        ? strokeColor
      : isBGP
        ? strokeColor
        : '#4b5563';

    return {
      id: `e-${idx}-${l.source}-${l.target}-${l.protocol}`,
      source: edgeSource,
      target: edgeTarget,
      label: displayLabel,
      type: 'default',
      animated,
      data: {
        portDetails,
        tooltipLines: portDetails,
        isMulti: isMultiLink,
        protocol: l.protocol,
        status: l.status,
        layer: rawLayer || (isOverlay ? 'overlay' : (isL3 ? 'l3' : 'l2')),
        confidence,
        quality,
        stale: !!l.stale,
        discovery_source: Array.isArray(l.discovery_sources) ? l.discovery_sources.join(',') : '',
        l3: l3Meta,
        overlay: overlayMeta,
        hybrid: hybridMeta,
        path: pathMeta ? { hopIndex: pathMeta.hopIndex, fromPort: pathMeta.fromPort, toPort: pathMeta.toPort } : null,
        fullLabel,
        traffic: {
          total_bps: trafficTotal,
          fwd_bps: Number(l.traffic_fwd_bps || 0),
          rev_bps: Number(l.traffic_rev_bps || 0)
        }
      },
      style: {
        stroke: strokeColor,
        strokeWidth,
        strokeDasharray: dashArray,
        cursor: 'pointer',
        opacity: (pathResult && !l.inPath) ? 0.25 : 1
      },
      labelStyle: {
        fill: (pathResult && !l.inPath) ? '#9ca3af' : (l.inPath ? '#065f46' : protocolLabelColor),
        fontWeight: isMultiLink || isL3 || isOverlay ? 800 : 500,
        fontSize: 11,
        opacity: (pathResult && !l.inPath) ? 0.5 : 1
      },
      markerEnd: l.inPath ? { type: MarkerType.ArrowClosed, color: strokeColor } : {
        type: MarkerType.ArrowClosed,
        color: strokeColor
      },
      markerStart,
      zIndex
    };
  });
};
