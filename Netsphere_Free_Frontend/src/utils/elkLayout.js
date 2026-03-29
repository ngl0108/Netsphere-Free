let elkInstancePromise = null;

const createElkInstance = async () => {
    const [apiMod, workerUrlMod] = await Promise.all([
        import('elkjs/lib/elk-api.js'),
        import('elkjs/lib/elk-worker.min.js?url'),
    ]);

    const ELK = apiMod?.default || apiMod;
    const workerUrl = workerUrlMod?.default || workerUrlMod;
    return new ELK({ workerUrl });
};

const getElkInstance = async () => {
    if (!elkInstancePromise) {
        elkInstancePromise = createElkInstance().catch((err) => {
            elkInstancePromise = null;
            throw err;
        });
    }
    return elkInstancePromise;
};

const elkOptions = {
    'elk.algorithm': 'layered',
    'elk.direction': 'DOWN',
    'elk.padding': '[top=100,left=80,bottom=80,right=80]',
    'elk.spacing.nodeNode': '150',
    'elk.layered.spacing.nodeNodeBetweenLayers': '250',
    'elk.hierarchyHandling': 'INCLUDE_CHILDREN', // Enable grouping
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
};

/**
 * Calculates layout for nodes and edges using ELK.js
 * @param {Array} nodes React Flow nodes (including group nodes)
 * @param {Array} edges React Flow edges
 * @param {Object} options Additional layout options
 * @returns {Promise<{nodes: Array, edges: Array}>} Layouted elements
 */
export const getElkLayoutedElements = async (nodes, edges, options = {}) => {
    const isHorizontal = options?.direction === 'RIGHT';
    const elk = await getElkInstance();

    // 1. Build ELK Graph Structure
    // We need to nest child nodes under their parent (group) nodes

    const graph = {
        id: 'root',
        layoutOptions: {
            ...elkOptions,
            'elk.direction': isHorizontal ? 'RIGHT' : 'DOWN',
        },
        children: [],
        edges: edges.map((edge) => ({
            id: edge.id,
            sources: [edge.source],
            targets: [edge.target],
        })),
    };

    // Map to store graph nodes by ID for easy lookup
    const nodeMap = {};

    // First pass: Create ELK node objects
    nodes.forEach((node) => {
        const elkNode = {
            id: node.id,
            width: node.width || 180,  // Default width if not rendered yet
            height: node.height || 80, // Default height
            // Only set labels for non-group nodes to avoid layout issues text measurement
            // labels: [{ text: node.data?.label || '' }], 
            children: [],
        };

        nodeMap[node.id] = elkNode;
    });

    // Second pass: Build hierarchy
    nodes.forEach((node) => {
        const elkNode = nodeMap[node.id];

        if (node.parentNode && nodeMap[node.parentNode]) {
            // It's a child node, add to parent's children array
            nodeMap[node.parentNode].children.push(elkNode);
        } else {
            // It's a top-level node (or group node itself)
            graph.children.push(elkNode);
        }
    });

    try {
        // 2. Run Layout Algorithm
        const layoutedGraph = await elk.layout(graph);

        // 3. Flatten graph back to React Flow nodes with absolute positions
        const layoutedNodes = [];

        const processNode = (elkNode, parentX = 0, parentY = 0) => {
            // Find original React Flow node to preserve data
            const originalNode = nodes.find((n) => n.id === elkNode.id);

            if (originalNode) {
                layoutedNodes.push({
                    ...originalNode,
                    position: {
                        x: elkNode.x,
                        y: elkNode.y,
                    },
                    style: {
                        ...originalNode.style,
                        width: elkNode.width,
                        height: elkNode.height,
                    },
                });
            }

            // Process children recursively
            // Note: ELK returns relative coordinates for children
            if (elkNode.children && elkNode.children.length > 0) {
                elkNode.children.forEach((child) => processNode(child, 0, 0));
            }
        };

        layoutedGraph.children.forEach((node) => processNode(node));

        return {
            nodes: layoutedNodes,
            edges: edges, // Edges don't need modification for React Flow usually, unless using complex routing points
        };

    } catch (error) {
        console.error('ELK Layout Error:', error);
        return { nodes, edges }; // Fallback to original positions
    }
};
