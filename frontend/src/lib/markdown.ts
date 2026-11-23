export const ASSET_URL_PREFIX = "/__mykb_asset__/";

const FRONTMATTER = /^\uFEFF?---\r?\n[\s\S]*?\r?\n---[ \t]*\r?\n?/;
const IMAGE_LINK = /(!\[[^\]]*\]\()\s*([^)\s]+)([^)]*)(\))/g;

export function stripFrontmatter(markdown: string): string {
  return markdown.replace(FRONTMATTER, "");
}

function isRewritableTarget(target: string): boolean {
  if (!target) return false;
  if (target.startsWith("#") || target.startsWith("//")) return false;
  return !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(target);
}

export function assetNameFromTarget(target: string): string | null {
  const withoutQuery = target.split("#")[0].split("?")[0];
  const marker = withoutQuery.lastIndexOf(".assets/");
  if (marker === -1) return null;
  const name = withoutQuery.slice(marker + ".assets/".length);
  if (!name || name.includes("/")) return null;
  try {
    return decodeURIComponent(name);
  } catch {
    return name;
  }
}

export function rewriteAssetLinks(markdown: string, conceptId: string): string {
  return markdown.replace(IMAGE_LINK, (match, head: string, rawTarget: string, tail: string, close) => {
    const target = rawTarget.startsWith("<") && rawTarget.endsWith(">")
      ? rawTarget.slice(1, -1)
      : rawTarget;
    if (!isRewritableTarget(target)) return match;
    const name = assetNameFromTarget(target);
    if (!name) return match;
    const url = `${ASSET_URL_PREFIX}${encodeURIComponent(conceptId)}/${encodeURIComponent(name)}`;
    return `${head}${url}${tail}${close}`;
  });
}

export function parseAssetUrl(src: string): { conceptId: string; name: string } | null {
  if (!src.startsWith(ASSET_URL_PREFIX)) return null;
  const rest = src.slice(ASSET_URL_PREFIX.length);
  const [encodedConcept, encodedName] = rest.split("/");
  if (!encodedConcept || !encodedName) return null;
  try {
    return {
      conceptId: decodeURIComponent(encodedConcept),
      name: decodeURIComponent(encodedName),
    };
  } catch {
    return null;
  }
}
