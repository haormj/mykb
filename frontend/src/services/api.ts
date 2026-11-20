export interface EvalCase {
  question: string;
  reference_answer: string;
  expected_concept?: string;
  domain?: string;
  difficulty?: string;
}

export interface EvalSetInput {
  name: string;
  title?: string;
  cases: EvalCase[];
}

export interface TrendPoint {
  created_at: string;
  a_score: number;
  b_score: number;
  knowledge_version?: string;
}

export interface EvalRun {
  set_name: string;
  a_score: number;
  b_score: number;
  created_at: string;
  knowledge_version?: string;
}

export interface Draft {
  concept_id: string;
  title: string | null;
  status: string;
}

async function getJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`${res.status} ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export const api = {
  listEvalSets: async (): Promise<string[]> =>
    (await getJson<{ sets: string[] }>(await fetch("/eval/sets"))).sets,

  createEvalSet: async (input: EvalSetInput): Promise<void> => {
    await getJson<unknown>(
      await fetch("/eval/sets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    );
  },

  runEval: async (name: string): Promise<EvalRun> =>
    getJson<EvalRun>(
      await fetch(`/eval/run?name=${encodeURIComponent(name)}`, { method: "POST" }),
    ),

  trend: async (name: string): Promise<TrendPoint[]> =>
    (
      await getJson<{ trend: TrendPoint[] }>(
        await fetch(`/eval/sets/${encodeURIComponent(name)}/trend`),
      )
    ).trend,

  listDrafts: async (): Promise<Draft[]> =>
    (await getJson<{ drafts: Draft[] }>(await fetch("/review/drafts"))).drafts,

  diff: async (conceptId: string): Promise<string> =>
    (
      await getJson<{ diff: string }>(
        await fetch(`/review/diff?concept_id=${encodeURIComponent(conceptId)}`),
      )
    ).diff,

  approve: async (conceptId: string, reviewer: string): Promise<void> => {
    await getJson<unknown>(
      await fetch(
        `/review/approve?concept_id=${encodeURIComponent(conceptId)}&reviewer=${encodeURIComponent(reviewer)}`,
        { method: "POST" },
      ),
    );
  },
};
