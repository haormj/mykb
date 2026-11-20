import type { KnowledgeBase, Member } from "@/services/api";

export const WRITE_ROLES = new Set(["owner", "admin", "editor"]);
export const ADMIN_ROLES = new Set(["owner", "admin"]);

export interface KbOutletContext {
  kb: KnowledgeBase;
  members: Member[];
  refresh: () => Promise<void>;
  canWrite: boolean;
  canAdmin: boolean;
  isOwner: boolean;
}

export function privileges(role: string) {
  return {
    canWrite: WRITE_ROLES.has(role),
    canAdmin: ADMIN_ROLES.has(role),
    isOwner: role === "owner",
  };
}

export function roleRank(role: string): number {
  return { viewer: 1, editor: 2, admin: 3, owner: 4 }[role] ?? 0;
}

export function assignableRoles(actorRole: string): string[] {
  return actorRole === "owner" ? ["admin", "editor", "viewer"] : ["editor", "viewer"];
}

export function canManageMember(
  actorRole: string,
  targetRole: string,
  canAdmin: boolean,
): boolean {
  return canAdmin && targetRole !== "owner" && roleRank(targetRole) < roleRank(actorRole);
}
