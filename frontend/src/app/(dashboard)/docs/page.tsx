import { requireAuth } from "@/lib/auth-utils";
import { apiFetch } from "@/lib/server-api";
import { DocsClient } from "./docs-client";

interface DocItem {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export default async function DocsPage() {
  const user = await requireAuth();

  let docs: DocItem[] = [];
  try {
    const res = await apiFetch<{ documents: DocItem[] }>("/api/documents");
    docs = res.documents ?? [];
  } catch {
    // FastAPI 不可达时按空列表降级展示
  }

  return (
    <div className="product-page product-page--redesigned">
      <header className="product-header">
        <div>
          <p className="product-eyebrow">Doc studio</p>
          <h1 className="product-title">文档</h1>
          <p className="product-subtitle">
            写作、阅读与知识库整理集中在一个安静的工作空间。
          </p>
        </div>
      </header>

      <DocsClient
        documents={docs.map((d) => ({
          id: d.id,
          title: d.title,
          updatedAt: d.updatedAt,
        }))}
      />
    </div>
  );
}
