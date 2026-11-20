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

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  email?: string | null;
  roles: string[];
  permissions: string[];
}

export interface KnowledgeBase {
  id: string;
  name: string;
  slug: string;
  git_url?: string | null;
  git_branch: string;
  local_path: string;
  owner_id: string;
  my_role: string;
  has_remote: boolean;
}

export interface Member {
  user_id: string;
  username: string;
  display_name: string;
  email?: string | null;
  role: string;
}

const TOKEN_KEY = "mykb.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function getJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`${res.status} ${await res.text()}`);
  }
  return (await res.json()) as T;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearToken();
  }
  return getJson<T>(res);
}

function jsonBody(payload: unknown): string {
  return JSON.stringify(payload);
}

export const api = {
  // -- identity ---------------------------------------------------------
  register: async (username: string, password: string): Promise<{ token: string; user: CurrentUser }> =>
    request<{ token: string; user: CurrentUser }>("/auth/register", {
      method: "POST",
      body: jsonBody({ username, password }),
    }),

  login: async (username: string, password: string): Promise<{ token: string; user: CurrentUser }> =>
    request<{ token: string; user: CurrentUser }>("/auth/login", {
      method: "POST",
      body: jsonBody({ username, password }),
    }),

  logout: async (): Promise<void> => {
    try {
      await request<unknown>("/auth/logout", { method: "POST" });
    } finally {
      clearToken();
    }
  },

  me: async (): Promise<CurrentUser> => request<CurrentUser>("/auth/me"),

  // -- knowledge bases --------------------------------------------------
  listKbs: async (): Promise<KnowledgeBase[]> =>
    (await request<{ knowledge_bases: KnowledgeBase[] }>("/kbs")).knowledge_bases,

  createKb: async (input: {
    name: string;
    git_url?: string;
    git_branch?: string;
    git_token?: string;
  }): Promise<KnowledgeBase> =>
    request<KnowledgeBase>("/kbs", { method: "POST", body: jsonBody(input) }),

  getKb: async (kbId: string): Promise<KnowledgeBase> => request<KnowledgeBase>(`/kbs/${kbId}`),

  patchKb: async (kbId: string, input: { name?: string; git_branch?: string }): Promise<KnowledgeBase> =>
    request<KnowledgeBase>(`/kbs/${kbId}`, { method: "PATCH", body: jsonBody(input) }),

  listMembers: async (kbId: string): Promise<Member[]> =>
    (await request<{ members: Member[] }>(`/kbs/${kbId}/members`)).members,

  // -- legacy (hidden in this phase; moved into knowledge-base scope next) --
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
