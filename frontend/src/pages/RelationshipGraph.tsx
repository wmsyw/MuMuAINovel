import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, Tag, Button, Space, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import axios from 'axios';
import dagre from 'dagre';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  MarkerType,
} from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// 使用 dagre 进行自动布局
const getLayoutedElements = (nodes: Node[], edges: Edge[]) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 140, height: 60 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 70,
        y: nodeWithPosition.y - 30,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

interface GraphNode {
  id: string;
  name: string;
  type: string;
  role_type: string;
  avatar: string | null;
}

interface GraphLink {
  source: string;
  target: string;
  relationship: string;
  intimacy: number;
  status: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface RelationshipType {
  id: number;
  name: string;
  category: string;
  reverse_name: string;
  intimacy_range: string;
  icon: string;
  description: string;
  created_at: string;
}

interface CharacterDetail {
  id: string;
  project_id: string;
  name: string;
  age: string;
  gender: string;
  is_organization: boolean;
  role_type: string;
  personality: string;
  background: string;
  appearance: string;
  organization_type: string;
  organization_purpose: string;
  organization_members: string;
  traits: string;
  avatar_url: string;
  power_level: number;
  location: string;
  motto: string;
  color: string;
}

export default function RelationshipGraph() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [, setGraphData] = useState<GraphData | null>(null);
  const [, setLoading] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<CharacterDetail | null>(null);
  const [, setDetailLoading] = useState(false);
  const [relationshipTypes, setRelationshipTypes] = useState<RelationshipType[]>([]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (projectId) {
      loadRelationshipTypes();
    }
  }, [projectId]);

  const loadRelationshipTypes = async () => {
    try {
      const res = await axios.get('/api/relationships/types');
      setRelationshipTypes(res.data || []);
    } catch (error) {
      console.error('加载关系类型失败', error);
    }
  };

  // 根据关系名称获取分类颜色
  const getCategoryColor = useCallback((relationshipName: string, isActive: boolean) => {
    // 找到对应的关系类型
    const relType = relationshipTypes.find(rt => rt.name === relationshipName);
    const category = relType?.category || 'default';

    // 分类颜色映射 - 重新设计更符合语义
    const categoryColors: Record<string, { active: string; inactive: string }> = {
      family: { active: '#f39c12', inactive: '#fcd59e' },      // 家族关系 - 橙黄色(温馨)
      hostile: { active: '#e74c3c', inactive: '#f5a49a' },     // 敌对关系 - 红色
      professional: { active: '#3498db', inactive: '#a9d4ed' }, // 职业关系 - 蓝色(专业)
      social: { active: '#27ae60', inactive: '#a3d9b5' },      // 社交关系 - 绿色(友好)
      default: { active: '#95a5a6', inactive: '#c8d0d2' },     // 默认 - 灰色
    };

    const colors = categoryColors[category] || categoryColors.default;
    return isActive ? colors.active : colors.inactive;
  }, [relationshipTypes]);

  const loadGraphData = useCallback(async () => {
    if (!projectId || relationshipTypes.length === 0) return;
    setLoading(true);
    try {
      const res = await axios.get(`/api/relationships/graph/${projectId}`);
      const data = res.data as GraphData;

      const getNodeColors = (type: string, roleType: string) => {
        // 节点颜色 - 重新设计更清晰
        if (type === 'character') {
          if (roleType === 'protagonist') return { border: '#e74c3c', bg: '#e74c3c' };    // 主角 - 红色
          if (roleType === 'antagonist') return { border: '#9b59b6', bg: '#9b59b6' };    // 反派 - 紫色
          return { border: '#3498db', bg: '#3498db' };                                     // 配角 - 蓝色
        }
        return { border: '#27ae60', bg: '#27ae60' };                                        // 组织 - 绿色
      };

      const flowNodes: Node[] = data.nodes.map((node) => {
        const colors = getNodeColors(node.type, node.role_type);
        return {
          id: node.id,
          type: 'default',
          position: { x: 0, y: 0 },
          data: {
            label: node.name,
            type: node.type,
            role_type: node.role_type,
          },
          style: {
            border: `2px solid ${colors.border}`,
            borderRadius: 8,
            backgroundColor: `${colors.bg}33`,
            padding: '10px 15px',
            minWidth: 100,
          },
        };
      });

      const flowEdges: Edge[] = data.links.map(link => {
        const edgeColor = getCategoryColor(link.relationship, link.status === 'active');
        return {
          id: `${link.source}-${link.target}`,
          source: link.source,
          target: link.target,
          label: link.relationship,
          type: 'smoothstep',
          style: {
            stroke: edgeColor,
            strokeWidth: 2,
          },
          labelStyle: {
            fill: '#666',
            fontSize: 10,
          },
          labelBgStyle: {
            fill: '#fff',
            fillOpacity: 0.9,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edgeColor,
          },
          data: {
            intimacy: link.intimacy,
            status: link.status,
            category: relationshipTypes.find(rt => rt.name === link.relationship)?.category || 'social',
          },
        };
      });

      // 使用 dagre 进行自动布局
      const layouted = getLayoutedElements(flowNodes, flowEdges);
      setNodes(layouted.nodes);
      setEdges(layouted.edges);
      setGraphData(data);
    } catch (error) {
      message.error('加载关系图谱失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [projectId, relationshipTypes, getCategoryColor, setNodes, setEdges]);

  // 当 relationshipTypes 加载完成后再加载图数据
  useEffect(() => {
    void loadGraphData();
  }, [loadGraphData]);

  const loadNodeDetail = async (nodeId: string) => {
    if (!projectId) return;
    setDetailLoading(true);
    try {
      const res = await axios.get(`/api/characters?project_id=${projectId}`);
      const characters = res.data.items || [];
      const character = characters.find((c: CharacterDetail) => c.id === nodeId);
      if (character) {
        setNodeDetail(character);
      } else {
        message.error('未找到该角色详细信息');
      }
    } catch (error) {
      message.error('加载角色详情失败');
      console.error(error);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleNodeClick = (_: unknown, node: { id: string }) => {
    setSelectedNodeId(node.id);
    loadNodeDetail(node.id);
  };

  const handleCloseDetail = () => {
    setSelectedNodeId(null);
    setNodeDetail(null);
  };

  const goBack = () => {
    if (projectId) {
      navigate(`/project/${projectId}/relationships`);
      return;
    }
    navigate('/projects');
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#f5f5f5' }}>
      <Card
        size="small"
        title={
          <Space>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={goBack}
            >
              返回
            </Button>
            <span>关系图谱</span>
          </Space>
        }
        extra={
          <Space>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12 }}>
              {/* 节点颜色图例 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#e74c3c', fontWeight: 'bold' }}>●</span>
                <span>主角</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#9b59b6', fontWeight: 'bold' }}>●</span>
                <span>反派</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#3498db', fontWeight: 'bold' }}>●</span>
                <span>配角</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#27ae60', fontWeight: 'bold' }}>●</span>
                <span>组织</span>
              </div>
              <span style={{ color: '#d9d9d9' }}>|</span>
              {/* 连线颜色图例 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#f39c12', fontWeight: 'bold' }}>—</span>
                <span>家族</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#e74c3c', fontWeight: 'bold' }}>—</span>
                <span>敌对</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#3498db', fontWeight: 'bold' }}>—</span>
                <span>职业</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#27ae60', fontWeight: 'bold' }}>—</span>
                <span>社交</span>
              </div>
            </div>
          </Space>
        }
      >
        <div style={{ height: 'calc(100vh - 80px)' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            attributionPosition="bottom-left"
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls position="top-left" />
          </ReactFlow>
        </div>
      </Card>

      {/* 节点详情 */}
      {selectedNodeId && nodeDetail && (
        <div style={{
          position: 'fixed',
          right: 20,
          top: 80,
          width: 320,
          maxHeight: 'calc(100vh - 120px)',
          overflow: 'auto',
          backgroundColor: '#fff',
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
          padding: 16,
          zIndex: 1000,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>{nodeDetail.is_organization ? '组织详情' : '角色详情'}</h3>
            <Button type="text" size="small" onClick={handleCloseDetail}>×</Button>
          </div>

          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            {nodeDetail.avatar_url ? (
              <img
                src={nodeDetail.avatar_url}
                alt={nodeDetail.name}
                style={{ width: 60, height: 60, borderRadius: '50%', objectFit: 'cover' }}
              />
            ) : (
              <div style={{
                width: 60,
                height: 60,
                borderRadius: '50%',
                backgroundColor: nodeDetail.color || '#1890ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto',
                fontSize: 24,
                color: '#fff'
              }}>
                {nodeDetail.is_organization ? '🏛️' : '👤'}
              </div>
            )}
            <h4 style={{ marginTop: 8, marginBottom: 4 }}>{nodeDetail.name}</h4>
            <Space size="small" wrap>
              <Tag color={nodeDetail.is_organization ? 'green' : 'blue'}>
                {nodeDetail.is_organization ? '组织' : '角色'}
              </Tag>
              <Tag color={
                nodeDetail.role_type === 'protagonist' ? 'red' :
                nodeDetail.role_type === 'antagonist' ? 'orange' : 'blue'
              }>
                {nodeDetail.role_type === 'protagonist' ? '主角' :
                 nodeDetail.role_type === 'antagonist' ? '反派' : '配角'}
              </Tag>
              {nodeDetail.gender && <Tag>{nodeDetail.gender}</Tag>}
              {nodeDetail.age && <Tag>{nodeDetail.age}岁</Tag>}
            </Space>
          </div>

          {!nodeDetail.is_organization ? (
            <>
              {nodeDetail.appearance && (
                <div style={{ marginBottom: 8 }}>
                  <strong>外貌特征：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.appearance}</p>
                </div>
              )}
              {nodeDetail.personality && (
                <div style={{ marginBottom: 8 }}>
                  <strong>性格特点：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.personality}</p>
                </div>
              )}
              {nodeDetail.background && (
                <div style={{ marginBottom: 8 }}>
                  <strong>背景故事：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.background}</p>
                </div>
              )}
              {nodeDetail.traits && (
                <div>
                  <strong>特征标签：</strong>
                  <div style={{ marginTop: 4 }}>
                    {JSON.parse(nodeDetail.traits).map((trait: string, index: number) => (
                      <Tag key={index} color="blue">{trait}</Tag>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {nodeDetail.organization_type && (
                <div style={{ marginBottom: 8 }}>
                  <strong>组织类型：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.organization_type}</p>
                </div>
              )}
              {nodeDetail.organization_purpose && (
                <div style={{ marginBottom: 8 }}>
                  <strong>组织目的：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.organization_purpose}</p>
                </div>
              )}
              {nodeDetail.location && (
                <div style={{ marginBottom: 8 }}>
                  <strong>所在地：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.location}</p>
                </div>
              )}
              {nodeDetail.motto && (
                <div style={{ marginBottom: 8 }}>
                  <strong>组织格言：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.motto}</p>
                </div>
              )}
              {nodeDetail.power_level !== undefined && (
                <div style={{ marginBottom: 8 }}>
                  <strong>势力等级：</strong>
                  <p style={{ margin: '4px 0', color: '#666', fontSize: 13 }}>{nodeDetail.power_level}/100</p>
                </div>
              )}
              {nodeDetail.organization_members && (
                <div>
                  <strong>组织成员：</strong>
                  <div style={{ marginTop: 4 }}>
                    {JSON.parse(nodeDetail.organization_members).map((member: string, index: number) => (
                      <Tag key={index} color="green">{member}</Tag>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
