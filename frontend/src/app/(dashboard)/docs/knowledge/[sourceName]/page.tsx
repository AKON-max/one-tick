import { requireAuth } from "@/lib/auth-utils";
import { apiFetch } from "@/lib/server-api";
import { notFound } from "next/navigation";
import { DocStudioClient } from "../../[id]/doc-studio-client";

export const dynamic = "force-dynamic";

function toTitle(sourceName: string) {
  return sourceName.replace(/\.(txt|md|markdown)$/i, "") || sourceName;
}

interface KnowledgeDocDetail {
  sourceName: string;
  sourceType: string;
  content: string;
  chunkCount: number;
  createdAt: string;
}

export default async function KnowledgeDocReadPage({
  params,
}: {
  params: Promise<{ sourceName: string }>;
}) {
  const user = await requireAuth();
  const { sourceName } = await params;
  const decoded = decodeURIComponent(sourceName);

  // FastAPI 聚合返回原文 + 切片；非 Markdown 或不存在的文档会 404/400，统一按 notFound 处理
  let doc: KnowledgeDocDetail | null = null;
  try {
    const res = await apiFetch<{ document: KnowledgeDocDetail }>(
      `/api/knowledge/documents/${encodeURIComponent(decoded)}`,
    );
    doc = res.document;
  } catch {
    notFound();
  }
  if (!doc) notFound();

  return (
    <DocStudioClient
      docId={`knowledge:${encodeURIComponent(decoded)}`}
      title={toTitle(doc.sourceName)}
      initialContent={doc.content}
      readOnly
      backHref="/agent"
      backLabel="返回知识库"
      backNavigation="replace"
    />
  );
}
