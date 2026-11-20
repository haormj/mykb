import { describe, expect, it } from "vitest";
import {
  assignableRoles,
  canManageMember,
  privileges,
  roleRank,
} from "./context";

describe("knowledge-base role privileges", () => {
  it("viewer is read-only", () => {
    expect(privileges("viewer")).toEqual({
      canWrite: false,
      canAdmin: false,
      isOwner: false,
    });
  });

  it("editor can write but cannot administer", () => {
    expect(privileges("editor")).toEqual({
      canWrite: true,
      canAdmin: false,
      isOwner: false,
    });
  });

  it("admin can administer but is not owner", () => {
    expect(privileges("admin")).toEqual({
      canWrite: true,
      canAdmin: true,
      isOwner: false,
    });
  });

  it("owner has every privilege", () => {
    expect(privileges("owner")).toEqual({
      canWrite: true,
      canAdmin: true,
      isOwner: true,
    });
  });
});

describe("member management boundaries", () => {
  it("owner manages lower roles but never another owner", () => {
    expect(canManageMember("owner", "admin", true)).toBe(true);
    expect(canManageMember("owner", "editor", true)).toBe(true);
    expect(canManageMember("owner", "owner", true)).toBe(false);
  });

  it("admin manages only strictly lower roles", () => {
    expect(canManageMember("admin", "editor", true)).toBe(true);
    expect(canManageMember("admin", "viewer", true)).toBe(true);
    expect(canManageMember("admin", "admin", true)).toBe(false);
    expect(canManageMember("admin", "owner", true)).toBe(false);
  });

  it("non-admins cannot manage members", () => {
    expect(canManageMember("editor", "viewer", false)).toBe(false);
    expect(canManageMember("viewer", "viewer", false)).toBe(false);
  });
});

describe("assignable roles", () => {
  it("owner can assign admin and below", () => {
    expect(assignableRoles("owner")).toEqual(["admin", "editor", "viewer"]);
  });

  it("admin cannot assign admin or owner", () => {
    expect(assignableRoles("admin")).toEqual(["editor", "viewer"]);
  });
});

describe("role ranks", () => {
  it("orders roles viewer < editor < admin < owner", () => {
    expect(roleRank("viewer")).toBeLessThan(roleRank("editor"));
    expect(roleRank("editor")).toBeLessThan(roleRank("admin"));
    expect(roleRank("admin")).toBeLessThan(roleRank("owner"));
  });
});
