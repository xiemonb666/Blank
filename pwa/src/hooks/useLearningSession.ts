import { useMemo, useState } from "react";
import { defaultNodeProfile } from "../app/sessionState";
import type {
  KnowledgeNode,
  MemoryEntry,
  Message,
  NodeLearningProfile,
  Persona,
} from "../types";

interface UseLearningSessionOptions {
  initialPersona: Persona;
  initialSessionId: string | null;
  initialMaterialTitle: string;
  initialNodes: KnowledgeNode[];
  initialActiveNodeId: string;
  initialMessageThreads: Record<string, Message[]>;
  initialMessageCountsByNodeId: Record<string, number>;
  initialDraftsByNodeId?: Record<string, string>;
  initialMemories?: MemoryEntry[];
  initialNodeProfiles: Record<string, NodeLearningProfile>;
}

function useLearningSession({
  initialPersona,
  initialSessionId,
  initialMaterialTitle,
  initialNodes,
  initialActiveNodeId,
  initialMessageThreads,
  initialMessageCountsByNodeId,
  initialDraftsByNodeId = {},
  initialMemories = [],
  initialNodeProfiles,
}: UseLearningSessionOptions) {
  const [persona, setPersona] = useState<Persona>(initialPersona);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [materialTitle, setMaterialTitle] = useState(initialMaterialTitle);
  const [nodes, setNodes] = useState<KnowledgeNode[]>(initialNodes);
  const [activeNodeId, setActiveNodeId] = useState(initialActiveNodeId);
  const [messageThreads, setMessageThreads] = useState<Record<string, Message[]>>(initialMessageThreads);
  const [messageCountsByNodeId, setMessageCountsByNodeId] = useState<Record<string, number>>(initialMessageCountsByNodeId);
  const [draftsByNodeId, setDraftsByNodeId] = useState<Record<string, string>>(initialDraftsByNodeId);
  const [memories, setMemories] = useState<MemoryEntry[]>(initialMemories);
  const [nodeProfiles, setNodeProfiles] = useState<Record<string, NodeLearningProfile>>(initialNodeProfiles);

  const activeNode = useMemo(() => nodes.find((node) => node.id === activeNodeId) ?? null, [activeNodeId, nodes]);
  const activeProfile = activeNode ? nodeProfiles[activeNode.id] ?? defaultNodeProfile(activeNode) : null;
  const activeNodeMessages = activeNode ? (messageThreads[activeNode.id] ?? []) : [];
  const activeDraft = activeNode ? (draftsByNodeId[activeNode.id] ?? "") : "";
  const nodeMessageCounts = useMemo(() => {
    return nodes.reduce<Record<string, number>>((counts, node) => {
      counts[node.id] = messageThreads[node.id]?.length ?? messageCountsByNodeId[node.id] ?? 0;
      return counts;
    }, {});
  }, [messageCountsByNodeId, messageThreads, nodes]);
  const masteredCount = nodes.filter((node) => node.status === "mastered").length;
  const nextNode = nodes.find((node) => node.status === "available");

  return {
    persona,
    setPersona,
    sessionId,
    setSessionId,
    materialTitle,
    setMaterialTitle,
    nodes,
    setNodes,
    activeNodeId,
    setActiveNodeId,
    messageThreads,
    setMessageThreads,
    messageCountsByNodeId,
    setMessageCountsByNodeId,
    draftsByNodeId,
    setDraftsByNodeId,
    memories,
    setMemories,
    nodeProfiles,
    setNodeProfiles,
    activeNode,
    activeProfile,
    activeNodeMessages,
    activeDraft,
    nodeMessageCounts,
    masteredCount,
    nextNode,
  };
}

export { useLearningSession };
