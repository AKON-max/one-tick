import { requireAuth } from "@/lib/auth-utils";
import { apiFetch } from "@/lib/server-api";
import { notFound } from "next/navigation";
import { DocStudioClient } from "./doc-studio-client";

export const dynamic = "force-dynamic";

interface DocDetail {
  id: string;
  userId: string;
  title: string;
  content: string;
}

export default async function DocStudioPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await requireAuth();
  const { id } = await params;

  let res: { document: DocDetail; indexed: boolean } | null = null;
  try {
    res = await apiFetch<{ document: DocDetail; indexed: boolean }>(`/api/documents/${id}`);
  } catch {
    notFound();
  }
  if (!res?.document || res.document.userId !== user.id) notFound();

  const doc = res.document;
  const indexed = res.indexed;

  return (
    <DocStudioClient
      docId={doc.id}
      title={doc.title}
      initialContent={doc.content}
      readOnly={Boolean(indexed)}
      backHref="/docs"
      backLabel={indexed ? "返回文档列表（已加入知识库，只读）" : "返回文档列表"}
    />
  );
}
