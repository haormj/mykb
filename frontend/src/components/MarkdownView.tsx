import { useEffect, useMemo, useState } from "react";
import type { ImgHTMLAttributes } from "react";
import { Spin, Typography } from "antd";
import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { mermaid } from "@streamdown/mermaid";
import { math } from "@streamdown/math";
import { cjk } from "@streamdown/cjk";
import { api } from "@/services/api";
import { parseAssetUrl, rewriteAssetLinks, stripFrontmatter } from "@/lib/markdown";

const PLUGINS = { code, mermaid, math, cjk };

interface CachedAsset {
  url: string;
  count: number;
}

const assetCache = new Map<string, CachedAsset>();
const assetPending = new Map<string, Promise<string>>();

function acquireAsset(key: string, loader: () => Promise<Blob>): Promise<string> {
  const existing = assetCache.get(key);
  if (existing) {
    existing.count += 1;
    return Promise.resolve(existing.url);
  }
  const inflight = assetPending.get(key);
  if (inflight) {
    return inflight.then((url) => {
      const entry = assetCache.get(key);
      if (entry) {
        entry.count += 1;
      } else {
        assetCache.set(key, { url, count: 1 });
      }
      return url;
    });
  }
  const promise = loader().then((blob) => URL.createObjectURL(blob));
  assetPending.set(key, promise);
  return promise
    .then((url) => {
      assetPending.delete(key);
      const entry = assetCache.get(key);
      if (entry) {
        entry.count += 1;
        return entry.url;
      }
      assetCache.set(key, { url, count: 1 });
      return url;
    })
    .catch((error) => {
      assetPending.delete(key);
      throw error;
    });
}

function releaseAsset(key: string): void {
  const entry = assetCache.get(key);
  if (!entry) return;
  entry.count -= 1;
  if (entry.count <= 0) {
    URL.revokeObjectURL(entry.url);
    assetCache.delete(key);
  }
}

type ImageProps = ImgHTMLAttributes<HTMLImageElement> & { node?: unknown };

function AuthedImage({
  kbId,
  conceptId,
  src,
  alt,
  node: _node,
  ...rest
}: ImageProps & { kbId: string; conceptId: string }) {
  const parsed = src ? parseAssetUrl(src) : null;
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const key = parsed ? `${kbId}/${parsed.conceptId}/${parsed.name}` : null;

  useEffect(() => {
    if (!parsed || !key) return;
    let cancelled = false;
    let acquired = false;
    setFailed(false);
    setUrl(null);
    acquireAsset(key, () => api.fetchConceptAsset(kbId, parsed.conceptId, parsed.name))
      .then((objectUrl) => {
        if (cancelled) {
          releaseAsset(key);
          return;
        }
        acquired = true;
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (acquired) releaseAsset(key);
    };
  }, [kbId, key, parsed?.conceptId, parsed?.name]);

  if (!parsed) {
    return <img src={src} alt={alt} {...rest} />;
  }
  if (failed) {
    return <Typography.Text type="secondary">{alt || "图片加载失败"}</Typography.Text>;
  }
  if (!url) {
    return <Spin size="small" />;
  }
  return <img src={url} alt={alt} {...rest} />;
}

export interface MarkdownViewProps {
  kbId: string;
  conceptId: string;
  markdown: string;
}

export default function MarkdownView({ kbId, conceptId, markdown }: MarkdownViewProps) {
  const content = useMemo(
    () => rewriteAssetLinks(stripFrontmatter(markdown), conceptId),
    [markdown, conceptId],
  );
  const components = useMemo(
    () => ({
      img: (props: ImageProps) => <AuthedImage {...props} kbId={kbId} conceptId={conceptId} />,
    }),
    [kbId, conceptId],
  );

  return (
    <div className="markdown-view">
      <Streamdown mode="static" plugins={PLUGINS} components={components}>
        {content}
      </Streamdown>
    </div>
  );
}
