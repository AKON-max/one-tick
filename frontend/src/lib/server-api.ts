// ============================================================
// 服务端直连 FastAPI 的公共 helper
// 供 Server Actions / 服务端组件 fetch 使用：
//  - 自动把当前请求的 Cookie 原样带给 FastAPI（JWT 认证）
//  - 解析 FastAPI 的 {"detail": "..."} 错误信息
// ============================================================

import { headers } from "next/headers";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const h = await headers();
  const cookie = h.get("cookie") ?? "";

  const res = await fetch(`${API_INTERNAL_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(cookie ? { Cookie: cookie } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `请求失败 (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) {
        message = body.detail
          .map((d: { msg?: string }) => d.msg ?? "")
          .filter(Boolean)
          .join("；");
      }
    } catch {
      // 非 JSON 响应，保留默认信息
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
