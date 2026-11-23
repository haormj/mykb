export interface EvalCase {
  question: string;
  reference_answer: string;
  expected_concept?: string;
  domain?: string;
  difficulty?: string;
}

export interface EvalCaseRow extends EvalCase {
  id: string;
  position: number;
}

export interface EvalSetInput {
  name: string;
  title?: string;
  description?: string;
  cases: EvalCase[];
}

export interface EvalSetSummary {
  id: string;
  name: string;
  title?: string | null;
  description?: string | null;
  owner_user_id: string;
  case_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface EvalSetDetail extends EvalSetSummary {
  cases: EvalCaseRow[];
}

export interface TrendPoint {
  created_at?: string | null;
  a_score: number;
  b_score: number;
  coverage: number;
  knowledge_version?: string | null;
}

export interface EvalRun {
  id: string;
  set_id: string;
  target_kb_id: string;
  triggered_by?: string | null;
  knowledge_version?: string | null;
  case_count: number;
  coverage: number;
  a_score: number;
  b_score: number;
  created_at?: string | null;
}

export interface EvalOverview {
  sets: { id: string; name: string; title?: string | null }[];
  kbs: { id: string; name: string; my_role: string }[];
  runs: EvalRun[];
}

export interface Draft {
  concept_id: string;
  title: string | null;
  status: string;
}

export interface ReviewMr {
  item_id: string;
  concept_id: string;
  title?: string | null;
  action: string;
  status: string;
  branch?: string | null;
  error?: string | null;
}

export interface ReviewMrDiff {
  item_id: string;
  concept_id: string;
  branch: string;
  files: string[];
  diff: string;
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

export interface DocumentItem {
  concept_id: string;
  title: string;
  resource?: string | null;
  status?: string | null;
  type?: string | null;
  import_task_id?: string | null;
}

export interface KnowledgeItem {
  concept_id: string;
  title: string;
  status?: string | null;
  type?: string | null;
  verified: boolean;
  sources: string[];
}

export interface ImportTask {
  id: string;
  kb_id: string;
  source_type: string;
  status:
    | "queued"
    | "running"
    | "converting"
    | "queued-for-review"
    | "reviewing"
    | "merged"
    | "rejected"
    | "succeeded"
    | "partial"
    | "failed"
    | "cancelled";
  total: number;
  added: number;
  updated: number;
  skipped: number;
  failed: number;
  error?: string | null;
  created_by: string;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

const ACTIVE_TASK_STATUSES = new Set([
  "queued",
  "running",
  "converting",
  "queued-for-review",
  "reviewing",
]);

export function isActiveTask(task: ImportTask): boolean {
  return ACTIVE_TASK_STATUSES.has(task.status);
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

  // -- documents & import tasks ----------------------------------------
  listDocuments: async (kbId: string): Promise<DocumentItem[]> =>
    (await request<{ documents: DocumentItem[] }>(`/kbs/${kbId}/documents`)).documents,

  listImportTasks: async (kbId: string): Promise<ImportTask[]> =>
    (await request<{ tasks: ImportTask[] }>(`/kbs/${kbId}/import-tasks`)).tasks,

  createImportTask: async (kbId: string, files: File[]): Promise<ImportTask> => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<ImportTask>(`/kbs/${kbId}/import-tasks`, { method: "POST", body: form });
  },

  cancelImportTask: async (kbId: string, taskId: string): Promise<ImportTask> =>
    request<ImportTask>(`/kbs/${kbId}/import-tasks/${taskId}/cancel`, { method: "POST" }),

  listKnowledge: async (kbId: string): Promise<KnowledgeItem[]> =>
    (await request<{ knowledge: KnowledgeItem[] }>(`/kbs/${kbId}/knowledge`)).knowledge,

  // -- knowledge-base settings -----------------------------------------
  bindRemote: async (
    kbId: string,
    input: { git_url: string; git_branch?: string; git_token?: string },
  ): Promise<KnowledgeBase> =>
    request<KnowledgeBase>(`/kbs/${kbId}/remote`, { method: "POST", body: jsonBody(input) }),

  deleteKb: async (kbId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}`, { method: "DELETE" });
  },

  addMember: async (
    kbId: string,
    input: { username: string; role: string },
  ): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/members`, { method: "POST", body: jsonBody(input) });
  },

  updateMember: async (kbId: string, userId: string, role: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/members/${userId}`, {
      method: "PATCH",
      body: jsonBody({ role }),
    });
  },

  removeMember: async (kbId: string, userId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/members/${userId}`, { method: "DELETE" });
  },

  transferOwner: async (kbId: string, userId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/members/${userId}/transfer`, { method: "POST" });
  },

  // -- platform-level evaluation ---------------------------------------
  listEvalSets: async (): Promise<EvalSetSummary[]> =>
    (await request<{ sets: EvalSetSummary[] }>("/eval/sets")).sets,

  getEvalSet: async (setId: string): Promise<EvalSetDetail> =>
    request<EvalSetDetail>(`/eval/sets/${setId}`),

  createEvalSet: async (input: EvalSetInput): Promise<EvalSetDetail> =>
    request<EvalSetDetail>("/eval/sets", { method: "POST", body: jsonBody(input) }),

  updateEvalSet: async (setId: string, input: EvalSetInput): Promise<EvalSetDetail> =>
    request<EvalSetDetail>(`/eval/sets/${setId}`, { method: "PATCH", body: jsonBody(input) }),

  deleteEvalSet: async (setId: string): Promise<void> => {
    await request<unknown>(`/eval/sets/${setId}`, { method: "DELETE" });
  },

  runEvalSet: async (setId: string, targetKbIds: string[]): Promise<EvalRun[]> =>
    (
      await request<{ runs: EvalRun[] }>(`/eval/sets/${setId}/run`, {
        method: "POST",
        body: jsonBody({ target_kb_ids: targetKbIds }),
      })
    ).runs,

  listEvalRuns: async (
    params: { kbId?: string; setId?: string } = {},
  ): Promise<EvalRun[]> => {
    const search = new URLSearchParams();
    if (params.kbId) search.set("kb_id", params.kbId);
    if (params.setId) search.set("set_id", params.setId);
    const suffix = search.toString();
    return (
      await request<{ runs: EvalRun[] }>(`/eval/runs${suffix ? `?${suffix}` : ""}`)
    ).runs;
  },

  evalTrend: async (setId: string, kbId: string): Promise<TrendPoint[]> =>
    (
      await request<{ trend: TrendPoint[] }>(
        `/eval/sets/${setId}/trend?kb_id=${encodeURIComponent(kbId)}`,
      )
    ).trend,

  evalOverview: async (): Promise<EvalOverview> => request<EvalOverview>("/eval/overview"),

  // -- scoped review ----------------------------------------------------
  listDrafts: async (kbId: string): Promise<Draft[]> =>
    (await request<{ drafts: Draft[] }>(`/kbs/${kbId}/review/drafts`)).drafts,

  diff: async (kbId: string, conceptId: string): Promise<string> =>
    (
      await request<{ diff: string }>(
        `/kbs/${kbId}/review/diff?concept_id=${encodeURIComponent(conceptId)}`,
      )
    ).diff,

  approve: async (kbId: string, conceptId: string, reviewer: string): Promise<void> => {
    await request<unknown>(
      `/kbs/${kbId}/review/approve?concept_id=${encodeURIComponent(conceptId)}&reviewer=${encodeURIComponent(reviewer)}`,
      { method: "POST" },
    );
  },

  // -- document-level review MRs ---------------------------------------
  listReviewMrs: async (kbId: string): Promise<ReviewMr[]> =>
    (await request<{ mrs: ReviewMr[] }>(`/kbs/${kbId}/review/mrs`)).mrs,

  reviewMrDiff: async (kbId: string, itemId: string): Promise<ReviewMrDiff> =>
    request<ReviewMrDiff>(`/kbs/${kbId}/review/mrs/${itemId}/diff`),

  approveMr: async (kbId: string, itemId: string, reviewer: string): Promise<void> => {
    await request<unknown>(
      `/kbs/${kbId}/review/mrs/${itemId}/approve?reviewer=${encodeURIComponent(reviewer)}`,
      { method: "POST" },
    );
  },

  rejectMr: async (kbId: string, itemId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/review/mrs/${itemId}/reject`, { method: "POST" });
  },

  redraftMr: async (kbId: string, itemId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/review/mrs/${itemId}/redraft`, { method: "POST" });
  },

  deleteDocument: async (kbId: string, conceptId: string): Promise<void> => {
    await request<unknown>(`/kbs/${kbId}/documents/${conceptId}`, { method: "DELETE" });
  },
};
