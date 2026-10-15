// ============================================================
// 认证客户端（对接 Python FastAPI 后端）
// 原 better-auth 版本 → 改为直接 fetch FastAPI 的 /api/auth/*
// 保持 signIn / signUp / signOut / useSession 同名导出，
// 登录/注册/登出页面代码无需改动。
//
// 认证方式：JWT。登录/注册后 FastAPI 通过 Set-Cookie 写入
// session_token（同域反代，浏览器自动携带），useSession 读
// /api/auth/me 判断登录态。
// ============================================================

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  image: string | null;
  theme: string;
}

interface AuthResult {
  data: { user: AuthUser; token?: string } | null;
  error: { message?: string; status?: number } | null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    // 尽量解析 FastAPI 的 {"detail": "..."} 错误信息
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
    throw Object.assign(new Error(message), { status: res.status });
  }
  return res.json();
}

export async function signUp(params: {
  name: string;
  email: string;
  password: string;
}): Promise<AuthResult> {
  try {
    const data = await request<{ token: string; user: AuthUser }>(
      "/api/auth/register",
      { method: "POST", body: JSON.stringify(params) },
    );
    return { data: data, error: null };
  } catch (e) {
    const err = e as Error & { status?: number };
    return { data: null, error: { message: err.message, status: err.status } };
  }
}

export async function signIn(params: {
  email: string;
  password: string;
}): Promise<AuthResult> {
  try {
    const data = await request<{ token: string; user: AuthUser }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify(params) },
    );
    return { data: data, error: null };
  } catch (e) {
    const err = e as Error & { status?: number };
    return { data: null, error: { message: err.message, status: err.status } };
  }
}

export async function signInAsGuest(): Promise<AuthResult> {
  // 游客体验：后端新建一个隔离的临时账号并直接签发登录态（免注册）
  try {
    const data = await request<{ token: string; user: AuthUser }>(
      "/api/auth/guest",
      { method: "POST" },
    );
    return { data: data, error: null };
  } catch (e) {
    const err = e as Error & { status?: number };
    return { data: null, error: { message: err.message, status: err.status } };
  }
}

export async function signOut(): Promise<AuthResult> {
  // JWT 无状态：前端清掉 cookie 即完成登出（cookie 非 httpOnly 可直接删）
  document.cookie = "session_token=; Max-Age=0; path=/";
  return { data: null, error: null };
}

/** 获取当前登录用户（同步版本，供客户端组件判断登录态） */
export function getCurrentUser(): AuthUser | null {
  const token = document.cookie
    .split("; ")
    .find((c) => c.startsWith("session_token="))
    ?.split("=")[1];
  if (!token) return null;
  try {
    // JWT payload 是 base64url，第 2 段是数据
    const payload = JSON.parse(atob(token.split(".")[1]));
    return {
      id: payload.sub,
      name: payload.name,
      email: payload.email,
      image: null,
      theme: "system",
    };
  } catch {
    return null;
  }
}

/** useSession hook（兼容原 authClient.useSession 调用点） */
export function useSession() {
  // 简化实现：渲染时读一次 cookie；登录态变化由页面跳转驱动
  return { data: { user: getCurrentUser() }, isPending: false };
}

// 兼容导出（原代码若引用 authClient 对象本身）
export const authClient = {
  signIn: { email: signIn },
  signUp: { email: signUp },
  signInAsGuest,
  signOut,
  useSession,
};

// 兼容旧式调用：authClient.signIn.email(...) / authClient.signUp.email(...)
export const signInEmail = signIn;
