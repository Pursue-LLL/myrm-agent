/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/peerCognition::listPeerIdentities, getPersonaCard, registerPeerIdentity, addRelationEdge, updatePersonaCard, recordInteractionEvent, getEdgesForPeer, generatePromptProjection
 * ../command-center/PeerCognitionStudioCard::PeerCognitionStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Peer-Centric Entity Graph & Agent Persona Card Studio Card (Item 110 P0):
 * 1. Default render of card header, 4-dimension HUD telemetry bar, and graph view
 * 2. Peer filtering and cognitive relationship edges display
 * 3. Tab switching to Persona Card Studio, preference mutation, and interaction evolution
 * 4. Prompt context projection compilation and token cost estimation
 * 5. New peer registration form flow
 *
 * [POS]
 * Unit test for Item 110.
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PeerCognitionStudioCard } from '../command-center/PeerCognitionStudioCard';
import {
  FALLBACK_CARDS,
  FALLBACK_EDGES,
  FALLBACK_PEERS,
  FALLBACK_PROJECTION,
} from '../command-center/peerCognitionFallbacks';

const {
  mockListPeerIdentities,
  mockGetPersonaCard,
  mockRegisterPeerIdentity,
  mockAddRelationEdge,
  mockUpdatePersonaCard,
  mockRecordInteractionEvent,
  mockGetEdgesForPeer,
  mockGeneratePromptProjection,
} = vi.hoisted(() => ({
  mockListPeerIdentities: vi.fn(),
  mockGetPersonaCard: vi.fn(),
  mockRegisterPeerIdentity: vi.fn(),
  mockAddRelationEdge: vi.fn(),
  mockUpdatePersonaCard: vi.fn(),
  mockRecordInteractionEvent: vi.fn(),
  mockGetEdgesForPeer: vi.fn(),
  mockGeneratePromptProjection: vi.fn(),
}));

vi.mock('@/services/memory/peerCognition', () => ({
  listPeerIdentities: mockListPeerIdentities,
  getPersonaCard: mockGetPersonaCard,
  registerPeerIdentity: mockRegisterPeerIdentity,
  addRelationEdge: mockAddRelationEdge,
  updatePersonaCard: mockUpdatePersonaCard,
  recordInteractionEvent: mockRecordInteractionEvent,
  getEdgesForPeer: mockGetEdgesForPeer,
  generatePromptProjection: mockGeneratePromptProjection,
}));

describe('PeerCognitionStudioCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListPeerIdentities.mockResolvedValue(FALLBACK_PEERS);
    mockGetPersonaCard.mockImplementation((peerId: string) =>
      Promise.resolve(FALLBACK_CARDS[peerId] || FALLBACK_CARDS.user_alice),
    );
    mockGetEdgesForPeer.mockResolvedValue(FALLBACK_EDGES);
    mockGeneratePromptProjection.mockResolvedValue(FALLBACK_PROJECTION);
    mockRecordInteractionEvent.mockResolvedValue({
      ...FALLBACK_CARDS.user_alice,
      interaction_count: 87,
      trust_score: 1.0,
    });
    mockRegisterPeerIdentity.mockResolvedValue({
      peer_id: 'user_david',
      peer_type: 'user_peer',
      display_name: 'David Chen',
      role_title: '前端架构师',
      avatar_or_icon: 'user',
      created_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    });
  });

  it('renders card header, HUD bar metrics, and entity graph explorer by default', async () => {
    render(<PeerCognitionStudioCard />);

    // Header & Badges
    expect(screen.getByText('社会认知实体图谱与常驻画像卡中枢')).toBeInTheDocument();
    expect(screen.getByText('Item 110 · P0')).toBeInTheDocument();
    expect(screen.getByText('对标 Hermes+Honcho · 参与者社会认知')).toBeInTheDocument();

    // 4 HUD metrics
    await waitFor(() => {
      expect(screen.getByText('常驻参与者 Peer')).toBeInTheDocument();
    });
    expect(screen.getByText('社会认知关联拓扑')).toBeInTheDocument();
    expect(screen.getByText('自演化交互反馈')).toBeInTheDocument();
    expect(screen.getByText('Prompt 上下文投影')).toBeInTheDocument();

    // Graph explorer default elements
    expect(screen.getByText('参与者实体库 (4)')).toBeInTheDocument();
    expect(screen.getByText('当前社会认知拓扑边 (4)')).toBeInTheDocument();
    expect(screen.getAllByText('Alice Liu').length).toBeGreaterThan(0);
    expect(screen.getByText('CoderAgent')).toBeInTheDocument();
  });

  it('filters peer entities by type and displays cognitive relation edges', async () => {
    render(<PeerCognitionStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Alice Liu').length).toBeGreaterThan(0);
    });

    // 筛选仅智能体
    const agentFilterBtn = screen.getByRole('button', { name: '智能体' });
    fireEvent.click(agentFilterBtn);

    expect(screen.getByText('CoderAgent')).toBeInTheDocument();
    expect(screen.queryByText('@user_alice')).not.toBeInTheDocument();

    // 校验关系边
    expect(screen.getAllByText('fact_pure_refactor_no_backcompat').length).toBeGreaterThan(0);
    expect(screen.getByText('asserts')).toBeInTheDocument();
  });

  it('switches to persona card studio and records simulated interaction outcome', async () => {
    render(<PeerCognitionStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Alice Liu').length).toBeGreaterThan(0);
    });

    // 切换至常驻画像卡 Tab
    const personaTabBtn = screen.getByRole('button', { name: '切换至常驻画像卡管理' });
    fireEvent.click(personaTabBtn);

    // 校验 Alice Liu 的画像卡内容
    expect(screen.getByText('明确职责边界 (Role Alignment)')).toBeInTheDocument();
    expect(screen.getByText('决策风格与容差偏好')).toBeInTheDocument();
    expect(screen.getByText('常驻偏好字典 (Standing Preferences)')).toBeInTheDocument();

    // 模拟协作成功交互
    const successBtn = screen.getByRole('button', { name: /协作成功/ });
    fireEvent.click(successBtn);

    await waitFor(() => {
      expect(mockRecordInteractionEvent).toHaveBeenCalledTimes(1);
    });
  });

  it('generates prompt context projection and estimates token cost', async () => {
    render(<PeerCognitionStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Alice Liu').length).toBeGreaterThan(0);
    });

    // 切换至常驻画像卡 Tab
    const personaTabBtn = screen.getByRole('button', { name: '切换至常驻画像卡管理' });
    fireEvent.click(personaTabBtn);

    // 点击生成低 Token 投影
    const projectBtn = screen.getByRole('button', { name: /生成低Token上下文投影/ });
    fireEvent.click(projectBtn);

    await waitFor(() => {
      expect(mockGeneratePromptProjection).toHaveBeenCalledTimes(1);
    });

    // 校验投影预览渲染
    expect(screen.getAllByText(/~78 Tokens/).length).toBeGreaterThan(0);
    expect(screen.getByText(/当前协作参与者社会认知对齐/)).toBeInTheDocument();
  });

  it('switches to register tab and submits new peer registration', async () => {
    render(<PeerCognitionStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Alice Liu').length).toBeGreaterThan(0);
    });

    // 切换至登记新参与者 Tab
    const registerTabBtn = screen.getByRole('button', { name: '切换至登记新参与者' });
    fireEvent.click(registerTabBtn);

    expect(screen.getByText('登记新参与者 Peer 实体 (进入社会认知图谱)')).toBeInTheDocument();

    // 填写新用户表单
    const idInput = screen.getByLabelText(/参与者唯一标识/);
    const nameInput = screen.getByLabelText(/显示名称/);
    const roleInput = screen.getByLabelText(/职能职责/);

    fireEvent.change(idInput, { target: { value: 'user_david' } });
    fireEvent.change(nameInput, { target: { value: 'David Chen' } });
    fireEvent.change(roleInput, { target: { value: '前端架构师' } });

    // 提交登记
    const submitBtn = screen.getByRole('button', { name: /确认登记并初始化画像卡/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRegisterPeerIdentity).toHaveBeenCalledTimes(1);
    });
  });
});
