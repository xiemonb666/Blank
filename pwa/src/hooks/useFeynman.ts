import { useState } from "react";
import { buildFeynmanAnswer } from "../app/sessionState";
import type { FeynmanAnswer, FeynmanQuestion } from "../types";

interface UseFeynmanOptions {
  initialQuestionsByNodeId?: Record<string, FeynmanQuestion[]>;
  initialAnswersByNodeId?: Record<string, Record<string, FeynmanAnswer>>;
  initialQuestions?: FeynmanQuestion[];
  initialAnswerTexts?: Record<string, string>;
  initialStep?: number;
}

function answerTextMap(answers: Record<string, FeynmanAnswer>) {
  return Object.fromEntries(Object.entries(answers).map(([questionId, answer]) => [questionId, answer.answer]));
}

function clampStep(questions: FeynmanQuestion[], step: number) {
  return Math.max(0, Math.min(Math.max(0, questions.length - 1), step));
}

function useFeynman({
  initialQuestionsByNodeId = {},
  initialAnswersByNodeId = {},
  initialQuestions = [],
  initialAnswerTexts = {},
  initialStep = 0,
}: UseFeynmanOptions = {}) {
  const [questionsByNodeId, setQuestionsByNodeId] = useState<Record<string, FeynmanQuestion[]>>(initialQuestionsByNodeId);
  const [answersByNodeId, setAnswersByNodeId] = useState<Record<string, Record<string, FeynmanAnswer>>>(initialAnswersByNodeId);
  const [questions, setQuestions] = useState<FeynmanQuestion[]>(initialQuestions);
  const [answerTexts, setAnswerTexts] = useState<Record<string, string>>(initialAnswerTexts);
  const [currentIndex, setCurrentIndex] = useState(initialStep);
  const [isAdvancing, setIsAdvancing] = useState(false);

  function clearAll() {
    setQuestionsByNodeId({});
    setAnswersByNodeId({});
    resetCurrentNode();
  }

  function resetCurrentNode() {
    setQuestions([]);
    setAnswerTexts({});
    setCurrentIndex(0);
    setIsAdvancing(false);
  }

  function replaceCache(
    nextQuestionsByNodeId: Record<string, FeynmanQuestion[]>,
    nextAnswersByNodeId: Record<string, Record<string, FeynmanAnswer>>,
  ) {
    setQuestionsByNodeId(nextQuestionsByNodeId);
    setAnswersByNodeId(nextAnswersByNodeId);
  }

  function hydrateFromSession(
    nodeId: string,
    nextQuestionsByNodeId: Record<string, FeynmanQuestion[]>,
    nextAnswersByNodeId: Record<string, Record<string, FeynmanAnswer>>,
  ) {
    setQuestionsByNodeId(nextQuestionsByNodeId);
    setAnswersByNodeId(nextAnswersByNodeId);
    hydrateNodeState(nodeId, nextQuestionsByNodeId, nextAnswersByNodeId);
  }

  function hydrateNodeState(
    nodeId: string,
    nextQuestionsByNodeId = questionsByNodeId,
    nextAnswersByNodeId = answersByNodeId,
  ) {
    const nodeQuestions = nextQuestionsByNodeId[nodeId] ?? [];
    const nodeAnswers = nextAnswersByNodeId[nodeId] ?? {};
    setQuestions(nodeQuestions);
    setAnswerTexts(answerTextMap(nodeAnswers));
    const firstUnanswered = nodeQuestions.findIndex((question) => !nodeAnswers[question.id]?.answer?.trim());
    setCurrentIndex(firstUnanswered >= 0 ? firstUnanswered : Math.max(0, nodeQuestions.length - 1));
    setIsAdvancing(false);
  }

  function syncNodeState(
    nodeId: string,
    nextQuestions: FeynmanQuestion[],
    nextAnswers: Record<string, FeynmanAnswer>,
    nextStep?: number,
  ) {
    setQuestionsByNodeId((current) => ({ ...current, [nodeId]: nextQuestions }));
    setAnswersByNodeId((current) => ({ ...current, [nodeId]: nextAnswers }));
    setQuestions(nextQuestions);
    setAnswerTexts(answerTextMap(nextAnswers));
    if (typeof nextStep === "number") {
      setCurrentIndex(clampStep(nextQuestions, nextStep));
    }
  }

  function answerCurrent(nodeId: string, value: string) {
    if (!nodeId) return;
    const question = questions[currentIndex];
    if (!question) return;
    setAnswerTexts((current) => ({ ...current, [question.id]: value }));
    setAnswersByNodeId((current) => ({
      ...current,
      [nodeId]: {
        ...(current[nodeId] ?? {}),
        [question.id]: buildFeynmanAnswer(question, value),
      },
    }));
  }

  function moveStep(offset: number) {
    setCurrentIndex((current) => clampStep(questions, current + offset));
  }

  function buildAnswersForNode(nodeId: string, sourceQuestions = questions) {
    const persistedAnswers = answersByNodeId[nodeId] ?? {};
    return sourceQuestions.map((question) => persistedAnswers[question.id] ?? buildFeynmanAnswer(question, answerTexts[question.id] ?? ""));
  }

  return {
    questionsByNodeId,
    answersByNodeId,
    questions,
    answerTexts,
    currentIndex,
    isAdvancing,
    setIsAdvancing,
    clearAll,
    resetCurrentNode,
    replaceCache,
    hydrateFromSession,
    hydrateNodeState,
    syncNodeState,
    answerCurrent,
    moveStep,
    buildAnswersForNode,
  };
}

export { useFeynman };
