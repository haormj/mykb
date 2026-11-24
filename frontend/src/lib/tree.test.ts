import { describe, expect, it } from "vitest";
import { buildTree, filterTree, type TreeNode } from "./tree";

interface Item {
  concept_id: string;
  title?: string | null;
}

const item = (concept_id: string, title?: string): Item => ({ concept_id, title });

function allKeys(nodes: TreeNode<Item>[]): string[] {
  return nodes.flatMap((node) => [node.key, ...(node.children ? allKeys(node.children) : [])]);
}

describe("buildTree", () => {
  it("groups nested concept ids into folders and leaves", () => {
    const tree = buildTree(
      [item("raw/upload/q1", "Q1"), item("raw/upload/2024/q2", "Q2")],
      "raw",
    );

    expect(tree).toHaveLength(1);
    const upload = tree[0];
    expect(upload).toMatchObject({ key: "dir:raw/upload", title: "upload", isLeaf: false, count: 2 });
    expect(upload.children?.map((node) => node.key)).toEqual([
      "dir:raw/upload/2024",
      "file:raw/upload/q1",
    ]);
    const year = upload.children?.[0];
    expect(year?.children?.map((node) => node.key)).toEqual(["file:raw/upload/2024/q2"]);
  });

  it("only includes the requested level", () => {
    const tree = buildTree(
      [item("raw/upload/a"), item("knowledge/topics/b")],
      "knowledge",
    );

    expect(allKeys(tree)).toEqual(["dir:knowledge/topics", "file:knowledge/topics/b"]);
  });

  it("places folders before files and sorts each group naturally", () => {
    const tree = buildTree(
      [
        item("raw/b"),
        item("raw/a"),
        item("raw/10/x"),
        item("raw/2/y"),
      ],
      "raw",
    );

    expect(tree.map((node) => node.key)).toEqual([
      "dir:raw/2",
      "dir:raw/10",
      "file:raw/a",
      "file:raw/b",
    ]);
  });

  it("keeps a file and a same-named folder as distinct nodes", () => {
    const tree = buildTree(
      [item("raw/upload", "Upload File"), item("raw/upload/child", "Child")],
      "raw",
    );

    expect(tree.map((node) => node.key)).toEqual(["dir:raw/upload", "file:raw/upload"]);
    const folder = tree[0];
    const file = tree[1];
    expect(folder.isLeaf).toBe(false);
    expect(folder.children?.map((node) => node.key)).toEqual(["file:raw/upload/child"]);
    expect(file.isLeaf).toBe(true);
    expect(file.conceptId).toBe("raw/upload");
    expect(file.item).toMatchObject({ title: "Upload File" });
  });

  it("renders top-level files directly under the level", () => {
    const tree = buildTree([item("raw/loose", "Loose")], "raw");

    expect(tree).toHaveLength(1);
    expect(tree[0]).toMatchObject({
      key: "file:raw/loose",
      title: "Loose",
      isLeaf: true,
      conceptId: "raw/loose",
    });
  });

  it("counts all descendant files for a folder", () => {
    const tree = buildTree(
      [item("raw/a/1"), item("raw/a/2"), item("raw/a/deep/3"), item("raw/b/4")],
      "raw",
    );

    const a = tree.find((node) => node.key === "dir:raw/a");
    const b = tree.find((node) => node.key === "dir:raw/b");
    expect(a?.count).toBe(3);
    expect(b?.count).toBe(1);
  });

  it("falls back to the path segment when a title is missing", () => {
    const tree = buildTree([item("raw/upload/q1")], "raw", (value) => value.title ?? "custom");
    const upload = tree[0];

    expect(upload.children?.[0].title).toBe("custom");
  });

  it("returns an empty array for no items", () => {
    expect(buildTree([], "raw")).toEqual([]);
  });
});

describe("filterTree", () => {
  const tree = buildTree(
    [
      item("raw/upload/q1", "Quarter One"),
      item("raw/upload/2024/q2", "Quarter Two"),
      item("raw/other/z", "Zeta"),
    ],
    "raw",
  );

  it("filters by title and keeps ancestors expanded", () => {
    const result = filterTree(tree, "quarter two");

    expect(result.nodes.map((node) => node.key)).toEqual(["dir:raw/upload"]);
    expect(result.nodes[0].children?.map((node) => node.key)).toEqual(["dir:raw/upload/2024"]);
    expect(result.expandKeys).toEqual(["dir:raw/upload", "dir:raw/upload/2024"]);
  });

  it("filters by concept path", () => {
    const result = filterTree(tree, "raw/other");

    expect(result.nodes.map((node) => node.key)).toEqual(["dir:raw/other"]);
    expect(result.nodes[0].children?.map((node) => node.key)).toEqual(["file:raw/other/z"]);
    expect(result.expandKeys).toEqual(["dir:raw/other"]);
  });

  it("returns no nodes and no expansion when nothing matches", () => {
    const result = filterTree(tree, "missing");

    expect(result.nodes).toEqual([]);
    expect(result.expandKeys).toEqual([]);
  });

  it("returns the full tree and no expansion for an empty query", () => {
    const result = filterTree(tree, "   ");

    expect(result.nodes).toBe(tree);
    expect(result.expandKeys).toEqual([]);
  });
});
