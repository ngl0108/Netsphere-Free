import React from 'react';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import GroupNode from '../GroupNode';

const nodeTypes = { groupNode: GroupNode };

const GraphCanvas = ({ 
  nodes, 
  edges, 
  onNodesChange, 
  onEdgesChange, 
  onNodeClick, 
  onEdgeClick, 
  onPaneClick,
  onInit
}) => {
  return (
    <div className="flex-1 h-full relative bg-gray-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        onInit={onInit}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.1}
        maxZoom={4}
        defaultEdgeOptions={{ type: 'default', animated: true }}
      >
        <Background color="#ccc" gap={16} />
        <Controls />
        <MiniMap 
          nodeColor={(n) => {
            if (n.type === 'groupNode') return '#e2e8f0';
            return '#3b82f6';
          }}
          maskColor="rgba(240, 240, 240, 0.6)"
        />
      </ReactFlow>
    </div>
  );
};

export default GraphCanvas;
