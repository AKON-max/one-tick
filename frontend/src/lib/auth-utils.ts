// ============================================================
// 服务端鉴权工具（对接 Python FastAPI 后端）
// 原 better-auth 版本 → 改为读 session_token cookie → 调 FastAPI /api/auth/me
// 保持 getCurrentUser / requireAuth / getAuthUser 同名导出，调用方无需改动。
// ============================================================

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  image: string | null;
  theme: string;
}

// Next.js 进程直连 FastAPI（容器内走 compose 网络；本地开发走 localhost）
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";

export async function getCurrentUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("session_token")?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/auth/me`, {
      // 把 cookie 原样带给 FastAPI，由后端校验 JWT
      headers: { Cookie: `session_token=${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as AuthUser;
  } catch {
    // FastAPI 不可达时按未登录处理，避免页面直接抛错
    return null;
  }
}

export async function requireAuth() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  return user;
}

/** For Route Handlers - returns null instead of redirecting */
export async function getAuthUser() {
  return getCurrentUser();
}
