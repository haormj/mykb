export type TreeLevel = "raw" | "knowledge";

export interface TreeSourceItem {
  concept_id: string;
  title?: string | null;
}

export interface TreeNode<T extends TreeSourceItem = TreeSourceItem> {
  key: string;
  title: string;
  isLeaf: boolean;
  conceptId?: string;
  item?: T;
  count?: number;
  children?: TreeNode<T>[];
}

interface TrieNode<T extends TreeSourceItem> {
  name: string;
  path: string;
  children: Map<string, TrieNode<T>>;
  file?: { item: T; conceptId: string };
  fileCount: number;
}

function createTrie<T extends TreeSourceItem>(name: string, path: string): TrieNode<T> {
  return { name, path, children: new Map(), fileCount: 0 };
}

function compareName(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

function defaultTitle(item: TreeSourceItem): string {
  const title = item.title;
  if (typeof title === "string" && title.trim()) {
    return title;
  }
  const segments = item.concept_id.split("/").filter(Boolean);
  return segments[segments.length - 1] ?? item.concept_id;
}

function render<T extends TreeSourceItem>(
  trie: TrieNode<T>,
  level: TreeLevel,
  getTitle: (item: T) => string,
): TreeNode<T>[] {
  const dirs: { node: TreeNode<T>; name: string }[] = [];
  const files: { node: TreeNode<T>; name: string }[] = [];

  for (const child of trie.children.values()) {
    if (child.children.size > 0) {
      dirs.push({
        name: child.name,
        node: {
          key: `dir:${level}/${child.path}`,
          title: child.name,
          isLeaf: false,
          count: child.fileCount,
          children: render(child, level, getTitle),
        },
      });
    }
    if (child.file) {
      files.push({
        name: child.name,
        node: {
          key: `file:${child.file.conceptId}`,
          title: getTitle(child.file.item),
          isLeaf: true,
          conceptId: child.file.conceptId,
          item: child.file.item,
        },
      });
    }
  }

  dirs.sort((a, b) => compareName(a.name, b.name));
  files.sort((a, b) => compareName(a.name, b.name));

  return [...dirs.map((entry) => entry.node), ...files.map((entry) => entry.node)];
}

export function buildTree<T extends TreeSourceItem>(
  items: readonly T[],
  level: TreeLevel,
  getTitle: (item: T) => string = defaultTitle,
): TreeNode<T>[] {
  const prefix = `${level}/`;
  const root = createTrie<T>("", "");

  for (const item of items) {
    const normalized = item.concept_id.replace(/^\/+/, "");
    if (!normalized.startsWith(prefix)) {
      continue;
    }
    const segments = normalized.slice(prefix.length).split("/").filter(Boolean);
    if (segments.length === 0) {
      continue;
    }

    let cursor = root;
    let path = "";
    root.fileCount += 1;
    for (const segment of segments) {
      path = path ? `${path}/${segment}` : segment;
      let next = cursor.children.get(segment);
      if (!next) {
        next = createTrie<T>(segment, path);
        cursor.children.set(segment, next);
      }
      cursor = next;
      cursor.fileCount += 1;
    }
    cursor.file = { item, conceptId: normalized };
  }

  return render(root, level, getTitle);
}

export interface FilterResult<T extends TreeSourceItem> {
  nodes: TreeNode<T>[];
  expandKeys: string[];
}

export function filterTree<T extends TreeSourceItem>(
  nodes: TreeNode<T>[],
  query: string,
): FilterResult<T> {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return { nodes, expandKeys: [] };
  }

  const expand = new Set<string>();

  const walk = (list: TreeNode<T>[]): TreeNode<T>[] => {
    const kept: TreeNode<T>[] = [];
    for (const node of list) {
      if (node.isLeaf) {
        const titleMatch = node.title.toLowerCase().includes(needle);
        const pathMatch = (node.conceptId ?? "").toLowerCase().includes(needle);
        if (titleMatch || pathMatch) {
          kept.push(node);
        }
        continue;
      }
      const children = walk(node.children ?? []);
      if (children.length > 0) {
        kept.push({ ...node, children });
        expand.add(node.key);
      }
    }
    return kept;
  };

  return { nodes: walk(nodes), expandKeys: Array.from(expand).sort() };
}
