import { describe, expect, it } from "vitest";
import {
  ASSET_URL_PREFIX,
  assetNameFromTarget,
  parseAssetUrl,
  rewriteAssetLinks,
  stripFrontmatter,
} from "./markdown";

describe("stripFrontmatter", () => {
  it("removes a leading YAML frontmatter block", () => {
    const text = "---\ntype: 源数据\ntitle: Doc\n---\n# Doc\n\nbody";
    expect(stripFrontmatter(text)).toBe("# Doc\n\nbody");
  });

  it("leaves markdown without frontmatter untouched", () => {
    expect(stripFrontmatter("# Doc\n\nbody")).toBe("# Doc\n\nbody");
  });

  it("does not strip a later horizontal rule", () => {
    const text = "# Doc\n\n---\n\nbody";
    expect(stripFrontmatter(text)).toBe(text);
  });
});

describe("assetNameFromTarget", () => {
  it("extracts the file name from a concept asset link", () => {
    expect(assetNameFromTarget("report.docx.assets/001-abc.png")).toBe("001-abc.png");
    expect(assetNameFromTarget("./report.docx.assets/001-abc.png")).toBe("001-abc.png");
  });

  it("ignores query strings and fragments", () => {
    expect(assetNameFromTarget("a.assets/img.png?x=1#y")).toBe("img.png");
  });

  it("returns null for links outside an asset directory", () => {
    expect(assetNameFromTarget("images/foo.png")).toBeNull();
    expect(assetNameFromTarget("a.assets/nested/foo.png")).toBeNull();
    expect(assetNameFromTarget("https://example.com/a.assets/foo.png")).toBe("foo.png");
  });
});

describe("rewriteAssetLinks", () => {
  it("rewrites relative asset links to the placeholder URL", () => {
    const result = rewriteAssetLinks("![img](report.docx.assets/001-abc.png)", "raw/upload/report.docx");
    const expected = `![img](${ASSET_URL_PREFIX}${encodeURIComponent("raw/upload/report.docx")}/001-abc.png)`;
    expect(result).toBe(expected);
  });

  it("keeps external links and non-asset relative links", () => {
    const text = "![a](https://example.com/x.png)\n![b](images/y.png)";
    expect(rewriteAssetLinks(text, "raw/upload/doc")).toBe(text);
  });

  it("preserves an optional title", () => {
    const result = rewriteAssetLinks(
      '![img](report.docx.assets/001.png "shot")',
      "raw/upload/report.docx",
    );
    expect(result).toContain(' "shot")');
    expect(result).toContain(ASSET_URL_PREFIX);
  });
});

describe("parseAssetUrl", () => {
  it("round-trips a rewritten asset URL", () => {
    const url = `${ASSET_URL_PREFIX}${encodeURIComponent("raw/upload/report.docx")}/001-abc.png`;
    expect(parseAssetUrl(url)).toEqual({
      conceptId: "raw/upload/report.docx",
      name: "001-abc.png",
    });
  });

  it("returns null for other URLs", () => {
    expect(parseAssetUrl("https://example.com/x.png")).toBeNull();
    expect(parseAssetUrl(ASSET_URL_PREFIX)).toBeNull();
  });
});
